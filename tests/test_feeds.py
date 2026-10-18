from datetime import datetime, timedelta, timezone
import time
from unittest.mock import patch

from magger.feeds import article_id, canonical_url, fetch_recent


def test_canonical_url_removes_tracking_and_fragment():
    assert canonical_url("HTTPS://Example.com/story/?utm_source=x&keep=yes#part") == "https://example.com/story?keep=yes"
    assert article_id("https://example.com/story?utm_campaign=a") == article_id("https://example.com/story")


def test_fetch_recent_filters_old_and_undated_entries():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    parsed = type("Feed", (), {})()
    parsed.bozo = False
    parsed.entries = [
        {"title": "Recent", "link": "https://example.com/new?utm_source=rss", "published": (now - timedelta(days=2)).strftime("%a, %d %b %Y %H:%M:%S +0000"), "summary": "excerpt"},
        {"title": "Old", "link": "https://example.com/old", "published": (now - timedelta(days=20)).strftime("%a, %d %b %Y %H:%M:%S +0000")},
        {"title": "Undated", "link": "https://example.com/undated"},
    ]
    with patch("magger.feeds.feedparser.parse", return_value=parsed):
        result = fetch_recent([{"name": "Example", "url": "https://feed.test/rss"}], 7, now=now)
    assert len(result) == 1
    assert result[0]["title"] == "Recent"
    assert result[0]["feed"] == "Example"



def test_fetch_recent_does_not_treat_old_published_story_as_new_updated_story():
    now = datetime(2026, 10, 17, tzinfo=timezone.utc)
    parsed = type("Feed", (), {})()
    parsed.bozo = False
    parsed.entries = [{
        "title": "DataJunction as Netflix’s answer to the missing piece of the modern data stack",
        "link": "https://netflixtechblog.medium.com/datajunction-example",
        # Some feeds expose a non-RFC published string but a valid parsed date.
        "published": "Feb 24, 2026",
        "published_parsed": time.strptime("2026-02-24", "%Y-%m-%d"),
        "updated": (now - timedelta(days=1)).strftime("%a, %d %b %Y %H:%M:%S +0000"),
        "updated_parsed": time.strptime((now - timedelta(days=1)).strftime("%Y-%m-%d"), "%Y-%m-%d"),
    }]
    with patch("magger.feeds.feedparser.parse", return_value=parsed):
        result = fetch_recent([{"name": "Netflix TechBlog", "url": "https://feed.test/rss"}], 7, now=now)
    assert result == []
