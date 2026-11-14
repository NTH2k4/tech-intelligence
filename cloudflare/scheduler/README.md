# Tech Intelligence — Cloudflare Daily Scheduler

This Worker is a dedicated, schedule-only trigger for the existing GitHub Actions
pipeline. It does not collect news, call Gemini, access D1, or send Telegram
messages itself.

## Schedule

Cloudflare Cron Triggers use UTC. The configured expression is:

```cron
17 0 * * *
```

This fires daily at 00:17 UTC / 07:17 in `Asia/Ho_Chi_Minh`.

The Worker calls GitHub's `workflow_dispatch` API for
`.github/workflows/daily-tech-intelligence.yml` on `main`, passing:

- `send_briefing=true`
- `trigger_source=cloudflare-cron`

A successful HTTP 204 response means GitHub accepted the dispatch request. It
does not mean the job has started or that Telegram delivery has completed.
The GitHub Actions run and the State API delivery record remain the source of
truth for execution and delivery.

## Required configuration

Create a fine-grained GitHub personal access token scoped to this repository:

- Repository access: only `NTH2k4/tech-intelligence`
- Repository permission: `Actions: Read and write`
- No Contents, Secrets, Administration, or Organization permissions are needed
  for the dispatch endpoint.
- Set an expiry and rotate the token before it expires.

Add these GitHub repository settings before deploying:

| Setting | Type | Value |
|---|---|---|
| `CLOUDFLARE_API_TOKEN` | Actions secret | Cloudflare API token with permission to edit Workers Scripts for the target account |
| `GITHUB_WORKFLOW_DISPATCH_TOKEN` | Actions secret | Fine-grained token described above |
| `CLOUDFLARE_ACCOUNT_ID` | Actions variable | Cloudflare account ID containing the Worker |

The deployment workflow uploads `GITHUB_WORKFLOW_DISPATCH_TOKEN` to the Worker
as the secret `GITHUB_TOKEN`. The token is never written to repository files
or printed in workflow logs.

## Deploy

After the GitHub settings above are configured, run:

**GitHub → Actions → Deploy Cloudflare Daily Scheduler → Run workflow**

The workflow deploys this Worker and then stores/rotates its `GITHUB_TOKEN`
secret. Wrangler deploys the Cron Trigger from this file.

The equivalent local commands, from the repository root, are:

```bash
npx --yes wrangler@4.156.2 deploy --config cloudflare/scheduler/wrangler.jsonc
printf '%s' "$GITHUB_WORKFLOW_DISPATCH_TOKEN" |
  npx --yes wrangler@4.156.2 secret put GITHUB_TOKEN     --config cloudflare/scheduler/wrangler.jsonc
```

Do not run the local commands until the required Cloudflare and GitHub
credentials are available in the shell environment.

## Local test

From the repository root:

```bash
node --test cloudflare/scheduler/test/*.test.js
npx --yes wrangler@4.156.2 dev   --config cloudflare/scheduler/wrangler.jsonc   --test-scheduled
```

Then invoke the local scheduled handler in another terminal:

```bash
curl "http://localhost:8787/cdn-cgi/local/scheduled?format=json"
```

A local scheduled invocation makes a real GitHub dispatch if the Worker is
configured with a real token. Use a disposable test repository or a deliberately
non-production token when testing dispatch behavior. The unit tests do not make
network requests.

## Cutover and safety

- Keep the existing GitHub `schedule` trigger enabled during the initial
  deployment and verification period. It is the fallback until a Cloudflare
  Cron event and a corresponding GitHub run have been observed.
- The workflow performs a State API delivery-state preflight before the
  collection/scoring work. A later fallback invocation exits successfully
  without running the pipeline when today's briefing is already `sent`.
- The existing D1 `briefing_date` uniqueness and `run_daily_briefing.py`
  preflight remain the final duplicate-delivery safeguards.
- Do not remove the GitHub schedule until the Cloudflare Cron invocation and
  the resulting Telegram delivery have both been verified on production.
- If Cloudflare scheduling fails, inspect **Workers & Pages → tech-intel-scheduler
  → Settings → Trigger Events** and the Worker logs. If dispatch was accepted,
  inspect the resulting GitHub Actions run before attempting any manual retry.

To roll back, first disable/delete the Worker's Cron Trigger in the Cloudflare
dashboard (or deploy an empty `triggers.crons` array), then verify the native
GitHub schedule still runs. Do not delete or rotate the only active GitHub
dispatch token until the Worker trigger is disabled.
