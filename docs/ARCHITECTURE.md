# System Architecture

## 1. Overview

Tech Intelligence is a scheduled, cloud-native AI news
collection and intelligence platform.

## 2. Data Flow

1. Azure Container Apps Job starts on schedule.
2. Python Collector retrieves news from configured sources.
3. Data is normalized and deduplicated.
4. Cloudflare Worker provides historical state.
5. Gemini analyzes and ranks selected articles.
6. Hermes Agent coordinates AI processing.
7. Telegram receives the final briefing.
8. Results are persisted through Cloudflare Worker API.
9. Container exits after completion.

## 3. Infrastructure

### Azure
- Container Apps Environment
- Container Apps Job
- Managed secrets where supported

### Cloudflare
- Workers
- D1 Database

### Google
- Gemini API

### Telegram
- Bot API

## 4. Design Principles

- Stateless scheduled execution
- External persistent state
- Modular data collection
- Provider-independent AI interface
- Secure service-to-service communication
- Free-tier-first infrastructure
