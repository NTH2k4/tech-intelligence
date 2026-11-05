#!/usr/bin/env bash
set -Eeuo pipefail

: "${STATE_API_URL:?STATE_API_URL is required}"
: "${STATE_API_TOKEN:?STATE_API_TOKEN is required in the scheduled environment}"
: "${GEMINI_API_KEY:?GEMINI_API_KEY is required}"
: "${GEMINI_MODEL:?GEMINI_MODEL is required}"
: "${GEMINI_SCORING_MODEL:?GEMINI_SCORING_MODEL is required}"
[[ "$STATE_API_URL" == https://* ]] || {
  echo "STATE_API_URL must use HTTPS in the scheduled environment" >&2
  exit 2
}

mode="${1:---preview}"
case "$mode" in
  --preview) briefing_flags=() ;;
  --send)
    : "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required for delivery}"
    : "${TELEGRAM_CHAT_ID:?TELEGRAM_CHAT_ID is required for delivery}"
    briefing_flags=(--send --yes)
    ;;
  *) echo "Usage: $0 [--preview|--send]" >&2; exit 2 ;;
esac

python -m scripts.run_pipeline \
  --hours 36 \
  --max-per-feed 8 \
  --hn-limit 15 \
  --limit 10

python -m scripts.run_daily_briefing \
  --base-url "$STATE_API_URL" \
  "${briefing_flags[@]}"
