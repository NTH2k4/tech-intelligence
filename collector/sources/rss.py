import feedparser
import httpx

from datetime import datetime, timedelta, timezone

from collector.normalizer import (
    make_article,
    parse_datetime,
)


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

        # Extract summary or content.
        summary = entry.get("summary", "")

        if not summary and entry.get("content"):
            summary = entry["content"][0].get("value", "")

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
