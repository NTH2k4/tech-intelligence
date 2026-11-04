"""Local-only integration test for Tech Intelligence briefing lifecycle.

Run from the repository root with the local Worker running at 127.0.0.1:8787.
This script creates two synthetic articles and a synthetic daily run through the
local State API. It DOES NOT call Telegram and DOES NOT access production.

After the test, stop the local Worker and run the printed Wrangler cleanup SQL.
"""
from __future__ import annotations

import hashlib
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

from integrations.state_api_client import StateAPIClient, StateAPIError

LOCAL_URL = "http://127.0.0.1:8787"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def find_article(client: StateAPIClient, article_id: str) -> dict:
    result = client.get_state(limit=500)
    articles = result.get("articles", [])
    for article in articles:
        if article.get("id") == article_id:
            return article
    raise AssertionError(f"Article {article_id!r} was not returned by State API")


def find_briefing(client: StateAPIClient, briefing_date: str) -> dict:
    result = client.get_briefing_status(briefing_date)
    briefing = result.get("briefing")
    require(isinstance(briefing, dict), f"No briefing record found for {briefing_date}")
    return briefing


def main() -> int:
    tag = f"ti_lifecycle_test_{uuid.uuid4().hex[:12]}"
    run_id = f"{tag}_run"
    article_ids = [f"{tag}_article_complete", f"{tag}_article_fail"]
    briefing_ids = [f"{tag}_briefing_complete", f"{tag}_briefing_fail"]

    print("Synthetic test identifiers (keep these if the test fails):")
    print(f"  tag: {tag}")
    print(f"  daily_run: {run_id}")
    print(f"  articles: {article_ids[0]}, {article_ids[1]}")
    print(f"  briefings: {briefing_ids[0]}, {briefing_ids[1]}")

    # Use two consecutive future dates and check that neither is already claimed.
    first_day = date.today() + timedelta(days=400)
    chosen_date = None

    with StateAPIClient(base_url=LOCAL_URL) as client:
        for offset in range(0, 3000):
            candidate = first_day + timedelta(days=offset)
            candidate_next = candidate + timedelta(days=1)
            status_a = client.get_briefing_status(candidate.isoformat()).get("briefing")
            status_b = client.get_briefing_status(candidate_next.isoformat()).get("briefing")
            if status_a is None and status_b is None:
                chosen_date = (candidate.isoformat(), candidate_next.isoformat())
                break

        require(chosen_date is not None, "Could not find two unused future test dates")
        complete_date, fail_date = chosen_date

        now = utc_now()
        articles = []
        for index, article_id in enumerate(article_ids):
            title = f"Synthetic local lifecycle test article {index + 1}"
            intelligence = {
                "summary": "Synthetic test data. This is not a real news article.",
                "ai_category": "Developer Tools",
                "relevance_score": 90,
                "impact_score": 80,
                "novelty_score": 75,
                "source_authority_score": 70,
                "summary_vi": "Bài viết giả dùng để kiểm thử vòng đời bản tin trên D1 local.",
                "why_it_matters": "Chỉ phục vụ kiểm thử kỹ thuật.",
                "confidence": "high",
                "recommendation": "read",
                "scoring_model": "local-lifecycle-test",
                "scored_at": now,
            }
            articles.append({
                "id": article_id,
                "url": f"https://example.com/tech-intelligence-local-test/{tag}/{index + 1}",
                "title": title,
                "source": "Tech Intelligence Local Test",
                "category": "Developer Tools",
                "published_at": now,
                "score": 82,
                "status": "discovered",
                "intelligence": intelligence,
            })

        run = {
            "id": run_id,
            "started_at": now,
            "completed_at": now,
            "status": "success",
            "article_count": len(articles),
            "error_message": None,
        }

        print("[1/7] Seeding two synthetic articles through local State API...")
        commit_result = client.commit(run=run, articles=articles)
        require(commit_result.get("stored_articles") == 2, "Expected two stored test articles")
        for article_id in article_ids:
            article = find_article(client, article_id)
            require(article.get("status") == "discovered", "Seed article should start as discovered")
            require(article.get("delivered_at") is None, "Seed article must not be delivered")
        print("  PASS: two test articles stored; neither is delivered")

        print("[2/7] Claiming the first briefing...")
        content_hash = hashlib.sha256(f"{tag}:complete".encode()).hexdigest()
        claim_result = client.claim_briefing(
            briefing_id=briefing_ids[0],
            briefing_date=complete_date,
            started_at=now,
            article_ids=[article_ids[0]],
            content_hash=content_hash,
        )
        require(claim_result.get("ok") is True, "First claim did not return ok=true")
        require(find_briefing(client, complete_date).get("status") == "sending", "Claim status should be sending")
        require(find_article(client, article_ids[0]).get("status") == "selected", "Claim should mark article selected")
        print("  PASS: briefing is sending; article is selected")

        print("[3/7] Ensuring duplicate claim for the same date is rejected...")
        duplicate_rejected = False
        try:
            client.claim_briefing(
                briefing_id=f"{tag}_duplicate_claim",
                briefing_date=complete_date,
                started_at=now,
                article_ids=[article_ids[0]],
                content_hash=content_hash,
            )
        except StateAPIError as exc:
            duplicate_rejected = "HTTP 409" in str(exc)
            if not duplicate_rejected:
                raise
        require(duplicate_rejected, "Duplicate date claim was not rejected with HTTP 409")
        print("  PASS: duplicate claim rejected with HTTP 409")

        print("[4/7] Completing the first briefing (simulated Telegram message ID)...")
        complete_result = client.complete_briefing(
            briefing_id=briefing_ids[0],
            briefing_date=complete_date,
            sent_at=utc_now(),
            telegram_message_ids=[987654321],  # synthetic ID; no Telegram request is made
        )
        require(complete_result.get("ok") is True, "Complete did not return ok=true")
        require(find_briefing(client, complete_date).get("status") == "sent", "Briefing should be sent")
        delivered_article = find_article(client, article_ids[0])
        require(delivered_article.get("status") == "delivered", "Completed article should be delivered")
        require(bool(delivered_article.get("delivered_at")), "Delivered article needs delivered_at")
        print("  PASS: briefing is sent; article is delivered with delivered_at")

        print("[5/7] Claiming the second briefing for the failure path...")
        fail_hash = hashlib.sha256(f"{tag}:fail".encode()).hexdigest()
        fail_claim = client.claim_briefing(
            briefing_id=briefing_ids[1],
            briefing_date=fail_date,
            started_at=utc_now(),
            article_ids=[article_ids[1]],
            content_hash=fail_hash,
        )
        require(fail_claim.get("ok") is True, "Failure-path claim did not return ok=true")
        require(find_article(client, article_ids[1]).get("status") == "selected", "Failure-path article should be selected")
        print("  PASS: second briefing claimed")

        print("[6/7] Marking the second briefing as failed...")
        fail_result = client.fail_briefing(
            briefing_id=briefing_ids[1],
            briefing_date=fail_date,
            error_message="Intentional local lifecycle test failure; no Telegram call was made.",
        )
        require(fail_result.get("ok") is True, "Fail did not return ok=true")
        require(find_briefing(client, fail_date).get("status") == "failed", "Briefing should be failed")
        second_article = find_article(client, article_ids[1])
        require(second_article.get("status") != "delivered", "Failed article must not be marked delivered")
        print("  PASS: briefing is failed; article is not delivered")

    print("[7/7] Lifecycle integration tests PASSED")
    print("No Telegram request was made. All writes went to the local Worker/D1 only.")
    print("\nTest identifiers (for cleanup):")
    print(f"  tag: {tag}")
    print(f"  daily_run: {run_id}")
    print(f"  articles: {article_ids[0]}, {article_ids[1]}")
    print(f"  briefings: {briefing_ids[0]}, {briefing_ids[1]}")
    print(f"  dates: {complete_date}, {fail_date}")
    print("\nAfter stopping the local Worker, run this cleanup from the Worker directory:")
    print("  cd ~/projects/tech-intelligence/cloudflare/state-api")
    print(
        "  npx wrangler d1 execute tech-intel-db --local --command \""
        f"DELETE FROM briefing_runs WHERE id IN ('{briefing_ids[0]}','{briefing_ids[1]}'); "
        f"DELETE FROM articles WHERE id IN ('{article_ids[0]}','{article_ids[1]}'); "
        f"DELETE FROM daily_runs WHERE id = '{run_id}';"
        "\""
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, StateAPIError, OSError, ValueError) as exc:
        print(f"TEST FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
