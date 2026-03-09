# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FWD Travel Insurance Promotion Monitor — a Python automation that scrapes FWD Singapore's promotions page every 4 hours via GitHub Actions, detects new/changed/removed Travel Insurance deals using fuzzy matching, and sends structured Telegram notifications. State is persisted in a private GitHub Gist.

## Architecture

Linear pipeline executed by `scripts/monitor.py` (orchestrator):

```
GitHub Actions cron ─→ scraper.py (Playwright/Chromium)
                        ─→ comparator.py (thefuzz token_sort_ratio)
                        ─→ notifier.py (Telegram Bot API, HTML parse_mode)
                        ─→ state_store.py (GitHub Gist JSON read/write)
```

- **scraper.py** — Playwright headless Chromium; JS-rendered page at `https://www.fwd.com.sg/insurance-promotions/`. Retries 3x with exponential back-off, 60s timeout per attempt.
- **comparator.py** — Promotion ID = MD5 of normalised title. Change detection via `thefuzz.fuzz.token_sort_ratio` with configurable `FUZZY_THRESHOLD` (default 90). Score >= threshold means identical; below means UPDATED.
- **notifier.py** — Telegram `sendMessage` with `parse_mode=HTML`. Do NOT use MarkdownV2 (escaping issues with promotion text). Three message types: new/updated, removed, error alert.
- **state_store.py** — Private GitHub Gist holding `seen_promotions.json`. Atomic read-modify-write via Gist REST API. Never update state on scraper failure.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt
playwright install --with-deps chromium

# Run the monitor locally (requires env vars)
TELEGRAM_BOT_TOKEN=xxx TELEGRAM_CHAT_ID=xxx GIST_PAT=xxx GIST_ID=xxx python scripts/monitor.py

# Run all tests
python -m pytest tests/

# Run a single test file
python -m pytest tests/test_comparator.py

# Run a single test
python -m pytest tests/test_comparator.py::test_trivial_change_no_notification
```

## Key Technical Decisions

- **Playwright over requests/BeautifulSoup alone**: FWD page is client-side JS rendered; raw HTTP returns no promotion cards.
- **thefuzz token_sort_ratio over simple ratio**: insensitive to word-order changes (e.g. "Up to 30% off travel" vs "Travel - up to 30% off").
- **HTML parse_mode over MarkdownV2**: avoids mandatory escaping of `.`, `-`, `(`, `)`, `!` that appear in promotion text.
- **GitHub Gist over database**: zero additional accounts/services, negligible data volume, free.
- **Zero results = potential DOM break**: if scraper returns 0 promotions, do NOT update state store — send error alert instead.

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Yes | From @BotFather |
| `TELEGRAM_CHAT_ID` | Yes | Single user's chat ID |
| `GIST_PAT` | Yes | GitHub PAT with `gist` scope only |
| `GIST_ID` | Yes | Private Gist ID for state store |
| `FUZZY_THRESHOLD` | No | Integer 0-100, default 90 |

## Constraints

- All infrastructure must remain within free tiers (GitHub Actions, Gist, Telegram).
- Respect `robots.txt`; minimum 2-second delay between page requests.
- Python 3.11 on `ubuntu-latest` runner.
- Single-user Telegram delivery only — no groups/channels.
- Travel Insurance promotions only — do not scrape other FWD product lines.
