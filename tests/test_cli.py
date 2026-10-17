import json
from pathlib import Path

from magger.cli import _load_state, _rss_summary


def test_load_state_defaults_and_reads(tmp_path: Path):
    path = tmp_path / "seen.json"
    assert _load_state(path) == {"seen": {}}
    path.write_text(json.dumps({"seen": {"abc": {"url": "https://example.com"}}}), encoding="utf-8")
    assert "abc" in _load_state(path)["seen"]


def test_load_state_recovers_from_invalid_json(tmp_path: Path):
    path = tmp_path / "seen.json"
    path.write_text("{", encoding="utf-8")
    assert _load_state(path) == {"seen": {}}


def test_rss_summary_strips_markup_and_limits_words():
    assert _rss_summary("<p>Hello <b>world</b> from RSS.</p>", "Title", 3) == "Hello world from"
