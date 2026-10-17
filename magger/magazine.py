"""EPUB assembly with semantic article formatting and a table of contents."""
from __future__ import annotations

import html
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ebooklib import epub


STYLE = """
body { font-family: "Georgia", "Palatino Linotype", Palatino, serif; line-height: 1.55; margin: 6% 7%; widows: 2; orphans: 2; }
h1 { font-family: "Georgia", "Palatino Linotype", Palatino, serif; font-size: 1.8em; line-height: 1.12; font-weight: normal; margin: 0 0 0.55em; page-break-after: avoid; }
h2 { font-size: 1.3em; line-height: 1.2; font-weight: normal; margin: 1.55em 0 0.55em; page-break-after: avoid; }
h3, h4, h5, h6 { line-height: 1.25; margin: 1.25em 0 0.45em; page-break-after: avoid; }
p { margin: 0 0 1em; text-indent: 0; }
.article-byline { font-family: sans-serif; font-size: 0.78em; letter-spacing: 0.035em; margin: 0 0 1.8em; }
.article-body { margin-top: 1.4em; }
.article-body > p:first-child { margin-top: 0; }
.article-body img { display: block; max-width: 100%; height: auto; margin: 1.1em auto; }
.article-body figure { margin: 1.5em 0; page-break-inside: avoid; }
.article-body figcaption { font-family: sans-serif; font-size: 0.82em; line-height: 1.35; margin-top: 0.55em; text-align: center; }
.article-body blockquote { margin: 1.2em 0.8em; padding-left: 0.9em; border-left: 2px solid #888; font-style: italic; }
.article-body blockquote p { margin-bottom: 0.65em; }
.article-body ul, .article-body ol { padding-left: 1.5em; margin: 0.8em 0 1.2em; }
.article-body li { margin: 0 0 0.55em; padding-left: 0.15em; }
.article-body hr { margin: 1.6em auto; width: 25%; }
pre, code { font-family: monospace; white-space: pre-wrap; }
pre { margin: 0.8em 0; padding: 0.5em; }
img { max-width: 100%; height: auto; }
table { border-collapse: collapse; width: 100%; margin: 1.2em 0; font-size: 0.9em; }
th, td { border: 1px solid #888; padding: 0.4em; vertical-align: top; }
small { font-size: 0.85em; }
.synopsis { margin: 1.5em 0; padding: 0.8em 1em; border-top: 1px solid #888; border-bottom: 1px solid #888; }
.synopsis h2 { font-family: sans-serif; font-size: 0.75em; text-transform: uppercase; letter-spacing: 0.08em; margin: 0 0 0.5em; }
.synopsis p { margin: 0; font-size: 0.95em; }
"""


def _safe_link(url: str) -> str:
    return html.escape(url, quote=True) if urlsplit(url).scheme in ("http", "https") else ""


def build_epub(
    articles: list[dict[str, Any]],
    settings: dict[str, Any],
    output_path: str | Path,
    edition_date: datetime | None = None,
) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    edition_date = edition_date or datetime.now().astimezone()
    title = str(settings.get("title", "Magger Weekly"))
    subtitle = str(settings.get("subtitle", "A curated briefing from your feeds"))
    language = str(settings.get("language", "en"))
    book = epub.EpubBook()
    book.set_identifier(f"magger-{edition_date.date().isoformat()}")
    book.set_title(f"{title} — {edition_date.date().isoformat()}")
    book.set_language(language)
    book.add_author("Magger Editorial Desk")

    style = epub.EpubItem(uid="magger-style", file_name="style/magger.css", media_type="text/css", content=STYLE)
    book.add_item(style)

    intro = epub.EpubHtml(title="Contents", file_name="intro.xhtml", lang=language)
    intro.add_item(style)
    toc_rows = []
    for i, article in enumerate(articles, 1):
        safe_url = _safe_link(str(article.get("url", "")))
        article_title = html.escape(str(article.get("title", "Untitled")))
        source = html.escape(str(article.get("feed", "Source")))
        toc_rows.append(
            f'<li><a href="article-{i}.xhtml">{article_title}</a>'
            f'<br/><small>{source}</small>'
            + (f' · <a href="{safe_url}">original</a>' if safe_url else "")
            + "</li>"
        )
    intro.content = (
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>"
        f"<p>Edition: {edition_date.date().isoformat()}</p>"
        f"<h2>In this issue</h2><ol>{''.join(toc_rows)}</ol>"
    )
    book.add_item(intro)
    spine = [intro]
    toc = [epub.Link("intro.xhtml", "Contents", "contents")]

    for i, article in enumerate(articles, 1):
        article_title_raw = str(article.get("title", "Untitled"))
        article_title = html.escape(article_title_raw)
        safe_url = _safe_link(str(article.get("url", "")))
        source = html.escape(str(article.get("feed", "RSS source")))
        published = html.escape(str(article.get("published", ""))[:10])
        summary = html.escape(str(article.get("editorial_summary", article.get("synopsis", ""))))
        rationale = html.escape(str(article.get("rationale", "")))
        content_html = str(article.get("content_html") or "").strip()
        full_text = article.get("full_text") or ""
        embedded_images = article.get("embedded_images") or {}
        image_paths = {}
        for image_index, (image_url, image) in enumerate(embedded_images.items(), 1):
            extension = image.get("extension", ".jpg")
            file_name = f"images/article-{i}-image-{image_index}{extension}"
            item = epub.EpubItem(
                uid=f"article-{i}-image-{image_index}",
                file_name=file_name,
                media_type=image["media_type"],
                content=image["data"],
            )
            book.add_item(item)
            image_paths[image_url] = file_name
        if image_paths:
            def replace_image_src(match):
                original = html.unescape(match.group(3))
                local_path = image_paths.get(original)
                if not local_path:
                    return match.group(0)
                quote = match.group(2)
                return f'{match.group(1)}{quote}{html.escape(local_path, quote=True)}{quote}'
            content_html = re.sub(
                r"""(<img\b[^>]*?\bsrc=)(["\'])(.*?)\2""",
                replace_image_src,
                content_html,
                flags=re.I,
            )
        body = [
            f"<h1>{article_title}</h1>",
            f'<p class="article-byline">{source} · {published}</p>',
        ]
        if summary and settings.get("include_synopsis", False):
            body.append(f'<div class="synopsis"><h2>Editor&#39;s note</h2><p>{summary}</p></div>')
        if content_html:
            body.append('<div class="article-body">' + content_html + "</div>")
        elif full_text:
            # Keep blank-line paragraph separators from plain-text fallback content.
            chunks = [part.strip() for part in str(full_text).split("\n\n") if part.strip()]
            if not chunks:
                chunks = [part.strip() for part in str(full_text).splitlines() if part.strip()]
            body.append('<div class="article-body">')
            body.extend(f"<p>{html.escape(part)}</p>" for part in chunks)
            body.append("</div>")
        else:
            body.append(
                "<p><em>The publisher's full text could not be extracted. "
                "This entry contains the available RSS synopsis rather than the complete article.</em></p>"
            )
        if article.get("content_fallback"):
            body.append("<p><em>Publisher formatting and full text were unavailable; this is the feed excerpt.</em></p>")
        if rationale and settings.get("include_editorial_note", False):
            body.append(f"<p><small>Editorial note: {rationale}</small></p>")
        if safe_url:
            body.append(f'<p><a href="{safe_url}">Open original article</a></p>')
        chapter = epub.EpubHtml(title=article_title_raw, file_name=f"article-{i}.xhtml", lang=language)
        chapter.add_item(style)
        chapter.content = "".join(body)
        book.add_item(chapter)
        spine.append(chapter)
        toc.append(epub.Link(f"article-{i}.xhtml", article_title_raw, f"article{i}"))

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    epub.write_epub(str(output), book)
    return output
