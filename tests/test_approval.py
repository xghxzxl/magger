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



def test_article_parser_prefers_main_content_and_ignores_navigation():
    parser = approval.ArticleParser()
    parser.feed("""
    <nav><p>Navigation junk that should never appear in article.</p></nav>
    <main><article>
      <h1>Story</h1>
      <p>This is the first substantial paragraph in the story, long enough to be retained.</p>
      <p>This is another substantial paragraph with details that belong in the article.</p>
    </article></main>
    <footer><p>Footer junk that should never appear in article.</p></footer>
    """)
    assert len(parser.main_paragraphs) == 2
    assert all("Navigation junk" not in p and "Footer junk" not in p for p in parser.main_paragraphs)


def test_epub_has_contents_list_and_full_text(tmp_path):
    from zipfile import ZipFile
    from magger.magazine import build_epub

    output = tmp_path / "magazine.epub"
    build_epub([{
        "title": "A Real Story",
        "url": "https://example.com/story",
        "published": "2026-10-17",
        "feed": "Example",
        "editorial_summary": "A short synopsis.",
        "full_text": ["First full paragraph with actual reporting.", "Second full paragraph with more details."],
    }], {"title": "Magger"}, output)
    with ZipFile(output) as archive:
        xhtml = "\n".join(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith(".xhtml"))
    assert "In this issue" in xhtml
    assert "A Real Story" in xhtml
    assert "First full paragraph with actual reporting." in xhtml
    assert "Second full paragraph with more details." in xhtml

def test_article_parser_preserves_semantic_formatting_and_links():
    parser = approval.ArticleParser("https://example.com/story")
    parser.feed("""
    <nav><p>Navigation text should be removed completely.</p></nav>
    <main><article>
      <h2>A section heading</h2>
      <p>This paragraph has <strong>bold emphasis</strong>, <em>italic text</em>,
      and <a href="/related">a related link</a> in it.</p>
      <ul><li>First item in a list</li><li>Second item in a list</li></ul>
      <blockquote><p>A quotation that should remain formatted.</p></blockquote>
      <figure><img src="/images/chart.png" alt="A chart"/><figcaption>Chart caption</figcaption></figure>
    </article></main>
    """)
    rendered = "".join(parser.main_html)
    assert re.search(r"<h2>\\s*A section heading\\s*</h2>", rendered)
    assert "<strong>bold emphasis</strong>" in rendered
    assert "<em>italic text</em>" in rendered
    assert 'href="https://example.com/related"' in rendered
    assert "<ul>" in rendered and "<li>" in rendered
    assert "<blockquote>" in rendered
    assert 'src="https://example.com/images/chart.png"' in rendered
    assert "Navigation text" not in rendered


