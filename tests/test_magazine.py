from pathlib import Path
from zipfile import ZipFile

from magger.magazine import build_epub


def test_build_epub_includes_summary_and_source_link(tmp_path: Path):
    target = tmp_path / "issue.epub"
    build_epub([{
        "title": "Useful Article", "url": "https://example.com/story", "feed": "Example Feed",
        "published": "2026-10-16T10:00:00+00:00", "topic": "Technology",
        "editorial_summary": "A concise and faithful summary.", "rationale": "Original reporting.",
    }], {"title": "Test Mag"}, target)
    assert target.is_file() and target.stat().st_size > 0
    with ZipFile(target) as archive:
        text = b"".join(archive.read(name) for name in archive.namelist() if name.endswith(".xhtml")).decode("utf-8")
    assert "Useful Article" in text
    assert "A concise and faithful summary." in text
    assert "https://example.com/story" in text

def test_build_epub_keeps_article_markup_and_adds_reading_styles(tmp_path: Path):
    target = tmp_path / "formatted.epub"
    build_epub([{
        "title": "Formatted Story", "url": "https://example.com/story", "feed": "Example Feed",
        "published": "2026-10-17", "editorial_summary": "A synopsis.",
        "content_html": (
            "<h2>Section heading</h2><p>A paragraph with <strong>bold</strong> and "
            "<em>emphasis</em>.</p><ul><li>First item</li><li>Second item</li></ul>"
        ),
    }], {"title": "Test Mag"}, target)
    with ZipFile(target) as archive:
        names = archive.namelist()
        article = next(archive.read(name).decode("utf-8") for name in names if name.endswith("article-1.xhtml"))
        css_name = next(name for name in names if name.endswith("style/magger.css"))
        css = archive.read(css_name).decode("utf-8")
    assert "<h2>Section heading</h2>" in article
    assert "<strong>bold</strong>" in article
    assert "<em>emphasis</em>" in article
    assert "<ul>" in article and "<li>First item</li>" in article
    assert "line-height" in css
    assert "max-width: 100%" in css

