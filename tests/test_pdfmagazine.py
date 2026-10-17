from magger.pdfmagazine import _article_html


def test_pdf_article_html_preserves_semantics_and_source_link():
    document = _article_html({
        "title": "A & B",
        "feed": "Example publication",
        "published": "2026-10-17T10:00:00Z",
        "url": "https://example.com/story",
        "content_html": "<h2>Section heading</h2><p>Text with <strong>emphasis</strong>.</p>",
    })
    assert "<h1>A &amp; B</h1>" in document
    assert "<h2>Section heading</h2>" in document
    assert "<strong>emphasis</strong>" in document
    assert "https://example.com/story" in document
    assert "@page { size: Letter" in document


def test_pdf_article_html_embeds_downloaded_images():
    document = _article_html({
        "title": "Story",
        "url": "https://example.com/story",
        "content_html": '<figure><img src="https://example.com/photo.jpg" alt="Photo"></figure>',
        "embedded_images": {
            "https://example.com/photo.jpg": {
                "data": b"image-bytes",
                "media_type": "image/jpeg",
                "extension": ".jpg",
            }
        },
    })
    assert "data:image/jpeg;base64,aW1hZ2UtYnl0ZXM=" in document
    assert "https://example.com/photo.jpg" not in document


def test_pdf_article_html_uses_extracted_text_when_html_missing():
    document = _article_html({
        "title": "Fallback story",
        "url": "https://example.com/story",
        "full_text": "First paragraph.\n\nSecond paragraph.",
    })
    assert "<p>First paragraph.</p>" in document
    assert "<p>Second paragraph.</p>" in document
