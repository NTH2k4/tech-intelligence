import argparse
import sys
import uuid

from datetime import datetime, timezone

from collector.main import collect_news
from intelligence.scorer import IntelligenceScorer
from integrations.state_api_client import StateAPIClient


PRESERVED_AI_FIELDS = (
    "score",
    "ai_category",
    "relevance_score",
    "impact_score",
    "novelty_score",
    "source_authority_score",
    "summary_vi",
    "why_it_matters",
    "confidence",
    "recommendation",
    "scoring_model",
    "scored_at",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def has_persisted_intelligence(article: dict) -> bool:
    """Return True only when an article has a usable prior AI evaluation."""
    return bool(
        article.get("scored_at")
        and article.get("ai_category")
        and article.get("recommendation")
        and article.get("confidence")
        and article.get("summary_vi")
    )


def article_sort_key(article: dict) -> tuple[str, int]:
    """Sort newest articles first, using HN score only as a tie-breaker."""
    return (
        article.get("published_at") or "",
        int(article.get("source_score") or 0),
    )


def select_source_balanced_articles(
    articles: list[dict],
    limit: int,
) -> list[dict]:
    """Select recent articles in round-robin order across source IDs.

    Collector output is globally sorted by publication time. A simple
    articles[:limit] can let one source (for example, a batch of arXiv
    announcements with identical timestamps) occupy the entire limit.
    This function first takes one article per source, then a second round,
    until the limit is reached. The final selected list is restored to
    newest-first order for downstream processing.
    """
    if limit <= 0 or not articles:
        return []

    grouped: dict[str, list[dict]] = {}
    for article in articles:
        source_key = (
            article.get("source_id")
            or article.get("source")
            or "unknown"
        )
        grouped.setdefault(source_key, []).append(article)

    for source_articles in grouped.values():
        source_articles.sort(key=article_sort_key, reverse=True)

    # Start each round with the sources whose newest item is most recent.
    source_order = sorted(
        grouped,
        key=lambda source_key: article_sort_key(grouped[source_key][0]),
        reverse=True,
    )

    selected: list[dict] = []
    round_index = 0

    while len(selected) < limit:
        added_this_round = False

        for source_key in source_order:
            source_articles = grouped[source_key]
            if round_index < len(source_articles):
                selected.append(source_articles[round_index])
                added_this_round = True

                if len(selected) >= limit:
                    break

        if not added_this_round:
            break

        round_index += 1

    selected.sort(key=article_sort_key, reverse=True)
    return selected


def verify_commit(
    client: StateAPIClient,
    submitted_articles: list[dict],
    previous_by_url: dict[str, dict],
) -> None:
    state = client.get_state(limit=500)
    stored_articles = state.get("articles", [])

    stored_by_url = {
        article.get("url"): article
        for article in stored_articles
    }

    missing_urls = [
        article["url"]
        for article in submitted_articles
        if article["url"] not in stored_by_url
    ]

    if missing_urls:
        raise RuntimeError(
            f"{len(missing_urls)} submitted articles were not found "
            "when reading State API"
        )

    verified_new = 0
    verified_preserved = 0

    for submitted in submitted_articles:
        url = submitted["url"]
        stored = stored_by_url[url]
        intelligence = submitted.get("intelligence")

        if intelligence:
            checks = {
                "score": submitted.get("score"),
                "ai_category": intelligence.get("category"),
                "relevance_score": intelligence.get("relevance_score"),
                "impact_score": intelligence.get("impact_score"),
                "novelty_score": intelligence.get("novelty_score"),
                "source_authority_score": intelligence.get(
                    "source_authority_score"
                ),
                "summary_vi": intelligence.get("summary_vi"),
                "why_it_matters": intelligence.get("why_it_matters"),
                "confidence": intelligence.get("confidence"),
                "recommendation": intelligence.get("recommendation")
                or submitted.get("recommendation"),
                "scoring_model": intelligence.get("scoring_model"),
                "scored_at": intelligence.get("scored_at"),
            }

            for field, expected in checks.items():
                if stored.get(field) != expected:
                    raise RuntimeError(
                        f"State verification failed for {url}: "
                        f"{field} (expected {expected!r}, "
                        f"got {stored.get(field)!r})"
                    )

            verified_new += 1
            continue

        previous = previous_by_url.get(url)

        if previous and has_persisted_intelligence(previous):
            for field in PRESERVED_AI_FIELDS:
                expected = previous.get(field)
                actual = stored.get(field)

                if actual != expected:
                    raise RuntimeError(
                        f"Existing AI evaluation was modified for {url}: "
                        f"{field} (expected {expected!r}, got {actual!r})"
                    )

            verified_preserved += 1

    print(
        f"[OK] State API verified {len(submitted_articles)} articles"
    )
    print(f"[OK] Newly scored evaluations verified: {verified_new}")
    print(f"[OK] Previously scored evaluations preserved: {verified_preserved}")


def main():
    parser = argparse.ArgumentParser(
        description="Tech Intelligence end-to-end pipeline"
    )

    parser.add_argument("--hours", type=int, default=36)
    parser.add_argument("--max-per-feed", type=int, default=8)
    parser.add_argument("--hn-limit", type=int, default=15)
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum articles to process (1-100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Collect and score without committing to State API",
    )

    args = parser.parse_args()

    if (
        args.hours < 1
        or args.max_per_feed < 1
        or not 1 <= args.hn_limit <= 30
        or not 1 <= args.limit <= 100
    ):
        parser.error("Invalid collection or processing limits")

    started_at = utc_now()

    run_id = (
        "run-"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        + "-"
        + uuid.uuid4().hex[:12]
    )

    print("========== TECH INTELLIGENCE PIPELINE ==========")
    print(f"Run ID: {run_id}")
    print(f"Lookback: {args.hours} hours")
    print(f"Article processing limit: {args.limit}")
    print()

    # 1. Collect news.
    print("[1/4] Collecting news...")

    articles, collection_summary = collect_news(
        lookback_hours=args.hours,
        max_per_feed=args.max_per_feed,
        hn_limit=args.hn_limit,
    )

    print(
        f"[OK] Collected {len(articles)} unique articles "
        f"from {collection_summary['sources_succeeded']}/"
        f"{collection_summary['sources_total']} sources"
    )

    collected_article_count = len(articles)
    articles = select_source_balanced_articles(articles, args.limit)

    selected_by_source = {}
    for article in articles:
        source_name = article.get("source") or article.get("source_id") or "unknown"
        selected_by_source[source_name] = selected_by_source.get(source_name, 0) + 1

    print(f"[INFO] Unique articles collected: {collected_article_count}")
    print(f"[INFO] Articles selected for processing: {len(articles)}")
    print(f"[INFO] Selected by source: {selected_by_source}")

    # 2. Load existing state and determine which articles need scoring.
    previous_by_url = {}
    already_scored_urls = set()

    client = None

    if not args.dry_run:
        print()
        print("[2/4] Checking existing articles in State API...")

        client = StateAPIClient()

        try:
            state = client.get_state(limit=500)
            previous_by_url = {
                item["url"]: item
                for item in state.get("articles", [])
                if item.get("url")
            }
        except Exception:
            client.close()
            raise

        for article in articles:
            existing = previous_by_url.get(article["url"])

            if existing and has_persisted_intelligence(existing):
                already_scored_urls.add(article["url"])

        articles_to_score = [
            article
            for article in articles
            if article["url"] not in already_scored_urls
        ]

        print(f"[INFO] Already scored in D1: {len(already_scored_urls)}")
        print(f"[INFO] Need new AI evaluation: {len(articles_to_score)}")

    else:
        print()
        print("[2/4] Dry-run: skipping State API lookup")

        articles_to_score = articles

    # 3. Score only new or previously unscored articles.
    print()
    print("[3/4] Scoring articles with Gemini...")

    scored_by_url = {}
    scoring_model = None
    scoring_error = None

    if articles_to_score:
        try:
            scorer = IntelligenceScorer()
            scoring_model = scorer.gemini.model

            print(f"[INFO] Scoring model: {scoring_model}")

            scored = scorer.score_articles(articles_to_score)

            if len(scored) != len(articles_to_score):
                raise RuntimeError(
                    "Scorer returned a different number of articles"
                )

            scored_by_url = {
                article["url"]: article
                for article in scored
            }

            print(
                f"[OK] Newly scored {len(scored_by_url)} articles"
            )

        except Exception as exc:
            scoring_error = type(exc).__name__

            print(
                f"[ERROR] Gemini scoring failed: {scoring_error}",
                file=sys.stderr,
            )
            print(
                "[WARNING] Unscored articles will be committed "
                "without new AI evaluation.",
                file=sys.stderr,
            )

    else:
        print("[INFO] No new AI evaluations needed.")
        print("[OK] Skipped Gemini API call.")

    # Merge scored results with raw articles.
    # Previously evaluated articles are sent without intelligence;
    # Worker preserves their existing AI fields.
    articles_to_commit = [
        scored_by_url.get(article["url"], article)
        for article in articles
    ]

    newly_scored_count = len(scored_by_url)
    preserved_count = len(already_scored_urls)

    # Determine run status.
    errors = []

    source_failures = collection_summary["sources_failed"]
    source_successes = collection_summary["sources_succeeded"]

    if source_failures:
        errors.append(
            f"{source_failures}/{collection_summary['sources_total']} "
            "collection sources failed"
        )

    if scoring_error:
        errors.append(f"Gemini scoring failed: {scoring_error}")

    if source_successes == 0:
        run_status = "failed"
        errors.append("All collection sources failed")
    elif not articles:
        run_status = "no_news"
    elif errors:
        run_status = "partial"
    else:
        run_status = "success"

    completed_at = utc_now()

    run = {
        "id": run_id,
        "started_at": started_at,
        "completed_at": completed_at,
        "status": run_status,
        "article_count": len(articles_to_commit),
        "error_message": "; ".join(errors) or None,
    }

    print()
    print("[INFO] Pipeline summary")
    print(f"Run status: {run_status}")
    print(f"Articles collected for processing: {len(articles)}")
    print(f"Newly scored: {newly_scored_count}")
    print(f"Existing AI evaluations reused: {preserved_count}")
    print(
        "AI evaluations included in this commit: "
        f"{sum(bool(a.get('intelligence')) for a in articles_to_commit)}"
    )

    if args.dry_run:
        print()
        print("[DRY RUN] No data was sent to Cloudflare D1.")
        print("Pipeline preview completed.")
        return

    # 4. Commit and verify.
    try:
        print()
        print("[4/4] Committing to Cloudflare D1...")

        result = client.commit(
            run=run,
            articles=articles_to_commit,
        )

        print(
            f"[OK] Commit completed. "
            f"Stored: {result.get('stored_articles')}, "
            f"AI-scored in this commit: {result.get('scored_articles')}"
        )

        print("[INFO] Reading data back from State API...")

        verify_commit(
            client=client,
            submitted_articles=articles_to_commit,
            previous_by_url=previous_by_url,
        )

    finally:
        client.close()

    print()
    print("========== PIPELINE COMPLETED ==========")
    print(f"Run ID: {run_id}")
    print(f"Status: {run_status}")
    print(f"Articles: {len(articles_to_commit)}")
    print(f"Newly scored: {newly_scored_count}")
    print(f"Previously scored and reused: {preserved_count}")
    print("State API commit and verification: PASSED")


if __name__ == "__main__":
    main()
