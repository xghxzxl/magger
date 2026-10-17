import json
from argparse import Namespace
from pathlib import Path

import pytest

from magger import approval


def test_review_writes_manifest_and_exposes_synopsis(tmp_path, monkeypatch):
    monkeypatch.setattr(approval, "load_yaml", lambda path: {
        "magazine": {"lookback_days": 7, "max_articles": 12, "summary_max_words": 20}
    } if path == "config/editorial.yml" else {"feeds": []})
    monkeypatch.setattr(approval, "_load_state", lambda path: {"seen": {}})
    monkeypatch.setattr(approval, "fetch_recent", lambda feeds, days: [{
        "id": "abc", "title": "Example story", "url": "https://example.com/story",
        "published": "2026-10-16T12:00:00+00:00", "feed": "Example feed",
        "description": "<p>A short RSS synopsis.</p>"
    }])
    out = tmp_path / "draft" / "manifest.json"
    args = Namespace(editorial="config/editorial.yml", feeds="config/feeds.yml",
                     state=str(tmp_path / "seen.json"), output=str(out))
    assert approval.review(args) == 0
    data = json.loads(out.read_text())
    assert data["candidates"][0]["synopsis"] == "A short RSS synopsis."
    assert data["candidates"][0]["title"] == "Example story"


def test_publish_rejects_invalid_candidate_number_without_delivery(tmp_path, monkeypatch):
    draft = tmp_path / "manifest.json"
    draft.write_text(json.dumps({"settings": {}, "candidates": []}))
    monkeypatch.setattr(approval, "load_yaml", lambda path: {"magazine": {}})
    args = Namespace(draft=str(draft), editorial="config/editorial.yml",
                     state=str(tmp_path / "seen.json"), include="1", extra_urls="",
                     output=None, no_email=True)
    with pytest.raises(ValueError, match="Invalid candidate number"):
        approval.publish(args)


def test_manual_article_rejects_non_http_urls():
    with pytest.raises(ValueError, match="Invalid http"):
        approval.manual_article("file:///etc/passwd")
