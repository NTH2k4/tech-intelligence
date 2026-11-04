import argparse
import json
import sys

import httpx

from pathlib import Path
from datetime import datetime, timezone

from collector.config import (
    RSS_SOURCES,
    HACKER_NEWS_CONFIG,
    DEFAULT_LOOKBACK_HOURS,
    HTTP_TIMEOUT,
    USER_AGENT,
)

from collector.sources.rss import fetch_rss_source
from collector.sources.hacker_news import fetch_hacker_news


def deduplicate(articles: list[dict]) -> list[dict]:
    unique = {}

    for article in articles:
        url = article["url"]

        if url not in unique:
            article["also_seen_in"] = []
            unique[url] = article
            continue

        existing = unique[url]

        if article["summary"] and (
            len(article["summary"]) > len(existing["summary"])
        ):
            existing["summary"] = article["summary"]

        source_name = article["source"]

        if source_name not in existing["also_seen_in"]:
            existing["also_seen_in"].append(source_name)

    return list(unique.values())


def collect_news(
    lookback_hours: int,
    max_per_feed: int,
    hn_limit: int,
) -> tuple[list[dict], dict]:

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rss+xml, application/atom+xml, "
            "application/xml, application/json, */*"
        ),
    }

    timeout = httpx.Timeout(
        HTTP_TIMEOUT,
        connect=10
    )

    all_articles = []
    source_results = {}
    successful_sources = 0  # Source request/parse completed without exception.
    sources_with_articles = 0
    sources_empty = 0

    with httpx.Client(
        headers=headers,
        timeout=timeout,
        follow_redirects=True
    ) as client:

        # RSS collection
        for source in RSS_SOURCES:
            try:
                config = {
                    **source,
                    "max_items": min(
                        source["max_items"],
                        max_per_feed
                    )
                }

                items = fetch_rss_source(
                    client,
                    config,
                    lookback_hours
                )

                all_articles.extend(items)

                source_has_articles = bool(items)
                source_results[source["id"]] = {
                    "status": "success" if source_has_articles else "empty",
                    "count": len(items),
                }

                successful_sources += 1
                if source_has_articles:
                    sources_with_articles += 1
                    print(
                        f"[OK] {source['name']}: {len(items)} articles",
                        file=sys.stderr,
                    )
                else:
                    sources_empty += 1
                    print(
                        f"[EMPTY] {source['name']}: no articles in lookback window",
                        file=sys.stderr,
                    )

            except Exception as exc:
                source_results[source["id"]] = {
                    "status": "failed",
                    "error": type(exc).__name__,
                    "detail": str(exc)[:300],
                }

                print(
                    f"[ERROR] {source['name']}: "
                    f"{type(exc).__name__}",
                    file=sys.stderr
                )

        # Hacker News collection
        try:
            items = fetch_hacker_news(
                client,
                limit=hn_limit,
                lookback_hours=lookback_hours
            )

            all_articles.extend(items)

            source_has_articles = bool(items)
            source_results["hacker_news"] = {
                "status": "success" if source_has_articles else "empty",
                "count": len(items),
            }

            successful_sources += 1
            if source_has_articles:
                sources_with_articles += 1
                print(
                    f"[OK] Hacker News: {len(items)} articles",
                    file=sys.stderr,
                )
            else:
                sources_empty += 1
                print(
                    "[EMPTY] Hacker News: no articles in lookback window",
                    file=sys.stderr,
                )

        except Exception as exc:
            source_results["hacker_news"] = {
                "status": "failed",
                "error": type(exc).__name__,
                "detail": str(exc)[:300],
            }

            print(
                f"[ERROR] Hacker News: {type(exc).__name__}",
                file=sys.stderr
            )

    articles = deduplicate(all_articles)

    articles.sort(
        key=lambda item: (
            item.get("published_at") or "",
            item.get("source_score", 0)
        ),
        reverse=True
    )

    summary = {
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat().replace("+00:00", "Z"),

        "lookback_hours": lookback_hours,
        "sources_total": len(RSS_SOURCES) + 1,
        # Backward-compatible: succeeded means the fetch/parse call completed,
        # even when a source legitimately had no new items in this time window.
        "sources_succeeded": successful_sources,
        "sources_with_articles": sources_with_articles,
        "sources_empty": sources_empty,
        "sources_failed": (
            len(RSS_SOURCES) + 1 - successful_sources
        ),
        "article_count": len(articles),
        "sources": source_results,
    }

    return articles, summary


def main():
    parser = argparse.ArgumentParser(
        description="Tech Intelligence News Collector"
    )

    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_LOOKBACK_HOURS
    )

    parser.add_argument(
        "--max-per-feed",
        type=int,
        default=8
    )

    parser.add_argument(
        "--hn-limit",
        type=int,
        default=15
    )

    parser.add_argument(
        "--output",
        default="/tmp/tech-intelligence-collector.json"
    )

    args = parser.parse_args()

    if (
        args.hours < 1
        or args.max_per_feed < 1
        or not 1 <= args.hn_limit <= 30
    ):
        parser.error("Invalid collection limits")

    print("Starting Tech Intelligence Collector...")

    articles, summary = collect_news(
        lookback_hours=args.hours,
        max_per_feed=args.max_per_feed,
        hn_limit=args.hn_limit,
    )

    if summary["sources_succeeded"] == 0:
        print("All sources failed. No output generated.")
        sys.exit(1)

    output = {
        **summary,
        "articles": articles
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output_path.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    print("\n========== COLLECTION SUMMARY ==========")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nOutput saved to: {output_path}")
    print("=========================================")


if __name__ == "__main__":
    main()
