# TASKS.md — FWD Travel Insurance Promotion Monitor

> Derived from PRD v1.1 (9 March 2026). Tasks are ordered by dependency.

---

## Phase 1: Project Scaffolding

- [ ] **1.1** Create project directory structure:
  ```
  fwd-promo-monitor/
  ├── .github/workflows/
  ├── scripts/
  ├── tests/
  ```
- [ ] **1.2** Create `requirements.txt` with pinned dependencies:
  - `playwright`
  - `beautifulsoup4`
  - `lxml`
  - `python-telegram-bot`
  - `thefuzz`
- [ ] **1.3** Add a `.gitignore` (Python template, include `.env`, IDE files)
- [ ] **1.4** Initialise git repository

---

## Phase 2: State Store (`scripts/state_store.py`)

- [ ] **2.1** Implement `load_state(gist_id, pat)` — fetch `seen_promotions.json` from a private GitHub Gist via the REST API; return parsed JSON (or empty default if Gist is new)
- [ ] **2.2** Implement `save_state(gist_id, pat, state)` — atomic read-modify-write update of the Gist with the new JSON state
- [ ] **2.3** Define the state schema in code:
  ```json
  {
    "promotions": [
      {
        "id": "<MD5 hash>",
        "title": "...",
        "discount": "...",
        "expiry": "...",
        "link": "...",
        "content_hash": "...",
        "notified_at": "<ISO8601>",
        "last_seen": "<ISO8601>",
        "status": "active | removed"
      }
    ]
  }
  ```
- [ ] **2.4** Handle Gist API errors gracefully (auth failure, network timeout) without corrupting state
- [ ] **2.5** Write unit test `tests/test_state_store.py` — mock Gist API calls, verify load/save round-trip

---

## Phase 3: Web Scraper (`scripts/scraper.py`)

- [ ] **3.1** Implement Playwright-based scraper:
  - Launch headless Chromium
  - Navigate to `https://www.fwd.com.sg/insurance-promotions/`
  - Wait for JS-rendered promotion cards to appear in the DOM
- [ ] **3.2** Extract the following fields per Travel Insurance promotion card:
  - Title
  - Discount percentage or promo code (if present)
  - Validity / expiry date (if present)
  - Short description / terms
  - Direct link to the promotion detail page
- [ ] **3.3** Implement retry logic: up to 3 retries with exponential back-off; 60-second timeout per attempt
- [ ] **3.4** Validate scrape results: if zero promotions are returned on a page that previously had results, flag it as a potential DOM change (do NOT update state store)
- [ ] **3.5** Respect `robots.txt`; enforce minimum 2-second delay between page requests
- [ ] **3.6** Write unit test `tests/test_scraper.py` — mock Playwright page, verify field extraction and retry behaviour

---

## Phase 4: Comparator / Change Detection (`scripts/comparator.py`)

- [ ] **4.1** Implement `generate_promotion_id(title)` — normalise title (lowercase, strip punctuation, collapse whitespace), return MD5 hex digest
- [ ] **4.2** Implement `generate_content_hash(promotion)` — MD5 hash of all scraped fields concatenated; used as quick pre-check
- [ ] **4.3** Implement `compare_promotions(stored, scraped)` using `thefuzz.fuzz.token_sort_ratio`:
  - Score >= `FUZZY_THRESHOLD` (default 90): treat as identical
  - Score < `FUZZY_THRESHOLD`: treat as UPDATED
- [ ] **4.4** Implement `detect_changes(current_scrape, stored_state)` returning three lists:
  - `new_promotions` — IDs not in state store
  - `updated_promotions` — IDs in store but fuzzy score < threshold
  - `removed_promotions` — IDs in store with `status: active` but absent from current scrape
- [ ] **4.5** Make `FUZZY_THRESHOLD` configurable via environment variable (default: 90)
- [ ] **4.6** Write unit tests `tests/test_comparator.py`:
  - New promotion detected
  - Identical promotion (no notification)
  - Trivial wording change above threshold (no notification)
  - Genuine update below threshold (notification triggered)
  - Removed promotion detected

---

## Phase 5: Telegram Notifier (`scripts/notifier.py`)

- [ ] **5.1** Implement `send_new_or_updated(bot_token, chat_id, promotion, tag)` — format and send HTML message using `parse_mode=HTML`:
  ```
  🎉 <b>FWD Travel Insurance Promotion</b> [NEW | UPDATED]

  • <b>Title:</b> {title}
  • <b>Discount:</b> {discount % or promo code}
  • <b>Valid until:</b> {expiry or 'Not specified'}
  • <b>Terms:</b> {short summary, max 120 chars}

  🔗 <a href='{url}'>More info</a>

  <i>Checked: {ISO datetime SGT}</i>
  ```
- [ ] **5.2** Implement `send_removal(bot_token, chat_id, promotion)` — format and send removal notification:
  ```
  🗑️ <b>FWD Travel Insurance Promotion Removed</b>

  • <b>Title:</b> {title}
  • <b>Originally notified:</b> {notified_at}
  • <b>Last seen:</b> {last_seen}

  🔗 <a href='https://www.fwd.com.sg/insurance-promotions/'>View promotions page</a>
  ```
- [ ] **5.3** Implement `send_error_alert(bot_token, chat_id, error_message)` — alert user on scraper failure / DOM change detection
- [ ] **5.4** Handle Telegram API errors gracefully (rate limits, network errors)
- [ ] **5.5** Write unit tests `tests/test_notifier.py` — mock Telegram API, verify message HTML format and correct `parse_mode`

---

## Phase 6: Orchestrator (`scripts/monitor.py`)

- [ ] **6.1** Implement main pipeline:
  1. Load state from Gist
  2. Run scraper
  3. Detect changes (new / updated / removed)
  4. Send Telegram notifications for each change
  5. Update state store (add new, update hashes + `last_seen`, mark removed)
  6. Save state back to Gist
- [ ] **6.2** On scraper failure (zero results or exception):
  - Log the error
  - Send Telegram error alert
  - Exit with non-zero code **without** updating state store
- [ ] **6.3** Produce structured JSON logs to stdout for each run:
  - Promotions found count
  - New / updated / removed counts
  - Notifications sent count
  - Errors (if any)
- [ ] **6.4** Read configuration from environment variables:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `GIST_PAT`
  - `GIST_ID`
  - `FUZZY_THRESHOLD` (optional, default 90)

---

## Phase 7: GitHub Actions Workflow

- [ ] **7.1** Create `.github/workflows/fwd-promo-monitor.yml`:
  - Trigger: `schedule: cron '0 */4 * * *'` + `workflow_dispatch`
  - Runner: `ubuntu-latest`
  - Python: `3.11`
- [ ] **7.2** Workflow steps:
  1. Checkout repository
  2. Set up Python 3.11
  3. Cache pip dependencies
  4. Install requirements
  5. Install Playwright browsers: `playwright install --with-deps chromium`
  6. Run `python scripts/monitor.py`
  7. Upload logs as workflow artefact (retained 7 days)
- [ ] **7.3** Configure concurrency group to prevent overlapping runs (`cancel-in-progress: false`)
- [ ] **7.4** Define required secrets in workflow:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `GIST_PAT`
  - `GIST_ID`
- [ ] **7.5** Pass `FUZZY_THRESHOLD` as an env variable (default 90)

---

## Phase 8: Testing & Validation

- [ ] **8.1** Run all unit tests locally and confirm they pass
- [ ] **8.2** Manual end-to-end test: run `monitor.py` locally with real credentials and verify Telegram message receipt
- [ ] **8.3** Validate acceptance criteria:
  - **AC-1:** New promotion triggers Telegram message within 4.5 hours
  - **AC-2:** Unchanged promotion on next run produces no message
  - **AC-3:** Changed discount (fuzzy < 90%) sends `[UPDATED]` message
  - **AC-4:** Trivial punctuation change (fuzzy >= 90%) sends no message
  - **AC-5:** Removed promotion triggers removal message within 4.5 hours
  - **AC-6:** Secrets never appear in workflow logs
  - **AC-7:** Simulated scraper failure exits non-zero, state store is not corrupted
  - **AC-8:** Monthly GitHub Actions minutes < 2,000 on private repo

---

## Phase 9: Documentation & Cleanup

- [ ] **9.1** Write `README.md`:
  - Project overview
  - Setup instructions (secrets, Gist creation, bot setup)
  - How to trigger a manual run
  - Configuration options (`FUZZY_THRESHOLD`)
- [ ] **9.2** Verify `.gitignore` excludes secrets, IDE files, `__pycache__`, etc.
- [ ] **9.3** Final review: ensure no PII or secrets are committed to the repository
