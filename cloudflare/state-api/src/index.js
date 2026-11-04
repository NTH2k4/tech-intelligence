
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

const CONFIDENCE_LEVELS = ["low", "medium", "high"];
const RECOMMENDATIONS = ["read", "monitor", "skip"];

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

function validOptionalString(value, maxLength) {
  return (
    value === null ||
    value === undefined ||
    value === "" ||
    validString(value, maxLength)
  );
}

function cleanOptionalString(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  return value.trim();
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

function validOptionalScore(value) {
  return (
    value === null ||
    value === undefined ||
    (
      Number.isInteger(value) &&
      value >= 0 &&
      value <= 100
    )
  );
}

function firstPresent(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      return value;
    }
  }

  return null;
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
        summary,
        score,
        status,
        first_seen_at,
        last_seen_at,
        delivered_at,
        ai_category,
        relevance_score,
        impact_score,
        novelty_score,
        source_authority_score,
        summary_vi,
        why_it_matters,
        confidence,
        recommendation,
        scoring_model,
        scored_at
      FROM articles
      WHERE julianday(first_seen_at) >= julianday('now', '-30 days')
      ORDER BY score DESC, first_seen_at DESC
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

function prepareArticle(item, defaultScoringModel, defaultScoredAt) {
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return { error: "invalid_article" };
  }

  if (
    !validString(item.id, 128) ||
    !validString(item.title, 500) ||
    !validString(item.source, 120) ||
    !validString(item.url, 2048)
  ) {
    return { error: "invalid_article" };
  }

  let parsedUrl;

  try {
    parsedUrl = new URL(item.url);
  } catch {
    return { error: "invalid_article_url" };
  }

  if (!["http:", "https:"].includes(parsedUrl.protocol)) {
    return { error: "unsupported_article_url" };
  }

  const intelligence = item.intelligence ?? {};

  if (
    typeof intelligence !== "object" ||
    Array.isArray(intelligence)
  ) {
    return { error: "invalid_intelligence" };
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
    return { error: "invalid_article_metadata" };
  }

  const category = item.category ?? null;
  const publishedAt = item.published_at ?? null;
  const summary = item.summary ?? null;
  const deliveredAt = item.delivered_at ?? null;

  if (!validOptionalString(category, 80)) {
    return { error: "invalid_category" };
  }

  if (!validDate(publishedAt, true)) {
    return { error: "invalid_published_at" };
  }

  if (!validDate(deliveredAt, true)) {
    return { error: "invalid_delivered_at" };
  }

  if (!validOptionalString(summary, 10000)) {
    return { error: "invalid_summary" };
  }

  const aiCategory = firstPresent(
    item.ai_category,
    intelligence.category
  );

  const relevanceScore = firstPresent(
    item.relevance_score,
    intelligence.relevance_score
  );

  const impactScore = firstPresent(
    item.impact_score,
    intelligence.impact_score
  );

  const noveltyScore = firstPresent(
    item.novelty_score,
    intelligence.novelty_score
  );

  const sourceAuthorityScore = firstPresent(
    item.source_authority_score,
    intelligence.source_authority_score
  );

  const summaryVi = firstPresent(
    item.summary_vi,
    intelligence.summary_vi
  );

  const whyItMatters = firstPresent(
    item.why_it_matters,
    intelligence.why_it_matters
  );

  const confidence = firstPresent(
    item.confidence,
    intelligence.confidence
  );

  const recommendation = firstPresent(
    item.recommendation,
    intelligence.recommendation
  );

  const scoringModel = firstPresent(
    item.scoring_model,
    intelligence.scoring_model,
    defaultScoringModel
  );

  let scoredAt = firstPresent(
    item.scored_at,
    intelligence.scored_at
  );

  if (
    !validOptionalString(aiCategory, 80) ||
    !validOptionalScore(relevanceScore) ||
    !validOptionalScore(impactScore) ||
    !validOptionalScore(noveltyScore) ||
    !validOptionalScore(sourceAuthorityScore) ||
    !validOptionalString(summaryVi, 2000) ||
    !validOptionalString(whyItMatters, 2000) ||
    !validOptionalString(scoringModel, 120)
  ) {
    return { error: "invalid_intelligence_metadata" };
  }

  if (
    confidence !== null &&
    !CONFIDENCE_LEVELS.includes(confidence)
  ) {
    return { error: "invalid_confidence" };
  }

  if (
    recommendation !== null &&
    !RECOMMENDATIONS.includes(recommendation)
  ) {
    return { error: "invalid_recommendation" };
  }

  const hasIntelligence = [
    aiCategory,
    relevanceScore,
    impactScore,
    noveltyScore,
    sourceAuthorityScore,
    summaryVi,
    whyItMatters,
    confidence,
    recommendation
  ].some(value => value !== null && value !== undefined);

  if (!scoredAt && hasIntelligence) {
    scoredAt = defaultScoredAt || new Date().toISOString();
  }

  if (!validDate(scoredAt, true)) {
    return { error: "invalid_scored_at" };
  }

  return {
    article: {
      id: item.id.trim(),
      url: parsedUrl.href,
      title: item.title.trim(),
      source: item.source.trim(),
      category: cleanOptionalString(category),
      published_at: publishedAt || null,
      summary: cleanOptionalString(summary),
      score,
      status,
      delivered_at:
        deliveredAt ||
        (status === "delivered" ? new Date().toISOString() : null),
      ai_category: cleanOptionalString(aiCategory),
      relevance_score: relevanceScore ?? null,
      impact_score: impactScore ?? null,
      novelty_score: noveltyScore ?? null,
      source_authority_score: sourceAuthorityScore ?? null,
      summary_vi: cleanOptionalString(summaryVi),
      why_it_matters: cleanOptionalString(whyItMatters),
      confidence,
      recommendation,
      scoring_model: cleanOptionalString(scoringModel),
      scored_at: scoredAt || null,
      has_intelligence: hasIntelligence
    }
  };
}

async function commitData(request, env) {
  const rawBody = await request.text();

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
    typeof run !== "object" ||
    !validString(run.id, 128) ||
    !validDate(run.started_at) ||
    !validDate(run.completed_at, true) ||
    !RUN_STATUSES.includes(run.status) ||
    !Array.isArray(articles) ||
    articles.length > 100
  ) {
    return json({ error: "invalid_payload" }, 400);
  }

  if (
    body.scoring_model != null &&
    !validString(body.scoring_model, 120)
  ) {
    return json({ error: "invalid_scoring_model" }, 400);
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

  const defaultScoredAt =
    run.completed_at || new Date().toISOString();

  const preparedArticles = [];

  for (const item of articles) {
    const result = prepareArticle(
      item,
      body.scoring_model ?? null,
      defaultScoredAt
    );

    if (result.error) {
      return json({ error: result.error }, 400);
    }

    preparedArticles.push(result.article);
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
          delivered_at,
          summary,
          ai_category,
          relevance_score,
          impact_score,
          novelty_score,
          source_authority_score,
          summary_vi,
          why_it_matters,
          confidence,
          recommendation,
          scoring_model,
          scored_at
        )
        VALUES (
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
          ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )

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

          summary = COALESCE(
            excluded.summary,
            articles.summary
          ),

          score = CASE
            WHEN ? = 1 THEN excluded.score
            ELSE articles.score
          END,

          status = CASE
            WHEN articles.status = 'delivered'
            THEN 'delivered'
            WHEN articles.status = 'selected'
              AND excluded.status = 'discovered'
            THEN 'selected'
            ELSE excluded.status
          END,

          delivered_at = COALESCE(
            articles.delivered_at,
            excluded.delivered_at
          ),

          ai_category = COALESCE(
            excluded.ai_category,
            articles.ai_category
          ),

          relevance_score = COALESCE(
            excluded.relevance_score,
            articles.relevance_score
          ),

          impact_score = COALESCE(
            excluded.impact_score,
            articles.impact_score
          ),

          novelty_score = COALESCE(
            excluded.novelty_score,
            articles.novelty_score
          ),

          source_authority_score = COALESCE(
            excluded.source_authority_score,
            articles.source_authority_score
          ),

          summary_vi = COALESCE(
            excluded.summary_vi,
            articles.summary_vi
          ),

          why_it_matters = COALESCE(
            excluded.why_it_matters,
            articles.why_it_matters
          ),

          confidence = COALESCE(
            excluded.confidence,
            articles.confidence
          ),

          recommendation = COALESCE(
            excluded.recommendation,
            articles.recommendation
          ),

          scoring_model = COALESCE(
            excluded.scoring_model,
            articles.scoring_model
          ),

          scored_at = COALESCE(
            excluded.scored_at,
            articles.scored_at
          ),

          last_seen_at = CURRENT_TIMESTAMP
      `).bind(
        item.id,
        item.url,
        item.title,
        item.source,
        item.category,
        item.published_at,
        item.score,
        item.status,
        item.delivered_at,
        item.summary,
        item.ai_category,
        item.relevance_score,
        item.impact_score,
        item.novelty_score,
        item.source_authority_score,
        item.summary_vi,
        item.why_it_matters,
        item.confidence,
        item.recommendation,
        item.scoring_model,
        item.scored_at,
        item.has_intelligence ? 1 : 0
      )
    );
  }

  // D1 batch executes the statements transactionally.
  await env.DB.batch(statements);

  return json({
    ok: true,
    run_id: run.id,
    stored_articles: preparedArticles.length,
    scored_articles: preparedArticles.filter(
      item => item.has_intelligence
    ).length
  });
}


function isValidBriefingDate(value) {
  if (
    typeof value !== "string" ||
    !/^\d{4}-\d{2}-\d{2}$/.test(value)
  ) {
    return false;
  }

  const parsed = new Date(`${value}T00:00:00.000Z`);

  return (
    !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
  );
}

function isValidIsoDateTime(value) {
  return (
    typeof value === "string" &&
    value.length <= 40 &&
    !Number.isNaN(Date.parse(value))
  );
}

function validBriefingId(value) {
  return (
    typeof value === "string" &&
    /^[A-Za-z0-9_-]{1,128}$/.test(value)
  );
}

async function getBriefingStatus(request, env) {
  const url = new URL(request.url);
  const briefingDate = url.searchParams.get("date");

  if (!isValidBriefingDate(briefingDate)) {
    return json({
      ok: false,
      error: "invalid_briefing_date"
    }, 400);
  }

  const briefing = await env.DB.prepare(`
    SELECT
      id,
      briefing_date,
      status,
      started_at,
      sent_at,
      article_count,
      article_ids,
      content_hash,
      telegram_message_ids,
      error_message
    FROM briefing_runs
    WHERE briefing_date = ?
  `).bind(briefingDate).first();

  return json({
    ok: true,
    briefing: briefing || null
  });
}

async function claimBriefing(request, env) {
  let body;

  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ ok: false, error: "invalid_payload" }, 400);
  }

  const {
    id,
    briefing_date: briefingDate,
    started_at: startedAt,
    article_ids: articleIds,
    content_hash: contentHash = null
  } = body;

  if (!validBriefingId(id)) {
    return json({ ok: false, error: "invalid_briefing_id" }, 400);
  }

  if (!isValidBriefingDate(briefingDate)) {
    return json({ ok: false, error: "invalid_briefing_date" }, 400);
  }

  if (!isValidIsoDateTime(startedAt)) {
    return json({ ok: false, error: "invalid_started_at" }, 400);
  }

  if (
    !Array.isArray(articleIds) ||
    articleIds.length < 1 ||
    articleIds.length > 30 ||
    articleIds.some(item =>
      typeof item !== "string" ||
      item.length < 1 ||
      item.length > 128
    ) ||
    new Set(articleIds).size !== articleIds.length
  ) {
    return json({ ok: false, error: "invalid_article_ids" }, 400);
  }

  if (
    contentHash !== null &&
    (
      typeof contentHash !== "string" ||
      !/^[a-f0-9]{64}$/i.test(contentHash)
    )
  ) {
    return json({ ok: false, error: "invalid_content_hash" }, 400);
  }

  const placeholders = articleIds.map(() => "?").join(",");

  const articleResult = await env.DB.prepare(`
    SELECT
      id,
      status,
      delivered_at,
      scored_at,
      recommendation
    FROM articles
    WHERE id IN (${placeholders})
  `).bind(...articleIds).all();

  const foundArticles = articleResult.results || [];

  if (foundArticles.length !== articleIds.length) {
    return json({
      ok: false,
      error: "briefing_articles_not_found"
    }, 409);
  }

  const ineligibleArticles = foundArticles.filter(article =>
    !["read", "monitor"].includes(article.recommendation) ||
    !article.scored_at ||
    !["discovered", "selected"].includes(article.status) ||
    article.delivered_at
  );

  if (ineligibleArticles.length > 0) {
    return json({
      ok: false,
      error: "briefing_contains_ineligible_articles",
      rejected_article_ids: ineligibleArticles.map(item => item.id)
    }, 409);
  }

  const statements = [
    env.DB.prepare(`
      INSERT INTO briefing_runs (
        id,
        briefing_date,
        status,
        started_at,
        article_count,
        article_ids,
        content_hash
      )
      VALUES (?, ?, 'sending', ?, ?, ?, ?)
      ON CONFLICT(briefing_date) DO NOTHING
    `).bind(
      id,
      briefingDate,
      startedAt,
      articleIds.length,
      JSON.stringify(articleIds),
      contentHash
    ),

    env.DB.prepare(`
      UPDATE articles
      SET status = 'selected'
      WHERE id IN (${placeholders})
        AND status IN ('discovered', 'selected')
        AND delivered_at IS NULL
        AND EXISTS (
          SELECT 1
          FROM briefing_runs
          WHERE id = ?
            AND briefing_date = ?
            AND status = 'sending'
        )
    `).bind(...articleIds, id, briefingDate)
  ];

  const results = await env.DB.batch(statements);
  const inserted = Number(results?.[0]?.meta?.changes || 0) > 0;

  if (!inserted) {
    const existing = await env.DB.prepare(`
      SELECT id, briefing_date, status, started_at, sent_at,
             article_count, content_hash, error_message
      FROM briefing_runs
      WHERE briefing_date = ?
    `).bind(briefingDate).first();

    return json({
      ok: false,
      error: "briefing_date_already_claimed",
      briefing: existing || null
    }, 409);
  }

  const briefing = await env.DB.prepare(`
    SELECT
      id,
      briefing_date,
      status,
      started_at,
      article_count,
      article_ids,
      content_hash
    FROM briefing_runs
    WHERE id = ?
  `).bind(id).first();

  return json({
    ok: true,
    briefing
  }, 201);
}

async function completeBriefing(request, env) {
  let body;

  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ ok: false, error: "invalid_payload" }, 400);
  }

  const {
    id,
    briefing_date: briefingDate,
    sent_at: sentAt,
    telegram_message_ids: messageIds
  } = body;

  if (!validBriefingId(id)) {
    return json({ ok: false, error: "invalid_briefing_id" }, 400);
  }

  if (!isValidBriefingDate(briefingDate)) {
    return json({ ok: false, error: "invalid_briefing_date" }, 400);
  }

  if (!isValidIsoDateTime(sentAt)) {
    return json({ ok: false, error: "invalid_sent_at" }, 400);
  }

  if (
    !Array.isArray(messageIds) ||
    messageIds.length < 1 ||
    messageIds.length > 30 ||
    messageIds.some(value =>
      !Number.isSafeInteger(value) || value <= 0
    )
  ) {
    return json({
      ok: false,
      error: "invalid_telegram_message_ids"
    }, 400);
  }

  const briefing = await env.DB.prepare(`
    SELECT id, briefing_date, status, article_ids
    FROM briefing_runs
    WHERE id = ? AND briefing_date = ?
  `).bind(id, briefingDate).first();

  if (!briefing) {
    return json({ ok: false, error: "briefing_not_found" }, 404);
  }

  if (briefing.status === "sent") {
    return json({
      ok: true,
      already_completed: true,
      briefing
    });
  }

  if (briefing.status !== "sending") {
    return json({
      ok: false,
      error: "briefing_not_in_sending_state",
      status: briefing.status
    }, 409);
  }

  let articleIds;

  try {
    articleIds = JSON.parse(briefing.article_ids);
  } catch {
    return json({
      ok: false,
      error: "stored_article_ids_invalid"
    }, 500);
  }

  if (
    !Array.isArray(articleIds) ||
    articleIds.length < 1 ||
    articleIds.length > 30
  ) {
    return json({
      ok: false,
      error: "stored_article_ids_invalid"
    }, 500);
  }

  const placeholders = articleIds.map(() => "?").join(",");

  await env.DB.batch([
    env.DB.prepare(`
      UPDATE briefing_runs
      SET
        status = 'sent',
        sent_at = ?,
        telegram_message_ids = ?,
        error_message = NULL
      WHERE id = ?
        AND briefing_date = ?
        AND status = 'sending'
    `).bind(
      sentAt,
      JSON.stringify(messageIds),
      id,
      briefingDate
    ),

    env.DB.prepare(`
      UPDATE articles
      SET
        status = 'delivered',
        delivered_at = COALESCE(delivered_at, ?)
      WHERE id IN (${placeholders})
        AND EXISTS (
          SELECT 1
          FROM briefing_runs
          WHERE id = ?
            AND briefing_date = ?
            AND status = 'sent'
        )
    `).bind(sentAt, ...articleIds, id, briefingDate)
  ]);

  const updated = await env.DB.prepare(`
    SELECT id, briefing_date, status, sent_at,
           article_count, telegram_message_ids
    FROM briefing_runs
    WHERE id = ?
  `).bind(id).first();

  if (!updated || updated.status !== "sent") {
    return json({
      ok: false,
      error: "briefing_completion_not_confirmed"
    }, 409);
  }

  return json({
    ok: true,
    briefing: updated
  });
}

async function failBriefing(request, env) {
  let body;

  try {
    body = await request.json();
  } catch {
    return json({ ok: false, error: "invalid_json" }, 400);
  }

  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return json({ ok: false, error: "invalid_payload" }, 400);
  }

  const {
    id,
    briefing_date: briefingDate,
    error_message: errorMessage
  } = body;

  if (!validBriefingId(id)) {
    return json({ ok: false, error: "invalid_briefing_id" }, 400);
  }

  if (!isValidBriefingDate(briefingDate)) {
    return json({ ok: false, error: "invalid_briefing_date" }, 400);
  }

  if (
    typeof errorMessage !== "string" ||
    !errorMessage.trim() ||
    errorMessage.length > 1000
  ) {
    return json({ ok: false, error: "invalid_error_message" }, 400);
  }

  const result = await env.DB.prepare(`
    UPDATE briefing_runs
    SET
      status = 'failed',
      error_message = ?
    WHERE id = ?
      AND briefing_date = ?
      AND status = 'sending'
  `).bind(
    errorMessage.trim(),
    id,
    briefingDate
  ).run();

  const briefing = await env.DB.prepare(`
    SELECT id, briefing_date, status, started_at,
           sent_at, article_count, error_message
    FROM briefing_runs
    WHERE id = ? AND briefing_date = ?
  `).bind(id, briefingDate).first();

  if (!briefing) {
    return json({ ok: false, error: "briefing_not_found" }, 404);
  }

  if (briefing.status === "failed") {
    return json({
      ok: true,
      briefing,
      already_failed: Number(result?.meta?.changes || 0) === 0
    });
  }

  return json({
    ok: false,
    error: "briefing_cannot_be_marked_failed",
    status: briefing.status
  }, 409);
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

      const isBriefingStatus =
        url.pathname === "/internal/briefing/status";
      const isBriefingClaim =
        url.pathname === "/internal/briefing/claim";
      const isBriefingComplete =
        url.pathname === "/internal/briefing/complete";
      const isBriefingFail =
        url.pathname === "/internal/briefing/fail";

      const isKnownRoute =
        isState ||
        isCommit ||
        isBriefingStatus ||
        isBriefingClaim ||
        isBriefingComplete ||
        isBriefingFail;

      if (!isKnownRoute) {
        return json({ error: "not_found" }, 404);
      }

      const isGetRoute = isState || isBriefingStatus;
      const isPostRoute =
        isCommit ||
        isBriefingClaim ||
        isBriefingComplete ||
        isBriefingFail;

      if (
        (isGetRoute && request.method !== "GET") ||
        (isPostRoute && request.method !== "POST")
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

      if (isCommit) {
        return await commitData(request, env);
      }

      if (isBriefingStatus) {
        return await getBriefingStatus(request, env);
      }

      if (isBriefingClaim) {
        return await claimBriefing(request, env);
      }

      if (isBriefingComplete) {
        return await completeBriefing(request, env);
      }

      return await failBriefing(request, env);

    } catch (error) {
      console.error("Worker error:", error);

      return json({
        error: "internal_server_error"
      }, 500);
    }
  }
};
