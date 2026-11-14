const TIME_ZONE = "Asia/Ho_Chi_Minh";
const GITHUB_API_VERSION = "2022-11-28";

export function vietnamCalendarDate(value) {
  const date = value instanceof Date ? value : new Date(value);

  if (Number.isNaN(date.getTime())) {
    throw new Error("Invalid scheduled timestamp.");
  }

  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone: TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit"
  }).formatToParts(date);

  const values = Object.fromEntries(
    parts
      .filter(part => part.type !== "literal")
      .map(part => [part.type, part.value])
  );

  return `${values.year}-${values.month}-${values.day}`;
}

function requiredString(value, name) {
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error(`Missing required Worker configuration: ${name}`);
  }

  return value.trim();
}

export async function dispatchWorkflow({
  env,
  scheduledTime,
  fetchImpl = fetch
}) {
  const token = requiredString(env.GITHUB_TOKEN, "GITHUB_TOKEN");
  const owner = requiredString(env.GITHUB_OWNER, "GITHUB_OWNER");
  const repository = requiredString(
    env.GITHUB_REPOSITORY,
    "GITHUB_REPOSITORY"
  );
  const workflowFile = requiredString(
    env.GITHUB_WORKFLOW_FILE,
    "GITHUB_WORKFLOW_FILE"
  );
  const ref = requiredString(env.GITHUB_REF || "main", "GITHUB_REF");

  const scheduledAt = new Date(scheduledTime);

  if (Number.isNaN(scheduledAt.getTime())) {
    throw new Error("Invalid scheduled timestamp.");
  }

  const briefingDate = vietnamCalendarDate(scheduledAt);
  const workflowPath = encodeURIComponent(workflowFile);
  const endpoint =
    `https://api.github.com/repos/${encodeURIComponent(owner)}/` +
    `${encodeURIComponent(repository)}/actions/workflows/` +
    `${workflowPath}/dispatches`;

  const response = await fetchImpl(endpoint, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": GITHUB_API_VERSION
    },
    body: JSON.stringify({
      ref,
      inputs: {
        send_briefing: true,
        trigger_source: "cloudflare-cron"
      }
    })
  });

  // GitHub's workflow_dispatch endpoint confirms a dispatch with HTTP 204.
  // Do not log request headers, token values, or the full response body.
  if (response.status !== 204) {
    throw new Error(
      `GitHub workflow dispatch failed with HTTP ${response.status}; expected 204.`
    );
  }

  return {
    ok: true,
    workflow: workflowFile,
    ref,
    scheduled_at_utc: scheduledAt.toISOString(),
    briefing_date_vietnam: briefingDate,
    http_status: response.status
  };
}

export default {
  async scheduled(controller, env) {
    const result = await dispatchWorkflow({
      env,
      scheduledTime: controller.scheduledTime
    });

    console.log("TECH_INTELLIGENCE_WORKFLOW_DISPATCHED", JSON.stringify({
      workflow: result.workflow,
      ref: result.ref,
      scheduled_at_utc: result.scheduled_at_utc,
      briefing_date_vietnam: result.briefing_date_vietnam,
      http_status: result.http_status
    }));
  },

  async fetch() {
    // This Worker is schedule-only. No public HTTP endpoint is required.
    return new Response("Not Found", { status: 404 });
  }
};
