import feedparser
import httpx

from datetime import datetime, timedelta, timezone

from collector.normalizer import (
    clean_text,
    make_article,
    parse_datetime,
)


MAX_SUMMARY_LENGTH = 3000


def _extract_best_summary(entry: dict) -> str:
    """Choose the richest plain-text summary/content while bounding its size."""
    candidates: list[str] = []

    raw_summary = entry.get("summary")
    if isinstance(raw_summary, str):
        cleaned_summary = clean_text(raw_summary)
        if cleaned_summary:
            candidates.append(cleaned_summary)

    raw_content = entry.get("content") or []
    if isinstance(raw_content, dict):
        raw_content = [raw_content]
    elif isinstance(raw_content, str):
        raw_content = [{"value": raw_content}]

    if isinstance(raw_content, list):
        for item in raw_content:
            if not isinstance(item, dict):
                continue
            value = item.get("value")
            if not isinstance(value, str):
                continue
            cleaned_content = clean_text(value)
            if cleaned_content:
                candidates.append(cleaned_content)

    if not candidates:
        return ""

    # Prefer the longest cleaned candidate; ties preserve RSS summary priority.
    best_candidate = max(candidates, key=len)
    return best_candidate[:MAX_SUMMARY_LENGTH]


def fetch_rss_source(
    client: httpx.Client,
    source: dict,
    lookback_hours: int = 36,
) -> list[dict]:

    response = client.get(source["url"])
    response.raise_for_status()

    feed = feedparser.parse(response.content)

    if feed.bozo and not feed.entries:
        raise RuntimeError(
            f"Unable to parse RSS feed: {source['name']}"
        )

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=lookback_hours
    )

    articles = []

    for entry in feed.entries:
        title = entry.get("title", "")
        link = entry.get("link", "")

        published = parse_datetime(
            entry.get("published_parsed")
            or entry.get("updated_parsed")
        )

        # Ignore entries older than the lookback window.
        if published and published < cutoff:
            continue

        # Some feeds expose only a short description while others include a
        # richer content:encoded field. Use the best cleaned source text.
        summary = _extract_best_summary(entry)

        try:
            article = make_article(
                title=title,
                url=link,
                source=source["name"],
                category=source["category"],
                published_at=published,
                summary=summary,
            )
        except ValueError:
            continue

        article["source_id"] = source["id"]

        articles.append(article)

        if len(articles) >= source["max_items"]:
            break

    return articles
