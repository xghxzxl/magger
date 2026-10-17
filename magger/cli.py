"""Command-line entry point for the weekly Magger pipeline."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from magger.editor import judge_articles
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


def run(args: argparse.Namespace) -> int:
    feeds_config = _load_yaml(args.feeds)
    editorial_config = _load_yaml(args.editorial)
    settings = editorial_config.get("magazine", {})
    editorial = editorial_config.get("editorial", {})
    lookback = int(settings.get("lookback_days", 7))
    state_path = Path(args.state)
    state = _load_state(state_path)
    seen = state["seen"]
    articles = fetch_recent(feeds_config.get("feeds", []), lookback)
    unseen = [article for article in articles if article["id"] not in seen]
    print(f"Fetched {len(articles)} recent articles; {len(unseen)} have not appeared in prior editions.")
    if unseen:
        judged = judge_articles(unseen, editorial, model=args.model)
    else:
        judged = []
    selected = [article for article in judged if article.get("selected")]
    selected = selected[:int(settings.get("max_articles", 12))]
    now = datetime.now(timezone.utc)
    edition = now.astimezone().strftime("%Y-%m-%d")
    output_path = Path(args.output) if args.output else Path("dist") / f"magger-{edition}.epub"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build an issue even when nothing qualifies, so the weekly run remains inspectable.
    if selected:
        build_epub(selected, settings, output_path)
    else:
        build_epub([], settings, output_path)
        print("No articles met the editorial bar this issue.")

    if not args.no_email:
        send_to_kindle(output_path)
        print("EPUB delivered to Kindle email.")
    else:
        print("Email delivery skipped (--no-email).")

    # Only mark candidates as seen after a successful run/delivery.
    # Keep a bounded history to prevent state growing forever.
    if not args.no_email:
        for article in unseen:
            seen[article["id"]] = {"url": article["url"], "published": article["published"], "checked_at": now.isoformat()}
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
    parser = argparse.ArgumentParser(description="Curate RSS feeds into a weekly Kindle-ready EPUB.")
    parser.add_argument("--feeds", default="config/feeds.yml")
    parser.add_argument("--editorial", default="config/editorial.yml")
    parser.add_argument("--state", default="data/seen.json")
    parser.add_argument("--output", default=None)
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL") or "gpt-4o-mini")
    parser.add_argument("--no-email", action="store_true", help="Build the EPUB without sending email.")
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()
