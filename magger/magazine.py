"""EPUB assembly with a table of contents and readable article text."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ebooklib import epub


def _safe_link(url: str) -> str:
    return html.escape(url, quote=True) if urlsplit(url).scheme in ("http", "https") else ""


def build_epub(articles: list[dict[str, Any]], settings: dict[str, Any], output_path: str | Path, edition_date: datetime | None = None) -> Path:
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

    intro = epub.EpubHtml(title="Contents", file_name="intro.xhtml", lang=language)
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
        paragraphs = article.get("full_text") or []
        if isinstance(paragraphs, str):
            paragraphs = [p.strip() for p in paragraphs.splitlines() if p.strip()]
        body = [
            f"<h1>{article_title}</h1>",
            f"<p><em>{source} · {published}</em></p>",
        ]
        if summary:
            body.append(f"<p><strong>Synopsis:</strong> {summary}</p>")
        if paragraphs:
            body.append("<hr/><h2>Article</h2>")
            body.extend(f"<p>{html.escape(str(p))}</p>" for p in paragraphs if str(p).strip())
        else:
            body.append(
                "<p><em>The publisher's full text could not be extracted. "
                "This entry contains the available RSS synopsis rather than the complete article.</em></p>"
            )
        if rationale:
            body.append(f"<p><small>Editorial note: {rationale}</small></p>")
        if safe_url:
            body.append(f'<p><a href="{safe_url}">Open original article</a></p>')
        chapter = epub.EpubHtml(title=article_title_raw, file_name=f"article-{i}.xhtml", lang=language)
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
