"""Command-line entry point for the weekly Magger pipeline."""
from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from magger.feeds import fetch_recent
from magger.magazine import build_epub
from magger.delivery import send_to_kindle


def _load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"seen": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) and isinstance(data.get("seen"), dict) else {"seen": {}}
    except (json.JSONDecodeError, OSError):
        print(f"Warning: state file {path} was unreadable; starting with empty history.")
        return {"seen": {}}


def _rss_summary(description: str, title: str, max_words: int) -> str:
    """Make a short, transparent excerpt-based blurb without an LLM."""
    text = re.sub(r"<[^>]+>", " ", description or "")
    text = html.unescape(re.sub(r"\s+", " ", text)).strip()
    if not text:
        text = f"No RSS excerpt was provided. Open the original source for details: {title}"
    return " ".join(text.split()[:max_words])


def run(args: argparse.Namespace) -> int:
    feeds_config = _load_yaml(args.feeds)
    config = _load_yaml(args.editorial)
    settings = config.get("magazine", {})
    lookback = int(settings.get("lookback_days", 7))
    max_articles = int(settings.get("max_articles", 12))
    summary_max_words = int(settings.get("summary_max_words", 100))
    state_path = Path(args.state)
    state = _load_state(state_path)
    seen = state["seen"]
    articles = fetch_recent(feeds_config.get("feeds", []), lookback)
    unseen = [article for article in articles if article["id"] not in seen]
    print(f"Fetched {len(articles)} recent articles; {len(unseen)} have not appeared in prior editions.")

    # RSS-only mode: newest unseen stories are included without AI scoring or summaries.
    selected = []
    for article in unseen[:max_articles]:
        selected.append({
            **article,
            "score": None,
            "selected": True,
            "topic": article.get("feed") or "RSS",
            "rationale": "Included by publication date and feed order; no LLM judging was used.",
            "editorial_summary": _rss_summary(article.get("description", ""), article["title"], summary_max_words),
        })

    now = datetime.now(timezone.utc)
    edition = now.astimezone().strftime("%Y-%m-%d")
    output_path = Path(args.output) if args.output else Path("dist") / f"magger-{edition}.epub"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    build_epub(selected, settings, output_path)
    if not selected:
        print("No new articles were available in the configured lookback window.")

    if not args.no_email:
        send_to_kindle(output_path)
        print("EPUB delivered to Kindle email.")
    else:
        print("Email delivery skipped (--no-email).")

    # Only mark candidates as seen after a successful run/delivery.
    # Mark only included articles so stories beyond max_articles can appear next run.
    if not args.no_email:
        for article in selected:
            seen[article["id"]] = {
                "url": article["url"],
                "published": article["published"],
                "checked_at": now.isoformat(),
            }
        cutoff = now - timedelta(days=max(90, lookback * 12))
        state["seen"] = {
            key: value for key, value in seen.items()
            if value.get("checked_at") and datetime.fromisoformat(value["checked_at"]) >= cutoff
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        print("Preview mode: deduplication state was not changed.")
    print(f"Wrote {output_path} ({output_path.stat().st_size} bytes).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Turn recent RSS entries into a Kindle-ready EPUB without AI judging.")
    parser.add_argument("--feeds", default="config/feeds.yml")
    parser.add_argument("--editorial", default="config/editorial.yml", help="Magazine settings (legacy filename)")
    parser.add_argument("--state", default="data/seen.json")
    parser.add_argument("--output", default=None)
    parser.add_argument("--no-email", action="store_true", help="Build the EPUB without sending email.")
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
