import test from "node:test";
import assert from "node:assert/strict";

import scheduler, {
  dispatchWorkflow,
  vietnamCalendarDate
} from "../src/index.js";

const baseEnv = {
  GITHUB_TOKEN: "test-token-never-log",
  GITHUB_OWNER: "NTH2k4",
  GITHUB_REPOSITORY: "tech-intelligence",
  GITHUB_WORKFLOW_FILE: "daily-tech-intelligence.yml",
  GITHUB_REF: "main"
};

test("converts the scheduled UTC instant to the Vietnam calendar date", () => {
  assert.equal(
    vietnamCalendarDate("2026-11-14T00:17:00.000Z"),
    "2026-11-14"
  );

  // 17:30 UTC is already the following calendar day in Vietnam.
  assert.equal(
    vietnamCalendarDate("2026-11-14T17:30:00.000Z"),
    "2026-11-15"
  );
});

test("dispatches the production briefing workflow with sending enabled", async () => {
  let capturedUrl;
  let capturedOptions;

  const result = await dispatchWorkflow({
    env: baseEnv,
    scheduledTime: Date.parse("2026-11-14T00:17:00.000Z"),
    fetchImpl: async (url, options) => {
      capturedUrl = url;
      capturedOptions = options;
      return new Response(null, { status: 204 });
    }
  });

  assert.equal(
    capturedUrl,
    "https://api.github.com/repos/NTH2k4/tech-intelligence/actions/workflows/daily-tech-intelligence.yml/dispatches"
  );
  assert.equal(capturedOptions.method, "POST");
  assert.equal(
    capturedOptions.headers.Authorization,
    "Bearer test-token-never-log"
  );
  assert.equal(
    capturedOptions.headers["X-GitHub-Api-Version"],
    "2022-11-28"
  );
  assert.deepEqual(JSON.parse(capturedOptions.body), {
    ref: "main",
    inputs: {
      send_briefing: true,
      trigger_source: "cloudflare-cron"
    }
  });
  assert.deepEqual(result, {
    ok: true,
    workflow: "daily-tech-intelligence.yml",
    ref: "main",
    scheduled_at_utc: "2026-11-14T00:17:00.000Z",
    briefing_date_vietnam: "2026-11-14",
    http_status: 204
  });
});

test("fails closed when the GitHub token is not configured", async () => {
  await assert.rejects(
    dispatchWorkflow({
      env: { ...baseEnv, GITHUB_TOKEN: "" },
      scheduledTime: Date.parse("2026-11-14T00:17:00.000Z"),
      fetchImpl: async () => {
        throw new Error("fetch must not be called");
      }
    }),
    /GITHUB_TOKEN/
  );
});

test("treats non-204 GitHub responses as dispatch failures without echoing secrets", async () => {
  await assert.rejects(
    dispatchWorkflow({
      env: baseEnv,
      scheduledTime: Date.parse("2026-11-14T00:17:00.000Z"),
      fetchImpl: async () => new Response("private response body", { status: 403 })
    }),
    error => {
      assert.match(error.message, /HTTP 403/);
      assert.doesNotMatch(error.message, /test-token-never-log|private response body/);
      return true;
    }
  );
});

test("does not expose a public HTTP endpoint", async () => {
  const response = await scheduler.fetch(
    new Request("https://scheduler.example.workers.dev/"),
    baseEnv
  );

  assert.equal(response.status, 404);
});
