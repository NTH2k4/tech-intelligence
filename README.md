# Tech Intelligence

Personal AI-powered technology and AI news intelligence system. It collects selected public sources, evaluates relevance with Gemini, stores article and delivery state in Cloudflare D1 through a Cloudflare Worker, and sends a Vietnamese briefing to Telegram.

## Current implementation status

The local end-to-end workflow was verified on 2026-11-04:

- Collector retrieved 29 unique articles in a 36-hour window from all five configured sources.
- Source-balanced selection selected 10 articles across Hacker News, arXiv, Hugging Face, Google DeepMind, and OpenAI.
- Gemini scoring completed for all 10 articles using `gemini-3.5-flash-lite`.
- The pipeline committed 10 articles to local Cloudflare D1 and verified all 10 through the State API.
- The briefing service generated a Vietnamese briefing from six eligible articles (three `read`, three `monitor`).
- The operator confirmed delivery; Telegram returned message IDs `6` and `7`.
- Local D1 recorded the briefing as `sent` and all six articles as `delivered`.
- The briefing lifecycle integration test passed 7/7 local checks.

**This is a verified local workflow, not a production deployment.** Remote D1 migration/validation, scheduled execution, operational monitoring, and automated delivery reconciliation remain outstanding.

## Architecture

### Implemented components

- `collector/`: OpenAI News RSS, Google DeepMind RSS, Hugging Face RSS, arXiv AI/ML/CL RSS, and Hacker News.
- `collector/normalizer.py`: text cleanup, canonical URL normalization, timestamp parsing, and URL-derived article IDs.
- `scripts/run_pipeline.py`: source-balanced selection, AI scoring, State API commit, and read-back verification.
- `intelligence/`: Gemini-based relevance, impact, novelty, source-authority scoring, and recommendation (`read`, `monitor`, `skip`).
- `integrations/gemini_client.py`: Gemini API client.
- `integrations/state_api_client.py`: authenticated client for the Cloudflare Worker State API.
- `cloudflare/state-api/`: Worker API and D1 migrations.
- `briefing/`: Vietnamese briefing composition and Telegram message splitting.
- `scripts/run_daily_briefing.py`: eligible-article selection, preview, claim, Telegram delivery, and completion/failure state handling.
- `integrations/telegram_client.py`: Telegram Bot API client.

### Planned / not yet production deployed

- Azure Container Apps Jobs for scheduled daily execution.
- Remote D1 migration and remote Worker validation for the briefing lifecycle schema.
- Production secrets and deployment configuration.
- Alerting, operational monitoring, and automated recovery/reconciliation for partial Telegram delivery.
- Hermes Agent orchestration (future enhancement; not required by the current local pipeline).

## Repository layout

```text
cloudflare/state-api/   Cloudflare Worker, D1 migrations, Wrangler config
collector/              RSS and Hacker News collection, normalization
intelligence/           AI scoring and recommendation
integrations/           Gemini, State API, and Telegram clients
briefing/               Vietnamese briefing composer
scripts/                Pipeline, daily briefing, and local test scripts
docs/                   Architecture and security documentation
HANDOFF.md              Current engineering handoff and known limitations
```

## Local development

### 1. Python environment

```bash
cd ~/projects/tech-intelligence
source .venv/bin/activate
```

Configure `.env` using `.env.example` as a template. Never commit `.env`.

### 2. Start the local State API Worker

In Terminal 1:

```bash
cd ~/projects/tech-intelligence/cloudflare/state-api
npx wrangler dev --local
```

### 3. Collect news only

In Terminal 2, from the repository root:

```bash
cd ~/projects/tech-intelligence
source .venv/bin/activate
python -m collector.main \
  --hours 36 \
  --max-per-feed 8 \
  --hn-limit 15 \
  --output /tmp/tech-intelligence-collector.json
```

This writes a local JSON diagnostic file. It does not call Gemini or write to D1.

### 4. Run the pipeline without committing

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
GEMINI_SCORING_MODEL=gemini-3.5-flash-lite \
python -m scripts.run_pipeline \
  --hours 36 --max-per-feed 8 --hn-limit 15 --limit 10 --dry-run
```

### 5. Commit scored articles to local D1

Omit `--dry-run` to commit through the local Worker:

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
GEMINI_SCORING_MODEL=gemini-3.5-flash-lite \
python -m scripts.run_pipeline \
  --hours 36 --max-per-feed 8 --hn-limit 15 --limit 10
```

### 6. Preview a daily briefing

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
python -m scripts.run_daily_briefing --base-url http://127.0.0.1:8787
```

Preview is the default. It does not claim the briefing date and does not send Telegram messages.

### 7. Explicitly send a briefing

```bash
STATE_API_URL=http://127.0.0.1:8787 \
GEMINI_MODEL=gemini-3.6-flash \
python -m scripts.run_daily_briefing \
  --base-url http://127.0.0.1:8787 --send
```

Review the newly generated message and type `SEND` at the interactive confirmation prompt. This is a real Telegram delivery. Do not retry blindly if some chunks were sent but completion could not be confirmed; inspect Telegram and the `briefing_runs` record first.

## Environment variables

- `GEMINI_API_KEY`: Gemini API key.
- `GEMINI_MODEL`: briefing-generation model; `gemini-3.6-flash` was verified in the local run.
- `GEMINI_SCORING_MODEL`: scoring model; `gemini-3.5-flash-lite` was verified in the local run.
- `STATE_API_URL`: State API URL. Use `http://127.0.0.1:8787` for local development.
- `STATE_API_TOKEN`: Worker bearer token. Local development can read `API_BEARER_TOKEN` from the ignored Worker `.dev.vars` file.
- `TELEGRAM_BOT_TOKEN`: Telegram bot token.
- `TELEGRAM_CHAT_ID`: target Telegram chat ID.

Shell-exported variables take precedence over `.env` when dotenv is loaded without `override=True`. Check the current shell value when a model selection appears unexpected.

## Tests and verification

- `python -m scripts.test_intelligence --limit 10`: scoring test (uses Gemini API).
- `python -m scripts.test_briefing_state`: local Worker/D1 lifecycle integration test; creates synthetic records and prints a cleanup command. Stop the Worker before cleanup.
- `python -m py_compile scripts/run_pipeline.py scripts/run_daily_briefing.py`: syntax check for the main orchestration scripts.
- `npx wrangler d1 migrations list tech-intel-db --local`: inspect local migration state.

Use only a local D1 database for local tests. The remote migration `0003_briefing_runs.sql` was still pending at the handoff snapshot, and a previous remote operation returned Cloudflare API HTTP 403 code `7403`. Do not assume the remote schema is ready.

## Known limitations

See [HANDOFF.md](HANDOFF.md) for the complete handoff and next-agent checklist. Notable items:

- Validate generated URLs against URLs present in selected source material before Telegram delivery. A delivered briefing contained a generated URL typo (`github.org` instead of source-provided `github.com`).
- Tighten grounding of generated claims and Vietnamese proofreading.
- Resolve remote D1 migration/deployment permissions and validate the remote Worker.
- Add scheduled execution, monitoring, and safe recovery for partial Telegram delivery.

## Security

Never commit `.env`, Worker `.dev.vars`, API keys, Telegram tokens, Cloudflare tokens, or local state. `.env.example` must contain placeholders only. Review staged changes before every commit.
