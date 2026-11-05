from __future__ import annotations

import argparse
import hashlib
import sys
import uuid
import re
from urllib.parse import urlsplit
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from briefing.composer import BriefingComposer
from integrations.state_api_client import StateAPIClient
from integrations.telegram_client import TelegramClient


LOCAL_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")
STATE_LIMIT = 500
MAX_ARTICLES = 30

# Explicit markers for records created by local tests, demos, or fixtures.
# Keep this conservative: normal technology articles should not be excluded
# merely because their title contains the word "test".
_TEST_SOURCE_MARKERS = {
    "demo",
    "fixture",
    "integration-test",
    "local-test",
    "synthetic",
    "test",
    "test-source",
    "unit-test",
}
_TEST_ID_PREFIXES = ("demo-", "fixture-", "sample-", "synthetic-", "test-")
_TEST_TITLE_PREFIXES = ("demo:", "fixture:", "sample:", "synthetic:", "test:")
_RESERVED_TEST_HOSTS = {"example.com", "example.org", "example.net", "localhost"}


def utc_now_iso() -> str:
    """Return an ISO-8601 UTC timestamp accepted by the Worker API."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


def local_briefing_date() -> str:
    """Use Vietnam's calendar date for the daily briefing key."""
    return datetime.now(LOCAL_TIMEZONE).date().isoformat()


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _normalized_marker(value: Any) -> str:
    text = str(value or "").strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")


def _is_synthetic_or_test_article(article: dict[str, Any]) -> bool:
    """Reject clearly synthetic records without guessing from ordinary titles."""
    article_id = str(article.get("id") or "").strip().lower()
    if article_id.startswith(_TEST_ID_PREFIXES):
        return True

    source = _normalized_marker(article.get("source"))
    if source in _TEST_SOURCE_MARKERS:
        return True

    title = str(article.get("title") or "").strip().lower()
    if title.startswith(_TEST_TITLE_PREFIXES):
        return True

    raw_url = str(article.get("url") or "").strip()
    try:
        parsed = urlsplit(raw_url)
        host = (parsed.hostname or "").lower().rstrip(".")
    except ValueError:
        return True

    if parsed.scheme not in {"http", "https"} or not host:
        return True
    if host in _RESERVED_TEST_HOSTS or host.endswith((".test", ".invalid", ".localhost")):
        return True

    return False


def _article_priority(article: dict[str, Any]) -> float:
    """Prefer the stored priority score; derive it from AI scores as fallback."""
    score = article.get("score")
    if _is_number(score) and float(score) > 0:
        return float(score)

    score_fields = (
        "relevance_score",
        "impact_score",
        "novelty_score",
        "source_authority_score",
    )
    if all(_is_number(article.get(field)) for field in score_fields):
        return (
            float(article["relevance_score"]) * 0.35
            + float(article["impact_score"]) * 0.30
            + float(article["novelty_score"]) * 0.15
            + float(article["source_authority_score"]) * 0.20
        )

    return float(score) if _is_number(score) else 0.0


def select_eligible_articles(
    state: dict[str, Any], limit: int = MAX_ARTICLES
) -> list[dict[str, Any]]:
    """Select scored, recommended, not-yet-delivered articles from State API."""
    raw_articles = state.get("articles", [])
    if not isinstance(raw_articles, list):
        raise RuntimeError("State API response field 'articles' must be a list")

    eligible: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for article in raw_articles:
        if not isinstance(article, dict):
            continue
        if _is_synthetic_or_test_article(article):
            continue

        article_id = article.get("id")
        if not isinstance(article_id, str) or not article_id.strip():
            continue
        if article_id in seen_ids:
            continue

        recommendation = str(article.get("recommendation") or "").strip().lower()
        status = str(article.get("status") or "").strip().lower()

        if recommendation not in {"read", "monitor"}:
            continue
        if status not in {"discovered", "selected"}:
            continue
        if not article.get("scored_at"):
            continue
        if article.get("delivered_at") is not None:
            continue
        if not str(article.get("title") or "").strip():
            continue
        if not str(article.get("url") or "").strip():
            continue

        seen_ids.add(article_id)
        eligible.append(article)

    eligible.sort(
        key=lambda item: (
            _article_priority(item),
            str(item.get("published_at") or ""),
            str(item.get("scored_at") or ""),
        ),
        reverse=True,
    )

    # Keep only fields that are useful to the composer; avoid forwarding
    # persistence/internal fields or arbitrary source payloads to the LLM.
    composer_fields = (
        "id",
        "title",
        "source",
        "url",
        "category",
        "published_at",
        "score",
        "summary",
        "summary_vi",
        "why_it_matters",
        "recommendation",
        "confidence",
        "relevance_score",
        "impact_score",
        "novelty_score",
        "source_authority_score",
    )

    selected: list[dict[str, Any]] = []
    for article in eligible[:limit]:
        selected.append(
            {
                field: article[field]
                for field in composer_fields
                if field in article and article[field] is not None
            }
        )

    return selected


def _print_preview(
    *,
    briefing_date: str,
    articles: list[dict[str, Any]],
    content: str,
    chunks: list[str],
    content_hash: str,
) -> None:
    print("\n========== DAILY BRIEFING PREVIEW ==========")
    print(f"Briefing date (Asia/Ho_Chi_Minh): {briefing_date}")
    print(f"Selected articles: {len(articles)}")
    print(f"Message chunks: {len(chunks)}")
    print(f"Content SHA-256: {content_hash}")
    print("Chunk lengths: " + ", ".join(str(len(chunk)) for chunk in chunks))
    print("\n---------------- GENERATED CONTENT ----------------\n")
    print(content)
    print("\n-------------- END GENERATED CONTENT --------------\n")


def _mark_failed_safely(
    state_client: StateAPIClient,
    *,
    briefing_id: str,
    briefing_date: str,
    error_message: str,
) -> None:
    try:
        state_client.fail_briefing(
            briefing_id=briefing_id,
            briefing_date=briefing_date,
            error_message=error_message[:2000],
        )
        print("Briefing state recorded as failed.")
    except Exception as fail_error:  # noqa: BLE001 - report recovery failure
        print(
            "WARNING: Could not mark briefing as failed. "
            f"Recovery error: {type(fail_error).__name__}: {fail_error}",
            file=sys.stderr,
        )


def _delivery_confirmation(*, send: bool, yes: bool) -> str | None:
    if yes and not send:
        return "yes_requires_send"
    if send and not yes and not sys.stdin.isatty():
        return "noninteractive_confirmation_required"
    return None


def run(
    *, limit: int, send: bool, yes: bool = False, base_url: str | None = None
) -> int:
    confirmation_error = _delivery_confirmation(send=send, yes=yes)
    if confirmation_error:
        if confirmation_error == "noninteractive_confirmation_required":
            raise RuntimeError(
                "Non-interactive delivery requires both --send and --yes"
            )
        raise RuntimeError("--yes is valid only when used together with --send")

    briefing_date = local_briefing_date()

    with StateAPIClient(base_url=base_url) as state_client:
        print("Reading article state from State API...")
        state = state_client.get_state(limit=STATE_LIMIT)
        raw_articles = state.get("articles", [])
        if not isinstance(raw_articles, list):
            raise RuntimeError("State API response field 'articles' must be a list")
        synthetic_count = sum(
            1 for item in raw_articles
            if isinstance(item, dict) and _is_synthetic_or_test_article(item)
        )
        articles = select_eligible_articles(state, limit=limit)
        print(f"Stored articles returned: {len(raw_articles)}")
        print(f"Synthetic/test articles excluded: {synthetic_count}")

        if not articles:
            print(
                "No eligible articles (read/monitor, scored, not delivered, "
                "and not marked as synthetic/test data). Nothing to generate or send."
            )
            return 0

        article_ids = [article["id"] for article in articles]
        print(f"Eligible articles found: {len(articles)}")
        print("Generating Vietnamese briefing with Gemini...")

        composer = BriefingComposer()
        content = composer.compose(articles=articles, demo=False)
        chunks = composer.split_message(content)

        if not chunks:
            raise RuntimeError("Briefing composer returned no sendable content")
        if any(len(chunk) > BriefingComposer.TELEGRAM_LIMIT for chunk in chunks):
            raise RuntimeError("Briefing chunk exceeds the configured Telegram limit")

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        _print_preview(
            briefing_date=briefing_date,
            articles=articles,
            content=content,
            chunks=chunks,
            content_hash=content_hash,
        )

        if not send:
            print("PREVIEW ONLY: no claim was created and no Telegram message was sent.")
            print("Use --send to explicitly start the delivery workflow.")
            return 0

        # Manual runs require an interactive confirmation. Unattended runs must
        # opt in explicitly with both --send and --yes.
        if sys.stdin.isatty() and not yes:
            print("\nThis command will send the briefing to the configured Telegram chat.")
            print("Review the content above. Type SEND to confirm delivery.")
            try:
                confirmation = input("Confirm Telegram delivery [SEND]: ").strip()
            except EOFError:
                confirmation = ""
            if confirmation != "SEND":
                print("DELIVERY CANCELLED: no claim was created and no Telegram message was sent.")
                return 0

        # Validate Telegram configuration before claiming the date, so a missing
        # token/chat ID does not leave a briefing stuck in the 'sending' state.
        telegram = TelegramClient()
        briefing_id = (
            f"ti_briefing_{briefing_date.replace('-', '')}_{uuid.uuid4().hex[:12]}"
        )

        print("Claiming briefing date before Telegram delivery...")
        claim_result = state_client.claim_briefing(
            briefing_id=briefing_id,
            briefing_date=briefing_date,
            started_at=utc_now_iso(),
            article_ids=article_ids,
            content_hash=content_hash,
        )
        claimed = claim_result.get("briefing")
        if isinstance(claimed, dict) and claimed.get("status") not in (None, "sending"):
            raise RuntimeError(
                "Claim API returned an unexpected state: "
                f"{claimed.get('status')}"
            )

        message_ids: list[int] = []
        print(f"Claim acquired. Sending {len(chunks)} Telegram message(s)...")

        for index, chunk in enumerate(chunks, start=1):
            try:
                result = telegram.send_message(chunk)
                message_id = result.get("message_id") if isinstance(result, dict) else None
                if isinstance(message_id, bool) or not isinstance(message_id, int) or message_id <= 0:
                    raise RuntimeError("Telegram response did not contain a valid message_id")
                message_ids.append(message_id)
                print(f"Telegram chunk {index}/{len(chunks)} sent (message_id={message_id}).")
            except Exception as send_error:  # noqa: BLE001 - persist failure state
                failure_message = (
                    f"Telegram delivery failed after {len(message_ids)}/{len(chunks)} "
                    "chunks; inspect runner logs before any manual retry."
                )
                _mark_failed_safely(
                    state_client,
                    briefing_id=briefing_id,
                    briefing_date=briefing_date,
                    error_message=failure_message,
                )
                print(
                    f"ERROR: Telegram delivery failed: {type(send_error).__name__}: "
                    f"{send_error}",
                    file=sys.stderr,
                )
                if message_ids:
                    print(
                        "WARNING: Some chunks were already delivered. Do not retry "
                        "blindly; inspect Telegram and the D1 briefing record first.",
                        file=sys.stderr,
                    )
                return 1

        # All Telegram chunks are confirmed. If completion cannot be confirmed,
        # do NOT mark the run failed: Telegram may already have delivered the full
        # message and changing the state could make a duplicate retry dangerous.
        try:
            completed = state_client.complete_briefing(
                briefing_id=briefing_id,
                briefing_date=briefing_date,
                sent_at=utc_now_iso(),
                telegram_message_ids=message_ids,
            )
        except Exception as complete_error:  # noqa: BLE001 - reconcile state
            print(
                "CRITICAL: Telegram messages were sent, but completion was not "
                "confirmed by State API. The briefing may still be 'sending'.",
                file=sys.stderr,
            )
            try:
                status_result = state_client.get_briefing_status(briefing_date)
                status_record = status_result.get("briefing")
                status_value = (
                    status_record.get("status")
                    if isinstance(status_record, dict)
                    else status_result.get("status")
                )
                print(f"Reconciled briefing status: {status_value!r}")
                if status_value == "sent":
                    print("State API confirms the briefing is already marked sent.")
                    return 0
            except Exception as status_error:  # noqa: BLE001
                print(
                    "Could not query briefing status: "
                    f"{type(status_error).__name__}: {status_error}",
                    file=sys.stderr,
                )
            print(
                "Do not rerun with --send until the briefing record and Telegram "
                "messages have been manually reconciled. "
                f"Completion error: {type(complete_error).__name__}: {complete_error}",
                file=sys.stderr,
            )
            return 2

        completed_record = completed.get("briefing")
        if isinstance(completed_record, dict) and completed_record.get("status") not in (
            None,
            "sent",
        ):
            print(
                "WARNING: Complete endpoint returned an unexpected briefing state: "
                f"{completed_record.get('status')}",
                file=sys.stderr,
            )
            return 2

        print("\nSUCCESS: Daily briefing sent and marked as sent in State API.")
        print(f"Date: {briefing_date}")
        print(f"Articles: {len(article_ids)}")
        print(f"Telegram messages: {len(message_ids)}")
        print(f"Briefing ID: {briefing_id}")
        return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a Vietnamese daily technology briefing. Preview is the "
            "default; Telegram delivery requires the explicit --send flag."
        )
    )
    parser.add_argument(
        "--send",
        action="store_true",
        help="Claim today's briefing and send it to Telegram.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Explicitly authorize non-interactive delivery; requires --send.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=MAX_ARTICLES,
        help=f"Maximum number of articles to include (1-{MAX_ARTICLES}; default: {MAX_ARTICLES}).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Optional State API base URL override. Use http://127.0.0.1:8787 "
            "for local Worker testing. Defaults to STATE_API_URL in .env."
        ),
    )
    args = parser.parse_args()

    if not 1 <= args.limit <= MAX_ARTICLES:
        parser.error(f"--limit must be between 1 and {MAX_ARTICLES}")
    if args.yes and not args.send:
        parser.error("--yes requires --send")
    return args


def main() -> int:
    args = parse_args()
    try:
        return run(
            limit=args.limit,
            send=args.send,
            yes=args.yes,
            base_url=args.base_url,
        )
    except KeyboardInterrupt:
        print("Interrupted by user.", file=sys.stderr)
        return 130
    except Exception as error:  # noqa: BLE001 - CLI boundary
        print(
            f"ERROR: {type(error).__name__}: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
