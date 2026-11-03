# Tech Intelligence

Personal AI-powered technology intelligence system.

## Overview

Tech Intelligence automatically discovers, collects, filters,
analyzes and summarizes important technology and AI news.

The system delivers a Vietnamese daily technology briefing
through Telegram.

## Architecture

- Compute: Azure Container Apps Jobs
- State API: Cloudflare Workers
- Database: Cloudflare D1
- Collector: Python
- AI Orchestration: Hermes Agent
- LLM: Google Gemini API
- Notification: Telegram Bot API
- Development: GitHub + GitHub Copilot

## Project Structure

- cloudflare/: Workers API and D1 migrations
- collector/: News collection and filtering
- agent/: Hermes Agent prompts and configuration
- infra/: Cloud infrastructure and deployment
- docs/: Architecture, deployment and security documents
- tests/: Automated tests

## Development Principles

1. Prefer free-tier infrastructure.
2. Never commit credentials or API keys.
3. Every database change must have a migration.
4. Keep collection, AI processing and delivery independent.
5. Avoid duplicate news delivery.
6. Validate external data before processing.
7. Make scheduled jobs idempotent where possible.

## Current Status

- [x] Cloudflare D1 database created
- [x] D1 schema initialized locally
- [x] Cloudflare Worker deployed
- [x] Worker authentication implemented
- [x] Local API tests passed
- [x] Production health and authorization tests passed
- [ ] Production write test
- [ ] Python news collector
- [ ] Gemini integration
- [ ] Telegram delivery
- [ ] Hermes Agent integration
- [ ] Azure Container Apps deployment

## Development

Cloudflare Worker:

```bash
cd cloudflare/state-api
npm install
npx wrangler dev --local
```

## Security

Never commit:
- Google API keys
- Telegram bot tokens
- Cloudflare API tokens
- Worker bearer tokens
- Azure credentials
- Environment files containing secrets
