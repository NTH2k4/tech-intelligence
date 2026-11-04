# System Architecture

## 1. Purpose

Tech Intelligence collects technology and AI news, evaluates relevance and impact, persists article state, and produces a Vietnamese daily briefing delivered through Telegram.

This document distinguishes the components verified locally from planned production infrastructure.

## 2. Implemented local data flow

1. **Collection** — Python Collector fetches OpenAI News, Google DeepMind, Hugging Face, arXiv, and Hacker News.
2. **Normalization and deduplication** — normalize text, URLs, timestamps, and article identifiers; deduplicate canonical URLs.
3. **Source-balanced selection** — select recent articles across sources so a single source cannot fill the complete processing limit solely because of clustered timestamps.
4. **Intelligence scoring** — Gemini evaluates relevance, impact, novelty, and source authority; it assigns confidence and `read`, `monitor`, or `skip` recommendations.
5. **Persistence** — Python calls the authenticated Cloudflare Worker State API; the Worker stores article and run state in D1.
6. **Read-back verification** — the pipeline reads state back through the API and verifies submitted AI fields.
7. **Briefing selection** — select scored, not-yet-delivered `read` and `monitor` articles, excluding explicit test/demo records.
8. **Briefing generation** — Gemini produces Vietnamese briefing text; the composer splits it into Telegram-sized chunks.
9. **Delivery lifecycle** — claim the local briefing date, send chunks through Telegram, then mark the briefing `sent` and its articles `delivered`. Failures are recorded separately.

## 3. Components

### Python application

- `collector/`: RSS and Hacker News fetchers, normalization, and deduplication.
- `intelligence/`: AI scoring and recommendations.
- `integrations/`: Gemini, State API, and Telegram API clients.
- `briefing/`: Vietnamese briefing prompt, composition, and message splitting.
- `scripts/run_pipeline.py`: collection, source-balanced selection, scoring, commit, and verification.
- `scripts/run_daily_briefing.py`: preview-first briefing generation and controlled delivery.

### Cloudflare

- Worker: `cloudflare/state-api/src/index.js`.
- D1 database binding: `DB`.
- Migrations:
  - `0001_init_schema.sql`: articles and collection runs.
  - `0002_article_intelligence.sql`: AI evaluation fields.
  - `0003_briefing_runs.sql`: daily briefing delivery lifecycle.
- Internal API routes require a Bearer token. `/health` is public and reports Worker/database connectivity.

### External services

- Google Gemini API: article scoring and briefing generation.
- Telegram Bot API: sends briefing chunks to the configured chat.

## 4. Delivery state model

Briefing records use:

- `sending`: the date has been claimed before Telegram delivery.
- `sent`: every Telegram chunk was accepted and State API completion was confirmed.
- `failed`: delivery failed before all chunks completed; inspect Telegram and D1 before any retry.

Article records use `discovered`, `selected`, and `delivered` as the primary briefing path. Articles are marked `delivered` only after briefing completion is confirmed.

A partial Telegram send is an external side effect and cannot be rolled back. Do not blindly retry after an ambiguous failure. Reconcile Telegram message history and the D1 briefing record first.

## 5. Verified local status (2026-11-04)

- Collector returned 29 unique articles in a 36-hour window from all five sources.
- Source-balanced selection selected 10 articles from all five sources.
- Gemini scoring completed for all 10 articles.
- Local State API/D1 committed and read-back verified all 10 articles.
- Six eligible articles (three `read`, three `monitor`) were composed into a Vietnamese briefing.
- The operator confirmed delivery; Telegram returned message IDs `6` and `7`.
- Local D1 recorded briefing status `sent` and all six articles as `delivered`.
- The local briefing lifecycle integration harness passed 7/7 checks.

These results demonstrate a local end-to-end workflow; they do not establish production readiness.

## 6. Production target / not yet completed

- Apply and verify the briefing lifecycle migration on remote D1.
- Deploy and validate the Worker against remote D1.
- Configure production secrets without committing credentials.
- Provision scheduled execution (Azure Container Apps Jobs is the current candidate).
- Add run monitoring, alerting, and operational recovery/reconciliation.
- Evaluate Hermes Agent as a future orchestration enhancement; it is not required for the verified local workflow.

## 7. Design principles

- Keep collection, scoring, persistence, composition, and delivery independently testable.
- Treat external content as untrusted input; ignore instructions embedded in source material.
- Preserve original article URLs and validate generated links before delivery.
- Prefer quality over filling a fixed article count.
- Never mark an article delivered until completion is confirmed by State API.
- Keep all secrets in ignored local files or managed secret stores.
