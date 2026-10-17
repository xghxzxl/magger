"""Build a fixed-layout PDF magazine from cleaned article HTML using Chromium."""
from __future__ import annotations

import base64
import html
from io import BytesIO
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pypdf import PdfReader, PdfWriter
from playwright.sync_api import sync_playwright


PRINT_CSS = """
@page { size: Letter; margin: 0.72in 0.78in 0.75in; }
* { box-sizing: border-box; }
html { color: #171717; background: #fff; }
body { margin: 0; font-family: Georgia, 'Palatino Linotype', Palatino, serif;
       font-size: 11pt; line-height: 1.58; overflow-wrap: break-word; }
h1 { font-size: 28pt; line-height: 1.12; font-weight: normal; letter-spacing: -0.025em;
     margin: 0 0 12pt; break-after: avoid; }
h2 { font-size: 18pt; line-height: 1.2; font-weight: normal; margin: 25pt 0 9pt; break-after: avoid; }
h3, h4, h5, h6 { font-size: 13pt; line-height: 1.25; margin: 20pt 0 7pt; break-after: avoid; }
p { margin: 0 0 11pt; orphans: 3; widows: 3; }
.article-meta { font: 8.5pt/1.45 Arial, sans-serif; letter-spacing: .025em;
                color: #555; border-bottom: .5pt solid #bbb; padding-bottom: 13pt; margin-bottom: 20pt; }
.article-body img { display: block; max-width: 100%; max-height: 8.5in; height: auto;
                    object-fit: contain; margin: 18pt auto; }
figure { margin: 18pt 0; break-inside: avoid; }
figcaption { font: 8.5pt/1.4 Arial, sans-serif; color: #555; text-align: center; margin-top: 6pt; }
blockquote { margin: 16pt 12pt; padding-left: 12pt; border-left: 2pt solid #aaa; font-style: italic; }
ul, ol { padding-left: 22pt; margin: 10pt 0 15pt; }
li { margin-bottom: 5pt; }
hr { border: 0; border-top: .5pt solid #aaa; margin: 24pt auto; width: 28%; }
pre, code { font-family: monospace; white-space: pre-wrap; font-size: 9pt; }
table { border-collapse: collapse; width: 100%; font-size: 9pt; margin: 15pt 0; break-inside: auto; }
tr { break-inside: avoid; }
th, td { border: .5pt solid #aaa; padding: 5pt; vertical-align: top; }
a { color: inherit; text-decoration: underline; text-decoration-color: #999; }
.cover { min-height: 8.8in; display: flex; flex-direction: column; justify-content: center; }
.kicker { font: 9pt Arial, sans-serif; text-transform: uppercase; letter-spacing: .16em; color: #555; }
.subtitle { font-size: 14pt; color: #555; margin-top: 0; }
.contents { break-before: page; }
.contents li { margin: 0 0 12pt; }
.contents .source { display: block; font: 8.5pt Arial, sans-serif; color: #666; margin-top: 3pt; }
"""


def _safe_url(value: str) -> str:
    return value if urlsplit(value).scheme in ("http", "https") else ""


def _article_html(article: dict[str, Any]) -> str:
    title = html.escape(str(article.get("title") or "Untitled"))
    source = html.escape(str(article.get("feed") or "Source"))
    published = html.escape(str(article.get("published") or "")[:10])
    url = _safe_url(str(article.get("url") or ""))
    content = str(article.get("content_html") or "").strip()
    images = article.get("embedded_images") or {}

    # Use the downloaded image bytes already fetched by Magger, avoiding broken remote
    # images and preserving the exact source image in the PDF.
    for image_url, image in images.items():
        media_type = str(image.get("media_type") or "image/jpeg")
        data = base64.b64encode(image.get("data") or b"").decode("ascii")
        if data:
            uri = f"data:{media_type};base64,{data}"
            content = re.sub(
                r'(<img\b[^>]*\bsrc=["\'])' + re.escape(image_url) + r'(["\'])',
                lambda match: match.group(1) + uri + match.group(2),
                content,
                flags=re.I,
            )
    original = f'<p><a href="{html.escape(url, quote=True)}">Open original article</a></p>' if url else ""
    if not content:
        fallback_text = str(article.get("full_text") or article.get("description") or article.get("synopsis") or "").strip()
        if fallback_text:
            body = "".join(
                f"<p>{html.escape(part.strip())}</p>"
                for part in re.split(r"\n\s*\n", fallback_text)
                if part.strip()
            )
        else:
            body = "<p><em>The full article could not be extracted. This entry contains the available RSS excerpt rather than the complete article.</em></p>"
    else:
        body = content
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{PRINT_CSS}</style></head>
<body><article><h1>{title}</h1><div class="article-meta">{source} · {published}</div>
<div class="article-body">{body}</div>{original}</article></body></html>"""


def build_pdf(
    articles: list[dict[str, Any]],
    settings: dict[str, Any],
    output_path: str | Path,
    edition_date: datetime | None = None,
) -> Path:
    """Render a title/contents page and each article separately, then stitch without rerendering."""
    if not articles:
        raise ValueError("Cannot build a PDF edition without articles.")
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    edition_date = edition_date or datetime.now().astimezone()
    title = str(settings.get("title", "Magger Weekly"))
    subtitle = str(settings.get("subtitle", "A curated briefing from your feeds"))
    temp_pdfs: list[bytes] = []

    cover_rows = []
    for index, article in enumerate(articles, 1):
        article_title = html.escape(str(article.get("title") or "Untitled"))
        source = html.escape(str(article.get("feed") or "Source"))
        cover_rows.append(
            f'<li>{article_title}'
            f'<span class="source">{source}</span></li>'
        )
    cover_html = f"""<!doctype html><html><head><meta charset="utf-8"><style>{PRINT_CSS}
    .contents h2 {{ margin-top: 24pt; }}
    </style></head><body>
    <section class="cover"><div class="kicker">Magger Weekly</div><h1>{html.escape(title)}</h1>
    <p class="subtitle">{html.escape(subtitle)}</p><p>{edition_date.date().isoformat()}</p></section>
    <section class="contents"><h2>In this issue</h2><ol>{''.join(cover_rows)}</ol></section>
    </body></html>"""

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(cover_html, wait_until="load")
            temp_pdfs.append(page.pdf(format="Letter", print_background=True, prefer_css_page_size=True,
                                      margin={"top": "0.72in", "bottom": "0.75in", "left": "0.78in", "right": "0.78in"}))
            for article in articles:
                page.set_content(_article_html(article), wait_until="load")
                page.evaluate("""async () => {
                  await Promise.all(Array.from(document.images, img =>
                    img.complete ? Promise.resolve() : new Promise(resolve => {
                      img.onload = resolve; img.onerror = resolve;
                    })));
                }""")
                temp_pdfs.append(page.pdf(
                    format="Letter", print_background=True, prefer_css_page_size=True,
                    margin={"top": "0.72in", "bottom": "0.75in", "left": "0.78in", "right": "0.78in"},
                ))
        finally:
            browser.close()

    writer = PdfWriter()
    reader = PdfReader(BytesIO(temp_pdfs[0]))
    for page in reader.pages:
        writer.add_page(page)
    writer.add_outline_item("Contents", min(1, len(reader.pages) - 1))
    page_index = len(reader.pages)
    for index, (article, pdf_bytes) in enumerate(zip(articles, temp_pdfs[1:]), 1):
        reader = PdfReader(BytesIO(pdf_bytes))
        writer.add_outline_item(str(article.get("title") or f"Article {index}"), page_index)
        for page in reader.pages:
            writer.add_page(page)
        page_index += len(reader.pages)
    with output.open("wb") as handle:
        writer.write(handle)
    return output
