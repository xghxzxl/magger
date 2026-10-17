# Magger

Magger turns RSS feeds into a high-signal weekly magazine and sends it to a Kindle email address. The pipeline runs in GitHub Actions; configuration, editorial rules, source code, tests, and deduplication state live in this repository.

## What it does

1. Reads feeds in `config/feeds.yml`.
2. Collects RSS/Atom metadata and feed excerpts from the configured lookback window. It does not scrape full publisher pages.
3. Deduplicates canonical URLs and filters articles already processed in prior successful editions.
4. Asks an LLM to judge candidates against the written criteria in `config/editorial.yml`.
5. Builds a navigable EPUB with editorial summaries, source/feed attribution, publication dates, and a short rationale.
6. Optionally emails the EPUB to the configured Kindle address.
7. Uploads the EPUB as a GitHub Actions artifact (30-day retention) and persists deduplication state after successful delivery.

## Configure feeds and editorial policy

Edit `config/feeds.yml`:

```yaml
feeds:
  - name: Example publication
    url: https://example.com/feed.xml
```

Edit `config/editorial.yml` to tune the lookback window, issue size, summary length, topics, and selection threshold. The LLM receives the criteria as data and is instructed to judge only supplied feed metadata/excerpts, not instructions embedded in source content.

```yaml
magazine:
  title: Magger Weekly
  subtitle: A curated briefing from your feeds
  language: en
  max_articles: 12
  lookback_days: 7
  summary_max_words: 100

editorial:
  criteria:
    - Prefer original reporting and thoughtful analysis.
    - Prefer useful, novel, evidence-based ideas.
    - Penalize clickbait, duplicates, and promotional material.
  include_topics: [technology, science, culture, policy, ideas]
  exclude_topics: [gambling promotions, affiliate roundups, obvious advertisements]
  minimum_score: 6
```

## Set up secure Kindle delivery

In **Settings → Secrets and variables → Actions**, add these repository secrets:

| Secret | Purpose |
| --- | --- |
| `OPENAI_API_KEY` | API key used for editorial judging |
| `SMTP_USERNAME` | SMTP account username |
| `SMTP_PASSWORD` | SMTP password or app password |
| `KINDLE_EMAIL` | Your personal Send-to-Kindle email address |
| `KINDLE_SENDER_EMAIL` | Sender address used for outgoing email |

Optional repository variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `OPENAI_MODEL` | `gpt-4o-mini` | Editorial model |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP hostname |
| `SMTP_PORT` | `465` | SMTP SSL port |

Delivery uses SMTP over SSL. For Gmail, use an app password if available. In your Kindle settings, confirm the correct Send-to-Kindle address and add the sender address to approved personal document senders if required. Confirm current Amazon delivery limits and your mail provider's attachment limits.

**Never commit API keys, SMTP passwords, or personal recipient addresses to tracked files.** Secrets are injected into the Actions step at runtime. `data/seen.json` stores article IDs, URLs, and timestamps, not credentials.

## Run it

After configuring feeds, criteria, and secrets, open **Actions → Magger Weekly → Run workflow**. The default manual run delivers the EPUB. Set **Build an EPUB but skip Kindle email delivery** to true to preview without sending.

The workflow is scheduled for **Sunday at 12:00 UTC**; GitHub may delay scheduled runs during busy periods. It declares `contents: write` so the workflow can commit `data/seen.json`. If your repository's Actions settings disallow write tokens, enable the required contents write permission.

Local run (Python 3.11+):

```bash
python -m pip install -e ".[test]"
pytest -q
export OPENAI_API_KEY="..."
python -m magger --no-email
```

The command writes an EPUB under `dist/`. Use a temporary state path when experimenting:

```bash
python -m magger --state /tmp/magger-seen.json --output /tmp/magger.epub --no-email
```

## Design notes

- **GitHub-native orchestration:** schedule, manual dispatch, tests, artifact retention, and state persistence run in Actions.
- **Editorial transparency:** selected stories include source link, feed, publication date, summary, and rationale.
- **Metadata-only input:** summaries are based on RSS metadata and feed excerpts; Magger does not fetch or reproduce full article text. Respect publisher terms and rights.
- **Deduplication:** common tracking parameters are removed from URLs. Successful deliveries record checked articles in `data/seen.json` with bounded history.
- **LLM limitations:** summaries and scores may be wrong; follow the source for context and verify important claims.
- **Cost:** each new candidate invokes the configured model once. Keep feeds and lookback periods focused.
- **Failures:** malformed feeds are warned about and skipped. Editorial API or delivery failures fail the workflow; state is not committed.
- **Preview:** `--no-email` builds an EPUB but should not consume candidates in deduplication history.

## Layout

- `config/feeds.yml` — RSS/Atom sources
- `config/editorial.yml` — issue settings and editorial criteria
- `magger/feeds.py` — parsing, date filtering, URL normalization
- `magger/editor.py` — LLM scoring and summaries
- `magger/magazine.py` — EPUB generation
- `magger/delivery.py` — SMTP delivery
- `magger/cli.py` — pipeline and state
- `.github/workflows/magger.yml` — weekly/manual Actions workflow
- `tests/` — unit tests

## Possible next steps

Duplicate-story clustering, optional human review, per-feed weighting, feed health reporting, and additional delivery providers are natural follow-ups. The first version deliberately keeps the pipeline small and auditable.
