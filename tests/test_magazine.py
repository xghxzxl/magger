from pathlib import Path
from zipfile import ZipFile

from magger.magazine import build_epub


def test_build_epub_preserves_source_link_without_inserting_summary(tmp_path: Path):
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
    assert "A concise and faithful summary." not in text
    assert "https://example.com/story" in text

def test_build_epub_keeps_article_markup_and_adds_reading_styles(tmp_path: Path):
    target = tmp_path / "formatted.epub"
    build_epub([{
        "title": "Formatted Story", "url": "https://example.com/story", "feed": "Example Feed",
        "published": "2026-10-17", "editorial_summary": "A synopsis.",
        "content_html": (
            "<h2>Section heading</h2><p>A paragraph with <strong>bold</strong> and "
            "<em>emphasis</em>.</p><ul><li>First item</li><li>Second item</li></ul>"
            '<figure><img src="https://example.com/images/chart.png" alt="Chart"/></figure>'
        ),
        "embedded_images": {
            "https://example.com/images/chart.png": {
                "data": b"fake-png-image-bytes",
                "media_type": "image/png",
                "extension": ".png",
            }
        },
    }], {"title": "Test Mag"}, target)
    with ZipFile(target) as archive:
        names = archive.namelist()
        article = next(archive.read(name).decode("utf-8") for name in names if name.endswith("article-1.xhtml"))
        css_name = next(name for name in names if name.endswith("style/magger.css"))
        css = archive.read(css_name).decode("utf-8")
        embedded_name = next(name for name in names if name.endswith("images/article-1-image-1.png"))
        embedded_data = archive.read(embedded_name)
    assert 'src="images/article-1-image-1.png"' in article
    assert embedded_data == b"fake-png-image-bytes"
    assert "<h2>Section heading</h2>" in article
    assert "<strong>bold</strong>" in article
    assert "<em>emphasis</em>" in article
    assert "<ul>" in article and "<li>First item</li>" in article
    assert "line-height" in css
    assert "max-width: 100%" in css



def test_article_chapter_does_not_insert_summary_or_redundant_article_heading_by_default(tmp_path: Path):
    target = tmp_path / "faithful.epub"
    build_epub([{
        "title": "Original Story Title", "url": "https://example.com/story", "feed": "Example",
        "published": "2026-10-17", "editorial_summary": "This synopsis is not part of the original article.",
        "content_html": "<h2>Original section</h2><p>The original article starts here.</p>",
    }], {"title": "Magger"}, target)
    with ZipFile(target) as archive:
        chapter = next(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith("article-1.xhtml"))
        css = next(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith("magger.css"))
    assert "<h2>Original section</h2>" in chapter
    assert "This synopsis is not part of the original article." not in chapter
    assert "<h2>Article</h2>" not in chapter
    assert 'font-family: "Georgia"' in css
    assert "line-height: 1.55" in css


def test_synopsis_can_be_enabled_explicitly(tmp_path: Path):
    target = tmp_path / "synopsis.epub"
    build_epub([{
        "title": "A Story", "url": "https://example.com/story", "feed": "Example",
        "published": "2026-10-17", "editorial_summary": "An optional editorial synopsis.",
        "content_html": "<p>The source article body.</p>",
    }], {"title": "Magger", "include_synopsis": True}, target)
    with ZipFile(target) as archive:
        chapter = next(archive.read(name).decode("utf-8") for name in archive.namelist() if name.endswith("article-1.xhtml"))
    assert "An optional editorial synopsis." in chapter
