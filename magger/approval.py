"""Two-stage editorial review for Magger."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml

from magger.cli import _load_state, _rss_summary
from magger.feeds import article_id, canonical_url, fetch_recent
from magger.magazine import build_epub
from magger.delivery import send_to_kindle


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        value = yaml.safe_load(f) or {}
    if not isinstance(value, dict):
        raise ValueError(f"Expected YAML mapping: {path}")
    return value


def report(text):
    print(text)
    target = os.environ.get("GITHUB_STEP_SUMMARY")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def review(args):
    settings = load_yaml(args.editorial).get("magazine", {})
    state = _load_state(Path(args.state))["seen"]
    candidates = [
        a for a in fetch_recent(load_yaml(args.feeds).get("feeds", []), int(settings.get("lookback_days", 7)))
        if a["id"] not in state
    ][:int(settings.get("max_articles", 12))]
    for article in candidates:
        article["synopsis"] = _rss_summary(
            article.get("description", ""), article["title"], int(settings.get("summary_max_words", 100))
        )
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "settings": settings, "candidates": candidates}
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Magger — editorial approval", "",
        "Found **%d** unseen RSS candidates in the last **%s days**." % (len(candidates), settings.get("lookback_days", 7)),
        "",
        "Nothing is sent automatically. In a separate **Publish approved edition** run, enter candidate numbers in the include input (comma-separated, e.g. 1,3,4) and/or paste URLs into extra_urls (one per line).", ""
    ]
    for i, article in enumerate(candidates, 1):
        lines += [
            f"## {i}. {article['title']}", f"- **Source:** {article.get('feed', 'RSS')}",
            f"- **Date:** {article.get('published', '')[:10]}", f"- **Link:** {article['url']}",
            f"- **RSS synopsis:** {article['synopsis']}", ""
        ]
    if not candidates:
        lines += ["No new RSS candidates. You can still add manual URLs when publishing."]
    report("\n".join(lines))
    return 0


class MetaParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_title = False
        self.title = []
        self.meta = {}

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "title":
            self.in_title = True
        if tag.lower() == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta.setdefault(key, attrs["content"])

    def handle_endtag(self, tag):
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title and data.strip():
            self.title.append(data.strip())


class ArticleParser(MetaParser):
    """Extract semantic article HTML, dropping page chrome and unsafe markup."""

    SKIP = {"script", "style", "nav", "footer", "header", "aside", "form", "noscript", "svg", "iframe", "button"}
    ALLOWED = {
        "p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "blockquote",
        "pre", "code", "strong", "b", "em", "i", "u", "s", "del", "ins", "a", "br",
        "hr", "figure", "figcaption", "img", "dl", "dt", "dd", "table", "thead",
        "tbody", "tfoot", "tr", "th", "td", "sub", "sup", "small",
    }
    VOID = {"br", "hr", "img"}
    BLOCKS = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "pre", "figcaption", "dt", "dd", "tr"}

    def __init__(self, base_url=""):
        super().__init__()
        self.base_url = base_url
        self.stack = []
        self.main_depth = 0
        self.all_html = []
        self.main_html = []
        self.paragraph = []
        self.paragraphs = []
        self.main_paragraphs = []
        self.in_paragraph = False

    def _skipping(self):
        return any(tag in self.SKIP for tag in self.stack)

    def _emit(self, value):
        if self._skipping():
            return
        self.all_html.append(value)
        if self.main_depth:
            self.main_html.append(value)

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs = dict(attrs)
        if tag not in self.VOID:
            self.stack.append(tag)
        if tag in ("main", "article"):
            self.main_depth += 1
        if tag == "title":
            self.in_title = True
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").lower()
            if key and attrs.get("content"):
                self.meta.setdefault(key, attrs["content"])
        if tag == "p":
            self.in_paragraph = True
            self.paragraph = []

        if tag not in self.ALLOWED or self._skipping():
            return
        safe_attrs = ""
        if tag == "a":
            href = urljoin(self.base_url, attrs.get("href", ""))
            if urlsplit(href).scheme in ("http", "https"):
                safe_attrs = f' href="{html.escape(href, quote=True)}"'
            if attrs.get("title"):
                safe_attrs += f' title="{html.escape(attrs["title"], quote=True)}"'
        elif tag == "img":
            raw_src = (
                attrs.get("data-src") or attrs.get("data-original") or attrs.get("data-lazy-src")
                or attrs.get("src") or ""
            )
            if not raw_src and attrs.get("srcset"):
                raw_src = attrs["srcset"].split(",", 1)[0].strip().split(" ", 1)[0]
            src = urljoin(self.base_url, raw_src)
            if urlsplit(src).scheme not in ("http", "https"):
                return
            safe_attrs = f' src="{html.escape(src, quote=True)}"'
            if attrs.get("alt"):
                safe_attrs += f' alt="{html.escape(attrs["alt"], quote=True)}"'
            if attrs.get("width", "").isdigit():
                safe_attrs += f' width="{attrs["width"]}"'
        elif tag in ("th", "td"):
            for attr in ("colspan", "rowspan"):
                if attrs.get(attr, "").isdigit():
                    safe_attrs += f' {attr}="{attrs[attr]}"'
        self._emit(f"<{tag}{safe_attrs}>")
        if tag in self.BLOCKS:
            self._emit("\n")

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag.lower() not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        if tag == "p" and self.in_paragraph:
            text = " ".join(" ".join(self.paragraph).split())
            if len(text) > 25:
                self.paragraphs.append(text)
                if self.main_depth:
                    self.main_paragraphs.append(text)
            self.paragraph = []
            self.in_paragraph = False

        was_skipping = self._skipping()
        if tag in self.ALLOWED and not was_skipping:
            self._emit(f"</{tag}>")
            if tag in self.BLOCKS:
                self._emit("\n")
        if tag in ("main", "article") and self.main_depth:
            self.main_depth -= 1
        if tag in self.stack:
            pos = len(self.stack) - 1 - self.stack[::-1].index(tag)
            del self.stack[pos:]

    def handle_data(self, data):
        if self.in_title and data.strip():
            self.title.append(data.strip())
        if self.in_paragraph and not self._skipping():
            value = data.strip()
            if value:
                self.paragraph.append(value)
        if not self._skipping() and any(tag in self.ALLOWED for tag in self.stack):
            self._emit(html.escape(data, quote=False))



def _download_article_images(content_html, page_url, max_images=12, max_bytes=5_000_000):
    """Download article images for embedding; skip unsupported, oversized, or unavailable assets."""
    found = re.findall(r'<img\b[^>]*?src=["\']([^"\']+)["\']', content_html, flags=re.I)
    embedded = {}
    total_bytes = 0
    allowed_types = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/gif": ".gif",
    }
    for raw_url in found:
        image_url = urljoin(page_url, html.unescape(raw_url.strip()))
        if image_url in embedded or len(embedded) >= max_images or urlsplit(image_url).scheme not in ("http", "https"):
            continue
        try:
            req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (compatible; Magger/0.1)"})
            with urllib.request.urlopen(req, timeout=12) as response:
                media_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if media_type not in allowed_types:
                    print(f"Skipping unsupported article image ({media_type or 'unknown type'}): {image_url}")
                    continue
                declared = response.headers.get("Content-Length")
                if declared and int(declared) > max_bytes:
                    print(f"Skipping oversized article image: {image_url}")
                    continue
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes or total_bytes + len(data) > 20_000_000:
                    print(f"Skipping oversized article image: {image_url}")
                    continue
                embedded[image_url] = {"data": data, "media_type": media_type, "extension": allowed_types[media_type]}
                total_bytes += len(data)
        except Exception as exc:
            print(f"Warning: could not embed article image {image_url}: {exc}")
    return embedded


def _reader_extract(raw_html, base_url):
    """Use Readability to isolate the article, then sanitize while retaining semantic HTML."""
    try:
        from readability import Document
        document = Document(raw_html, url=base_url)
        reader_html = document.summary(html_partial=True)
        reader_title = document.short_title().strip()
        parser = ArticleParser(base_url)
        parser.feed(reader_html)
        cleaned = "".join(parser.all_html).strip()
        visible = re.sub(r"<[^>]+>", " ", cleaned)
        visible = html.unescape(re.sub(r"\s+", " ", visible)).strip()
        paragraphs = parser.main_paragraphs or parser.paragraphs
        return reader_title, cleaned, paragraphs, len(visible)
    except Exception as exc:
        print(f"Warning: reader-mode extraction failed for {base_url}: {exc}")
        return "", "", [], 0


def _render_page_with_browser(url):
    """Render JS-heavy pages in Chromium; return the final DOM or an empty string."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page(
                    user_agent="Mozilla/5.0 (compatible; Magger/0.1; +https://github.com/xghxzxl/magger)",
                    viewport={"width": 1280, "height": 1800},
                )
                page.goto(url, wait_until="domcontentloaded", timeout=25000)
                page.wait_for_timeout(1200)
                return page.content()
            finally:
                browser.close()
    except Exception as exc:
        print(f"Warning: headless browser rendering unavailable for {url}: {exc}")
        return ""


def fetch_article_content(article):
    """Fetch article content with reader-mode extraction and a browser-rendered fallback."""
    url = article.get("url", "")
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Mozilla/5.0 (compatible; Magger/0.1; +https://github.com/xghxzxl/magger)"}
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            if "html" not in content_type and content_type:
                raise ValueError("URL did not return HTML")
            final_url = response.geturl()
            raw_html = response.read(5_000_000).decode("utf-8", errors="replace")

        reader_title, chosen_html, paragraphs, visible_length = _reader_extract(raw_html, final_url)
        if visible_length < 500:
            rendered_html = _render_page_with_browser(final_url)
            if rendered_html:
                browser_title, browser_content, browser_paragraphs, browser_length = _reader_extract(
                    rendered_html, final_url
                )
                if browser_length > visible_length:
                    reader_title, chosen_html, paragraphs, visible_length = (
                        browser_title or reader_title,
                        browser_content,
                        browser_paragraphs,
                        browser_length,
                    )

        # Retain the conservative parser as a fallback for unusual publisher markup.
        if visible_length < 100:
            parser = ArticleParser(final_url)
            parser.feed(raw_html)
            main_html = "".join(parser.main_html).strip()
            all_html = "".join(parser.all_html).strip()
            chosen_html = main_html if len(re.sub(r"<[^>]+>", "", main_html)) >= 400 else all_html
            visible_length = len(re.sub(r"<[^>]+>", "", chosen_html).strip())
            paragraphs = parser.main_paragraphs or parser.paragraphs
            reader_title = reader_title or parser.meta.get("og:title") or " ".join(parser.title)

        if chosen_html and visible_length >= 100:
            if reader_title:
                article["title"] = html.unescape(reader_title)
            article["content_html"] = chosen_html[:150_000]
            article["embedded_images"] = _download_article_images(article["content_html"], final_url)
            article["full_text"] = "\n\n".join(paragraphs)[:40000].strip()
            article["extraction_method"] = "reader-mode"
            return
    except Exception as exc:
        print(f"Warning: article text extraction failed for {url}: {exc}")
    fallback = article.get("description") or article.get("synopsis") or article.get("editorial_summary") or ""
    article["full_text"] = _rss_summary(fallback, article.get("title", "Article"), 1000)
    article["content_fallback"] = True


def manual_article(raw):
    url = canonical_url(raw.strip())
    if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
        raise ValueError("Invalid http(s) URL: " + raw)
    title = url
    description = ""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Magger/0.1"})
        with urllib.request.urlopen(req, timeout=15) as response:
            final = canonical_url(response.geturl())
            if urlsplit(final).scheme in ("http", "https"):
                url = final
            if "html" in response.headers.get("Content-Type", "").lower():
                parser = MetaParser()
                parser.feed(response.read(1_000_000).decode("utf-8", errors="replace"))
                title = (parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title) or url).strip()
                description = (parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description") or "").strip()
    except Exception as exc:
        print(f"Warning: metadata fetch failed for {url}: {exc}; using URL as title.")
    return {
        "id": article_id(url), "title": html.unescape(title), "url": url,
        "published": datetime.now(timezone.utc).isoformat(), "feed": "Manually added",
        "description": description[:12000], "synopsis": _rss_summary(description, title, 100),
        "topic": "Manually added", "rationale": "Manually supplied and explicitly approved by the editor."
    }


def publish(args):
    manifest = json.loads(Path(args.draft).read_text(encoding="utf-8"))
    settings = load_yaml(args.editorial).get("magazine", manifest.get("settings", {}))
    state_path = Path(args.state)
    state = _load_state(state_path)
    seen = state["seen"]
    candidates = manifest.get("candidates", [])
    indices = set()
    for part in args.include.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit() or not 1 <= int(part) <= len(candidates):
            raise ValueError("Invalid candidate number %r; valid range 1-%d." % (part, len(candidates)))
        indices.add(int(part))
    selected = []
    for i in sorted(indices):
        article = dict(candidates[i - 1])
        article["topic"] = article.get("feed") or "RSS"
        article["rationale"] = "Explicitly approved by the editor."
        article["editorial_summary"] = article.get("synopsis") or _rss_summary(
            article.get("description", ""), article["title"], int(settings.get("summary_max_words", 100))
        )
        selected.append(article)
    for raw in args.extra_urls.splitlines():
        raw = raw.strip()
        if raw and not raw.startswith("#"):
            article = manual_article(raw)
            if article["id"] not in {item["id"] for item in selected}:
                article["editorial_summary"] = article["synopsis"]
                selected.append(article)
    selected = [article for article in selected if article["id"] not in seen]
    if not selected:
        raise ValueError("No new articles approved. Nothing was sent.")
    output = Path(args.output or ("dist/magger-" + datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d") + ".epub"))
    for article in selected:
        fetch_article_content(article)
    build_epub(selected, settings, output)
    if args.no_email:
        report(f"Preview EPUB built with {len(selected)} approved articles; no email sent and state unchanged.")
    else:
        send_to_kindle(output)
        now = datetime.now(timezone.utc)
        for article in selected:
            seen[article["id"]] = {"url": article["url"], "published": article["published"], "checked_at": now.isoformat()}
        cutoff = now - timedelta(days=max(90, int(settings.get("lookback_days", 7)) * 12))
        state["seen"] = {
            key: value for key, value in seen.items()
            if value.get("checked_at") and datetime.fromisoformat(value["checked_at"]) >= cutoff
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        report(f"Published and delivered {len(selected)} approved articles to Kindle.")
    print(f"Wrote {output} ({output.stat().st_size} bytes).")
    return 0


def main():
    p = argparse.ArgumentParser(description="Magger editorial approval workflow")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("review")
    r.add_argument("--feeds", default="config/feeds.yml")
    r.add_argument("--editorial", default="config/editorial.yml")
    r.add_argument("--state", default="data/seen.json")
    r.add_argument("--output", default="draft/manifest.json")
    q = sub.add_parser("publish")
    q.add_argument("--draft", default="draft/manifest.json")
    q.add_argument("--include", default="")
    q.add_argument("--extra-urls", default="")
    q.add_argument("--editorial", default="config/editorial.yml")
    q.add_argument("--state", default="data/seen.json")
    q.add_argument("--output")
    q.add_argument("--no-email", action="store_true")
    args = p.parse_args()
    raise SystemExit(review(args) if args.command == "review" else publish(args))


if __name__ == "__main__":
    main()
