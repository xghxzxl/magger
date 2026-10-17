# Magger

Magger prepares a weekly RSS/Atom reading list, lets you explicitly approve stories in GitHub Actions, then builds a Kindle-ready PDF magazine from only the approved items (EPUB remains available as an option). It runs in GitHub Actions and does not use an LLM or paid AI API.

## Editorial workflow

1. **Review run:** every Sunday at 12:00 UTC (or manually with Actions → Magger Weekly → Run workflow → mode: review) fetches recent RSS entries within the lookback window, excludes articles already delivered, and lists each candidate's title, RSS synopsis, source, date, and link in the Actions run summary. The candidate manifest is saved as a 14-day artifact. A review run never emails anything.
2. **Choose what to publish:** open the review run, copy its numeric run ID from the URL, then start another workflow run with mode: publish. Enter that ID as draft_run_id. Put the candidate numbers you want in include as a comma-separated list (for example, 1,3,4). Anything omitted is excluded. Add any non-RSS article URLs in extra_urls, one URL per line.
3. **Publish:** the workflow retrieves that exact draft artifact and builds a PDF magazine by rendering each cleaned article with Chromium and stitching the rendered PDFs together; EPUB is available by selecting output_format=epub. By default it emails a PDF to your Kindle. Choose output_format=epub if you prefer reflowable text, or select no_email for a preview; previews do not change deduplication state. After successful email delivery, selected article URLs are recorded so they do not reappear as new candidates.

**Nothing is automatically approved.** A blank include input means no RSS stories are selected; you may still provide manual URLs. If you choose no stories and provide no URLs, publishing fails safely without sending an edition. The default PDF begins with a title/contents section, then appends each article as a separately rendered PDF section. PDF pages are merged without rerendering and include article bookmarks. Select output_format=epub for the reflowable EPUB alternative. The workflow installs Chromium only for publish runs, so scheduled RSS review runs stay lightweight. At publish time Magger first extracts a reader-mode version of each selected article using Readability, preserving the publisher’s article structure, headings, paragraphs, quotations, lists, links, figures, captions, and images where available. If the initial HTML contains too little article text, a headless Chromium browser renders JavaScript-heavy pages before reader-mode extraction is retried. A conservative HTML parser remains as a fallback. Magger packages downloaded images (JPEG, PNG, and GIF) into the EPUB and applies a restrained, serif-led literary style while leaving the article content itself intact. Synopsis boxes and editorial notes are opt-in (`include_synopsis: true` and `include_editorial_note: true`); they are off by default so they do not interrupt the source article. Some sites block automated fetching, use JavaScript-only pages, or require a subscription; when extraction fails, Magger includes the available RSS excerpt and labels that limitation instead of pretending it has the full text. RSS synopses are shortened feed excerpts, not AI-generated summaries.

The draft artifact expires after 14 days. If it expires, run review again and use the new run ID.

## Configure feeds and issue settings

Edit `config/feeds.yml`:

```yaml
feeds:
  - name: Example publication
    url: https://example.com/feed.xml
```

Edit `config/editorial.yml`:

```yaml
magazine:
  title: Magger Weekly
  subtitle: A curated briefing from your feeds
  language: en
  max_articles: 12
  lookback_days: 7
  summary_max_words: 100
  # Optional: add Magger synopsis and editorial notes to article chapters.
  include_synopsis: false
  include_editorial_note: false
```

## Kindle delivery secrets

In **Settings → Secrets and variables → Actions**, configure these repository secrets:

| Secret | Purpose |
| --- | --- |
| `SMTP_USERNAME` | SMTP account username |
| `SMTP_PASSWORD` | SMTP password or app password |
| `KINDLE_EMAIL` | Your Send-to-Kindle email address |
| `KINDLE_SENDER_EMAIL` | Sender address used for outgoing email |

Optional repository variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `SMTP_HOST` | `smtp.gmail.com` | SMTP hostname |
| `SMTP_PORT` | `465` | SMTP SSL port |

For Gmail, use an app password if available. Add the sender address to your Kindle approved personal document senders if required. Never commit passwords or recipient addresses. No OpenAI API key is needed.

## Local development

```bash
python -m pip install -e ".[test]"
pytest -q
python -m magger.approval review
```

The review command writes `draft/manifest.json`. For a local preview, after reviewing candidate numbers in the generated manifest, run:

```bash
python -m magger.approval publish --draft draft/manifest.json --include 1,3 --format pdf --no-email
```

## Layout

- `config/feeds.yml` — RSS/Atom sources
- `config/editorial.yml` — magazine settings
- `magger/feeds.py` — feed parsing, date filtering, URL normalization
- `magger/approval.py` — review manifest, manual URL metadata, explicit approval
- `magger/magazine.py` — EPUB generation
- `magger/pdfmagazine.py` — Chromium PDF rendering and PDF stitching
- `magger/delivery.py` — SMTP delivery
- `.github/workflows/magger.yml` — scheduled review and manual publish workflow
- `tests/` — unit tests
