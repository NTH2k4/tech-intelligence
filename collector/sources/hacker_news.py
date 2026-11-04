import httpx

from datetime import datetime, timedelta, timezone

from collector.normalizer import (
    clean_text,
    make_article,
)


BASE_URL = "https://hacker-news.firebaseio.com/v0"


def fetch_hacker_news(
    client: httpx.Client,
    limit: int = 15,
    lookback_hours: int = 36,
) -> list[dict]:

    response = client.get(
        f"{BASE_URL}/topstories.json"
    )
    response.raise_for_status()

    story_ids = response.json()

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=lookback_hours
    )

    articles = []

    for story_id in story_ids[:limit]:
        try:
            item_response = client.get(
                f"{BASE_URL}/item/{story_id}.json"
            )

            item_response.raise_for_status()

            item = item_response.json()

            if not item:
                continue

            if (
                item.get("type") != "story"
                or item.get("deleted")
                or item.get("dead")
            ):
                continue

            title = item.get("title", "")

            timestamp = item.get("time")

            if not timestamp:
                continue

            published = datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc
            )

            if published < cutoff:
                continue

            story_url = item.get("url")

            discussion_url = (
                f"https://news.ycombinator.com/item?id={story_id}"
            )

            # Ask HN and Show HN posts may not have external URLs.
            article_url = story_url or discussion_url

            article = make_article(
                title=title,
                url=article_url,
                source="Hacker News",
                category="Developer Community",
                published_at=published,
                summary=clean_text(item.get("text", "")),
            )

            article["source_id"] = "hacker_news"
            article["source_score"] = int(item.get("score", 0))
            article["discussion_url"] = discussion_url
            article["comment_count"] = int(
                item.get("descendants", 0)
            )

            articles.append(article)

        except (
            httpx.HTTPError,
            ValueError,
            TypeError,
            OSError
        ):
            # A single unavailable story must not stop collection.
            continue

    return articles
