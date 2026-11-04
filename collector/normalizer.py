import hashlib
import html
import re

from datetime import datetime, timezone
from urllib.parse import (
    urlsplit,
    urlunsplit,
    parse_qsl,
    urlencode,
)
from email.utils import parsedate_to_datetime


TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}


def clean_text(value: str | None) -> str:
    if not value:
        return ""

    value = html.unescape(value)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize_url(url: str) -> str:
    if not url:
        raise ValueError("URL cannot be empty")

    parts = urlsplit(url.strip())

    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("Unsupported URL")

    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower()

    if parts.port:
        default_port = (
            (scheme == "http" and parts.port == 80)
            or (scheme == "https" and parts.port == 443)
        )

        netloc = hostname if default_port else f"{hostname}:{parts.port}"
    else:
        netloc = hostname

    query_items = [
        (key, value)
        for key, value in parse_qsl(
            parts.query,
            keep_blank_values=True
        )
        if not key.lower().startswith("utm_")
        and key.lower() not in TRACKING_KEYS
    ]

    query = urlencode(query_items)

    return urlunsplit((
        scheme,
        netloc,
        parts.path or "/",
        query,
        ""
    ))


def make_article_id(url: str) -> str:
    digest = hashlib.sha256(
        url.encode("utf-8")
    ).hexdigest()

    return digest[:32]


def parse_datetime(value) -> datetime | None:
    if value is None:
        return None

    try:
        if hasattr(value, "tm_year"):
            return datetime(
                value.tm_year,
                value.tm_mon,
                value.tm_mday,
                value.tm_hour,
                value.tm_min,
                value.tm_sec,
                tzinfo=timezone.utc
            )

        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(
                value,
                tz=timezone.utc
            )

        if isinstance(value, str):
            parsed = parsedate_to_datetime(value)

            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)

            return parsed.astimezone(timezone.utc)

    except (ValueError, TypeError, OverflowError):
        return None

    return None


def to_iso8601(value: datetime | None) -> str | None:
    if value is None:
        return None

    return (
        value.astimezone(timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def make_article(
    title: str,
    url: str,
    source: str,
    category: str,
    published_at: datetime | None,
    summary: str = "",
) -> dict:
    title = clean_text(title)
    url = normalize_url(url)

    if not title:
        raise ValueError("Article title cannot be empty")

    return {
        "id": make_article_id(url),
        "url": url,
        "title": title,
        "source": source,
        "category": category,
        "published_at": to_iso8601(published_at),
        "summary": clean_text(summary)[:3000],
        "score": 0.0,
        "status": "discovered",
    }
