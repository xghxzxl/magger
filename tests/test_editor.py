import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from magger.editor import judge_articles


def test_judge_applies_score_threshold_and_keeps_editorial_fields():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "score": 8,
            "selected": True,
            "topic": "Technology",
            "rationale": "Substantive original reporting.",
            "summary": "A concise summary.",
        })))]
    )
    client = MagicMock()
    client.chat.completions.create.return_value = response
    article = {
        "id": "abc",
        "title": "A story",
        "url": "https://example.com/story",
        "published": "2026-10-16T10:00:00+00:00",
        "feed": "Example",
        "description": "An RSS excerpt.",
        "author": "A. Writer",
    }
    with patch("magger.editor.OpenAI", return_value=client):
        result = judge_articles([article], {"minimum_score": 6, "criteria": ["Prefer original reporting"]}, api_key="test-key")
    assert len(result) == 1
    assert result[0]["selected"] is True
    assert result[0]["score"] == 8
    assert result[0]["editorial_summary"] == "A concise summary."
    assert result[0]["topic"] == "Technology"
    client.chat.completions.create.assert_called_once()


def test_judge_rejects_low_scoring_article_even_if_model_selects_it():
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "score": 3, "selected": True, "topic": "General",
            "rationale": "Too thin.", "summary": "A summary.",
        })))]
    )
    client = MagicMock()
    client.chat.completions.create.return_value = response
    article = {"id": "x", "title": "Thin", "url": "https://example.com/x", "published": "2026-10-16", "feed": "Example", "description": ""}
    with patch("magger.editor.OpenAI", return_value=client):
        result = judge_articles([article], {"minimum_score": 6}, api_key="test-key")
    assert result[0]["selected"] is False
