
const JSON_HEADERS = {
  "Content-Type": "application/json; charset=utf-8",
  "Cache-Control": "no-store"
};

const ARTICLE_STATUSES = [
  "discovered",
  "selected",
  "delivered",
  "failed"
];

const RUN_STATUSES = [
  "running",
  "success",
  "partial",
  "failed",
  "no_news"
];

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: JSON_HEADERS
  });
}

function validString(value, maxLength) {
  return (
    typeof value === "string" &&
    value.trim().length > 0 &&
    value.length <= maxLength
  );
}

function validDate(value, optional = false) {
  if (optional && (value === null || value === undefined || value === "")) {
    return true;
  }

  return (
    typeof value === "string" &&
    value.length <= 64 &&
    !Number.isNaN(Date.parse(value))
  );
}

function authorized(request, secret) {
  if (!secret) return false;

  const header = request.headers.get("Authorization") || "";

  if (!header.startsWith("Bearer ")) return false;

  const token = header.slice(7);

  if (!token || token.length !== secret.length) return false;

  let difference = 0;

  for (let i = 0; i < token.length; i++) {
    difference |= token.charCodeAt(i) ^ secret.charCodeAt(i);
  }

  return difference === 0;
}

async function getState(request, env) {
  const url = new URL(request.url);

  const rawLimit = Number(url.searchParams.get("limit") || 100);

  const limit = Number.isInteger(rawLimit)
    ? Math.min(Math.max(rawLimit, 1), 500)
    : 100;

  const [articles, runs] = await Promise.all([
    env.DB.prepare(`
      SELECT
        id,
        url,
        title,
        source,
        category,
        published_at,
        score,
        status,
        first_seen_at,
        delivered_at
      FROM articles
      WHERE julianday(first_seen_at) >= julianday('now', '-30 days')
      ORDER BY first_seen_at DESC
      LIMIT ?
    `).bind(limit).all(),

    env.DB.prepare(`
      SELECT
        id,
        started_at,
        completed_at,
        status,
        article_count,
        error_message
      FROM daily_runs
      ORDER BY started_at DESC
      LIMIT 10
    `).all()
  ]);

  return json({
    ok: true,
    window_days: 30,
    articles: articles.results || [],
    recent_runs: runs.results || []
  });
}

async function commitData(request, env) {
  const rawBody = await request.text();

  // Limit payload size to approximately 256 KB.
  if (new TextEncoder().encode(rawBody).length > 256_000) {
    return json({ error: "payload_too_large" }, 413);
  }

  if (
    !(request.headers.get("Content-Type") || "")
      .toLowerCase()
      .includes("application/json")
  ) {
    return json({ error: "content_type_must_be_json" }, 415);
  }

  let body;

  try {
    body = JSON.parse(rawBody);
  } catch {
    return json({ error: "invalid_json" }, 400);
  }

  const run = body?.run;
  const articles = body?.articles;

  if (
    !run ||
    !validString(run.id, 128) ||
    !validDate(run.started_at) ||
    !validDate(run.completed_at, true) ||
    !RUN_STATUSES.includes(run.status) ||
    !Array.isArray(articles) ||
    articles.length > 100
  ) {
    return json({ error: "invalid_payload" }, 400);
  }

  const articleCount = run.article_count ?? articles.length;

  if (
    !Number.isInteger(articleCount) ||
    articleCount < 0 ||
    articleCount > 10000
  ) {
    return json({ error: "invalid_article_count" }, 400);
  }

  if (
    run.error_message !== undefined &&
    run.error_message !== null &&
    typeof run.error_message !== "string"
  ) {
    return json({ error: "invalid_error_message" }, 400);
  }

  const preparedArticles = [];

  for (const item of articles) {
    if (
      !item ||
      !validString(item.id, 128) ||
      !validString(item.title, 500) ||
      !validString(item.source, 120) ||
      !validString(item.url, 2048)
    ) {
      return json({ error: "invalid_article" }, 400);
    }

    let parsedUrl;

    try {
      parsedUrl = new URL(item.url);
    } catch {
      return json({ error: "invalid_article_url" }, 400);
    }

    if (!["http:", "https:"].includes(parsedUrl.protocol)) {
      return json({ error: "unsupported_article_url" }, 400);
    }

    const score = item.score ?? 0;
    const status = item.status ?? "discovered";

    if (
      typeof score !== "number" ||
      !Number.isFinite(score) ||
      score < 0 ||
      score > 100 ||
      !ARTICLE_STATUSES.includes(status)
    ) {
      return json({ error: "invalid_article_metadata" }, 400);
    }

    if (
      item.category != null &&
      !validString(item.category, 80)
    ) {
      return json({ error: "invalid_category" }, 400);
    }

    if (!validDate(item.published_at, true)) {
      return json({ error: "invalid_published_at" }, 400);
    }

    if (!validDate(item.delivered_at, true)) {
      return json({ error: "invalid_delivered_at" }, 400);
    }

    preparedArticles.push({
      id: item.id.trim(),
      url: parsedUrl.href,
      title: item.title.trim(),
      source: item.source.trim(),
      category: item.category || null,
      published_at: item.published_at || null,
      score,
      status,
      delivered_at:
        item.delivered_at ||
        (status === "delivered" ? new Date().toISOString() : null)
    });
  }

  const statements = [
    env.DB.prepare(`
      INSERT INTO daily_runs (
        id,
        started_at,
        completed_at,
        status,
        article_count,
        error_message
      )
      VALUES (?, ?, ?, ?, ?, ?)

      ON CONFLICT(id) DO UPDATE SET
        completed_at = excluded.completed_at,
        status = excluded.status,
        article_count = excluded.article_count,
        error_message = excluded.error_message
    `).bind(
      run.id,
      run.started_at,
      run.completed_at || null,
      run.status,
      articleCount,
      run.error_message
        ? run.error_message.slice(0, 1000)
        : null
    )
  ];

  for (const item of preparedArticles) {
    statements.push(
      env.DB.prepare(`
        INSERT INTO articles (
          id,
          url,
          title,
          source,
          category,
          published_at,
          score,
          status,
          delivered_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)

        ON CONFLICT(url) DO UPDATE SET
          title = excluded.title,
          source = excluded.source,
          category = COALESCE(
            excluded.category,
            articles.category
          ),
          published_at = COALESCE(
            excluded.published_at,
            articles.published_at
          ),
          score = MAX(
            articles.score,
            excluded.score
          ),
          status = CASE
            WHEN articles.status = 'delivered'
            THEN 'delivered'
            ELSE excluded.status
          END,
          last_seen_at = CURRENT_TIMESTAMP,
          delivered_at = COALESCE(
            articles.delivered_at,
            excluded.delivered_at
          )
      `).bind(
        item.id,
        item.url,
        item.title,
        item.source,
        item.category,
        item.published_at,
        item.score,
        item.status,
        item.delivered_at
      )
    );
  }

  // D1 batch runs the statements transactionally.
  await env.DB.batch(statements);

  return json({
    ok: true,
    run_id: run.id,
    stored_articles: preparedArticles.length
  });
}

export default {
  async fetch(request, env) {
    try {
      const url = new URL(request.url);

      if (url.pathname === "/health" && request.method === "GET") {
        if (!env.DB) {
          return json({
            ok: false,
            database: "unavailable"
          }, 503);
        }

        await env.DB.prepare("SELECT 1 AS ok").first();

        return json({
          ok: true,
          service: "tech-intel-state-api",
          database: "connected"
        });
      }

      const isState = url.pathname === "/internal/state";
      const isCommit = url.pathname === "/internal/commit";

      if (!isState && !isCommit) {
        return json({ error: "not_found" }, 404);
      }

      if (
        (isState && request.method !== "GET") ||
        (isCommit && request.method !== "POST")
      ) {
        return json({ error: "method_not_allowed" }, 405);
      }

      if (!env.DB || !env.API_BEARER_TOKEN) {
        return json({ error: "server_not_configured" }, 503);
      }

      if (!authorized(request, env.API_BEARER_TOKEN)) {
        return json({ error: "unauthorized" }, 401);
      }

      if (isState) {
        return await getState(request, env);
      }

      return await commitData(request, env);

    } catch (error) {
      // Do not expose internal error details to API consumers.
      console.error("Worker error:", error);

      return json({
        error: "internal_server_error"
      }, 500);
    }
  }
};
