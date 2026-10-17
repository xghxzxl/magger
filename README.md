# Magger

Magger turns recent RSS/Atom entries into a weekly EPUB magazine and can send it to a Kindle email address. Everything runs in GitHub Actions; no LLM or paid AI API is used.

## What it does

1. Reads feeds in `config/feeds.yml`.
2. Collects entries published within the configured lookback window, using feed metadata and excerpts only.
3. Deduplicates canonical URLs and filters articles included in previous successful editions.
4. Selects the newest unseen entries up to `max_articles`. This is date/feed-order selection, **not semantic or quality judging**.
5. Builds a navigable EPUB with the RSS excerpt (or a fallback if no excerpt exists), source/feed attribution, publication date, and source link.
6. Optionally emails the EPUB to the configured Kindle address.
7. Uploads the EPUB as a GitHub Actions artifact (30-day retention) and persists deduplication state after successful delivery.

## Configure feeds and issue settings

Edit `config/feeds.yml`:

```yaml
feeds:
  - name: Example publication
    url: https://example.com/feed.xml
```

Edit `config/editorial.yml` to configure the issue:

```yaml
magazine:
  title: Magger Weekly
  subtitle: A curated briefing from your feeds
  language: en
  max_articles: 12
  lookback_days: 7
  summary_max_words: 100
```

The summaries are shortened RSS excerpts, not AI-written summaries or claims that Magger has read the full article. Articles are chosen by publication date, so promotional posts and lower-quality entries can be included; tune your feed list to control the results.

## Set up secure Kindle delivery

In **Settings → Secrets and variables → Actions**, add these repository secrets:

| Secret | Purpose |
| --- | --- |
| `SMTP_USERNAME` | SMTP account username |
| `SMTP_PASSWORD` | SMTP password or app password |
| `KINDLE_EMAIL` | Your personal Send-to-Kindle email address |
| `KINDLE_SENDER_EMAIL` | Sender address used for outgoing email |

Optional repository variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP hostname |
| `SMTP_PORT` | `465` | SMTP SSL port |

For Gmail, use an app password if available. In your Kindle settings, confirm the correct Send-to-Kindle address and add the sender address to approved personal document senders if required.

**Never commit passwords or personal recipient addresses to tracked files.** The workflow injects secrets at runtime. No OpenAI API key is needed.

## Run it

Open **Actions → Magger Weekly → Run workflow**. The default manual run sends the EPUB. Set **Build an EPUB but skip Kindle email delivery** to true to preview without sending.

The workflow is scheduled for **Sunday at 12:00 UTC**; GitHub may delay scheduled runs during busy periods. It declares `contents: write` so the workflow can commit `data/seen.json`. If your repository's Actions settings disallow write tokens, enable the required contents write permission.

Local run (Python 3.11+):

```bash
python -m pip install -e ".[test]"
pytest -q
python -m magger --no-email
```

The command writes an EPUB under `dist/`. Use a temporary state path when experimenting:

```bash
python -m magger --state /tmp/magger-seen.json --output /tmp/magger.epub --no-email
```

## Layout

- `config/feeds.yml` — RSS/Atom sources
- `config/editorial.yml` — issue settings
- `magger/feeds.py` — parsing, date filtering, URL normalization
- `magger/magazine.py` — EPUB generation
- `magger/delivery.py` — SMTP delivery
- `magger/cli.py` — RSS-only pipeline and state
- `.github/workflows/magger.yml` — weekly/manual Actions workflow
- `tests/` — unit tests
