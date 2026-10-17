"""EPUB assembly with linked, attributed editorial summaries."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ebooklib import epub


def build_epub(articles: list[dict[str, Any]], settings: dict[str, Any], output_path: str | Path, edition_date: datetime | None = None) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    edition_date = edition_date or datetime.now().astimezone()
    title = str(settings.get("title", "Magger Weekly"))
    subtitle = str(settings.get("subtitle", "A curated briefing from your feeds"))
    book = epub.EpubBook()
    book.set_identifier(f"magger-{edition_date.date().isoformat()}")
    book.set_title(f"{title} — {edition_date.date().isoformat()}")
    book.set_language(str(settings.get("language", "en")))
    book.add_author("Magger Editorial Desk")

    intro = epub.EpubHtml(title="Editor's note", file_name="intro.xhtml", lang="en")
    intro.content = (
        f"<h1>{html.escape(title)}</h1><p>{html.escape(subtitle)}</p>"
        f"<p>Edition: {edition_date.date().isoformat()}</p>"
        f"<p>This issue contains {len(articles)} selected articles. Summaries are generated from RSS metadata and excerpts; "
        "they are not a substitute for the linked original reporting.</p>"
    )
    book.add_item(intro)
    spine = [intro]
    toc = [intro]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for article in articles:
        grouped.setdefault(str(article.get("topic") or "General"), []).append(article)

    for index, (topic, items) in enumerate(sorted(grouped.items()), start=1):
        chapter = epub.EpubHtml(title=topic, file_name=f"topic-{index}.xhtml", lang=str(settings.get("language", "en")))
        body = [f"<h1>{html.escape(topic)}</h1>"]
        for article in items:
            source = html.escape(str(article.get("feed", "RSS source")))
            title_text = html.escape(str(article.get("title", "Untitled")))
            url = str(article.get("url", ""))
            if urlsplit(url).scheme not in ("http", "https"):
                continue
            safe_url = html.escape(url, quote=True)
            published = html.escape(str(article.get("published", ""))[:10])
            summary = html.escape(str(article.get("editorial_summary", "")))
            rationale = html.escape(str(article.get("rationale", "")))
            body.append(
                f"<article><h2><a href=\"{safe_url}\">{title_text}</a></h2>"
                f"<p><em>{source} · {published}</em></p><p>{summary}</p>"
                f"<p><small>Editorial note: {rationale}</small></p>"
                f"<p><a href=\"{safe_url}\">Read the original source</a></p><hr/></article>"
            )
        chapter.content = "".join(body)
        book.add_item(chapter)
        spine.append(chapter)
        toc.append(chapter)

    book.toc = tuple(toc)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = spine
    epub.write_epub(str(output), book)
    return output
