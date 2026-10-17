"""RSS ingestion; intentionally uses feed metadata rather than scraping publishers."""
from __future__ import annotations

import calendar
import hashlib
import time
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import feedparser


def _parse_date(entry: dict[str, Any]) -> datetime | None:
    for key in ("published", "updated", "created"):
        value = entry.get(key)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=timezone.utc)
            except (TypeError, ValueError, OverflowError):
                pass
    return None


def canonical_url(url: str) -> str:
    """Remove common tracking parameters and fragments for stable deduplication."""
    parts = urlsplit(url.strip())
    query_items = [
        item for item in parts.query.split("&")
        if item and not item.split("=", 1)[0].lower().startswith(("utm_", "fbclid", "gclid", "mc_cid", "mc_eid"))
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/") or "/", "&".join(query_items), ""))


def article_id(url: str) -> str:
    return hashlib.sha256(canonical_url(url).encode("utf-8")).hexdigest()


def fetch_recent(feeds: list[dict[str, str]], lookback_days: int, now: datetime | None = None) -> list[dict[str, Any]]:
    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=lookback_days)
    articles: dict[str, dict[str, Any]] = {}
    for feed in feeds:
        parsed = feedparser.parse(feed["url"])
        if getattr(parsed, "bozo", False) and not getattr(parsed, "entries", []):
            print(f"Warning: unable to parse feed {feed.get('name', feed['url'])}: {getattr(parsed, 'bozo_exception', 'unknown error')}")
            continue
        for entry in parsed.entries:
            link = entry.get("link")
            if not link or not urlsplit(link).scheme.startswith("http"):
                continue
            published = _parse_date(entry)
            # Undated entries are excluded: the lookback window must be meaningful.
            if published is None or published < cutoff or published > now + timedelta(hours=24):
                continue
            url = canonical_url(link)
            title = str(entry.get("title", "")).strip()
            if not title:
                continue
            content = entry.get("summary", "") or entry.get("description", "")
            if not content and entry.get("content"):
                content = entry["content"][0].get("value", "")
            articles[article_id(url)] = {
                "id": article_id(url),
                "title": title,
                "url": url,
                "published": published.isoformat(),
                "feed": feed.get("name", feed["url"]),
                "description": str(content)[:12000],
                "author": str(entry.get("author", "")).strip(),
            }
    return sorted(articles.values(), key=lambda item: item["published"], reverse=True)
