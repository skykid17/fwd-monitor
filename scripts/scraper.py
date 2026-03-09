"""Playwright-based scraper for FWD Singapore Travel Insurance promotions."""

import json
import logging
import re
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

logger = logging.getLogger(__name__)

FWD_URL = "https://www.fwd.com.sg/insurance-promotions/"
MAX_RETRIES = 3
TIMEOUT_MS = 60_000
MIN_DELAY_S = 2

# Realistic browser UA reduces bot-detection blocks on headless requests
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)


def _extract_preloaded_state(page) -> dict | None:
    """Extract __PRELOADED_STATE__ from the page via JS evaluation."""
    try:
        state = page.evaluate("() => window.__PRELOADED_STATE__")
        if state and isinstance(state, dict):
            return state
    except Exception as exc:
        logger.debug("page.evaluate failed: %s", exc)

    # Fallback: find the script tag in raw HTML and parse the JSON manually.
    # We walk matching braces rather than using a regex, because {.*?} is
    # non-greedy and stops at the first closing brace inside nested objects.
    from bs4 import BeautifulSoup
    content = page.content()
    soup = BeautifulSoup(content, "lxml")
    for script in soup.find_all("script"):
        text = script.string or ""
        if "__PRELOADED_STATE__" not in text:
            continue
        idx = text.find("window.__PRELOADED_STATE__")
        if idx == -1:
            continue
        after_eq = text.find("=", idx)
        if after_eq == -1:
            continue
        json_start = text.find("{", after_eq)
        if json_start == -1:
            continue
        depth, i = 0, json_start
        in_string, escape = False, False
        while i < len(text):
            ch = text[i]
            if escape:
                escape = False
            elif ch == "\\" and in_string:
                escape = True
            elif ch == '"':
                in_string = not in_string
            elif not in_string:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[json_start:i + 1])
                        except json.JSONDecodeError as exc:
                            logger.debug("JSON parse failed: %s", exc)
                        break
            i += 1
    return None


def _find_travel_promotions(state: dict) -> list[dict]:
    """Navigate the __PRELOADED_STATE__ structure to find Travel promotions."""
    acf_fields = state.get("pageConfig", {}).get("acf_fields", [])

    promo_layout = None
    for field in acf_fields:
        if field.get("acf_fc_layout") == "promotion_categories":
            promo_layout = field
            break

    if not promo_layout:
        logger.warning("No promotion_categories layout found in __PRELOADED_STATE__")
        return []

    categories = promo_layout.get("categories", [])

    # Primary: find by category_name == "Travel"
    for cat in categories:
        if cat.get("category_name", "").strip().lower() == "travel":
            return cat.get("products", cat.get("product", []))

    # Fallback: scan all categories for product_code == "TRAVEL"
    found = []
    for cat in categories:
        for prod in cat.get("products", cat.get("product", [])):
            if prod.get("product_code") == "TRAVEL":
                found.append(prod)
    return found


def _parse_promotion(raw: dict) -> dict:
    """Convert raw __PRELOADED_STATE__ product data to our promotion schema."""
    title = raw.get("product_title", "").strip()
    button = raw.get("button", {})
    link = button.get("link", "")
    if link and not link.startswith("http"):
        link = f"https://www.fwd.com.sg{link}"

    # Field names vary across FWD CMS versions — check all known candidates
    discount = (
        raw.get("promo_title")
        or raw.get("label_text")
        or raw.get("badge_text")
        or raw.get("discount")
        or ""
    )
    expiry = (
        raw.get("promo_expiry")
        or raw.get("expiry_date")
        or raw.get("expiry")
        or ""
    )
    description = (
        raw.get("promo_description")
        or raw.get("description")
        or raw.get("tc_caption")
        or ""
    )

    # Last resort: try to pull a percentage from the promo image alt text
    if not discount:
        alt_text = raw.get("product_promo_image_alt", "")
        pct_match = re.search(r"(\d+%\s*off)", alt_text, re.IGNORECASE)
        if pct_match:
            discount = pct_match.group(1)

    logger.debug("Parsed from state: title=%r discount=%r expiry=%r", title, discount, expiry)
    return {
        "title": title,
        "discount": discount.strip(),
        "expiry": expiry.strip(),
        "description": description.strip(),
        "link": link,
    }


def _scrape_rendered_cards(page) -> list[dict]:
    """Fallback: derive promotions from the fully rendered DOM.

    Uses a single JS evaluation to locate visible CTAs outside nav/footer
    whose parent card is travel-related, walks up to the card container,
    and returns deduplicated card text + href. Robust to class-name changes.
    """
    # Click Travel tab so only Travel cards are visible.
    # Use exact-text role/filter locators to avoid matching nav "Travel Insurance" links.
    try:
        # Prefer [role="tab"] with exact name; fall back to filter on exact text.
        tab = page.get_by_role("tab", name=re.compile(r"^\s*Travel\s*$", re.IGNORECASE))
        if not tab.count():
            tab = (
                page.locator("button, li, a")
                .filter(has_text=re.compile(r"^\s*Travel\s*$", re.IGNORECASE))
                .first
            )
        else:
            tab = tab.first

        tab.wait_for(state="visible", timeout=8000)
        tab.click()
        logger.debug("Travel tab clicked")

        # Wait for the page to settle after the tab switch.
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            time.sleep(3)
    except Exception as exc:
        logger.warning("Travel tab click failed: %s", exc)

    EXTRACT_CARDS_JS = """() => {
        const CTA_TEXTS = [
            'check your price', 'get a quote', 'buy now',
            'find out more', 'learn more', 'get quote',
        ];
        const results = [];

        document.querySelectorAll('a, button').forEach(el => {
            // Normalise text: collapse whitespace, handle non-breaking spaces
            const text = (el.innerText || el.textContent || '')
                .toLowerCase().replace(/[\\u00a0\\s]+/g, ' ').trim();
            if (!CTA_TEXTS.some(cta => text.includes(cta))) return;

            // Must not be in nav/footer/header
            if (el.closest('nav, footer, header, [role="navigation"]')) return;

            // Visibility check that works in headless/CI environments.
            // checkVisibility() (Chrome 105+) handles display:none, visibility:hidden,
            // content-visibility:hidden, and opacity:0.  Fall back to offsetParent
            // for older engines.
            if (typeof el.checkVisibility === 'function') {
                if (!el.checkVisibility({ checkOpacity: false, checkVisibilityCSS: true })) return;
            } else {
                if (!el.offsetParent && el.tagName !== 'BODY') return;
            }

            // Walk up to find the enclosing card (height 100–1200px)
            let node = el.parentElement;
            let cardText = '';
            for (let i = 0; i < 12; i++) {
                if (!node || node === document.body) break;
                const r = node.getBoundingClientRect();
                if (r.height >= 100 && r.height <= 1200) {
                    cardText = node.innerText || node.textContent || '';
                    break;
                }
                node = node.parentElement;
            }
            if (!cardText) return;

            // Only keep cards that are travel-related
            const href = el.getAttribute('href') || '';
            if (!href.includes('travel') && !cardText.toLowerCase().includes('travel')) return;

            results.push({ text: cardText, href: href });
        });

        // Deduplicate by first 80 chars of text
        const seen = new Set();
        return results.filter(r => {
            const key = r.text.slice(0, 80);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }"""

    try:
        card_data = page.evaluate(EXTRACT_CARDS_JS)
    except Exception as exc:
        logger.warning("JS card extraction failed: %s", exc)
        return []

    logger.info("Found %d travel card(s) via JS extraction", len(card_data))

    promotions = []
    seen_titles: set[str] = set()

    for card in card_data:
        card_text: str = card.get("text", "")
        href: str = card.get("href", "")
        lines = [ln.strip() for ln in card_text.splitlines() if ln.strip()]

        discount = next(
            (ln for ln in lines if re.search(r"\d+%\s*off|promo\s*code", ln, re.IGNORECASE)),
            "",
        )
        expiry = next(
            (ln for ln in lines if re.search(r"ends?\s*in|valid|until|\d{1,2}\s+\w+\s+\d{4}", ln, re.IGNORECASE)),
            "",
        )

        captured = {discount, expiry}
        title = next(
            (ln for ln in lines
             if ln not in captured
             and 2 < len(ln) <= 60
             and not re.search(
                 r"\d+%|check your price|get a quote|buy now|find out more"
                 r"|t&c|terms|^\d+\s+of\s+\d+$|^travel insurance$",
                 ln, re.IGNORECASE,
             )),
            "",
        )

        captured.add(title)
        description = max(
            (ln for ln in lines if ln not in captured and len(ln) > 20),
            key=len,
            default="",
        )
        if len(description) > 120:
            description = description[:117] + "..."

        if href and not href.startswith("http"):
            href = f"https://www.fwd.com.sg{href}"

        if not title or title in seen_titles:
            continue

        seen_titles.add(title)
        promotions.append({
            "title": title,
            "discount": discount,
            "expiry": expiry,
            "description": description,
            "link": href or FWD_URL,
        })
        logger.debug("DOM card: title=%r discount=%r expiry=%r", title, discount, expiry)

    return promotions


def scrape_promotions() -> list[dict]:
    """Scrape Travel Insurance promotions from FWD Singapore. Retries up to 3x."""
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info("Scrape attempt %d/%d", attempt, MAX_RETRIES)
            promotions = _run_scrape()
            if promotions is not None:
                return promotions
        except (PlaywrightTimeout, Exception) as exc:
            last_error = exc
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < MAX_RETRIES:
                delay = MIN_DELAY_S * (2 ** (attempt - 1))
                logger.info("Retrying in %ds...", delay)
                time.sleep(delay)

    raise RuntimeError(f"Scraper failed after {MAX_RETRIES} attempts: {last_error}")


def _run_scrape() -> list[dict] | None:
    """Single scrape attempt using Playwright."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(user_agent=USER_AGENT)
            # Explicit viewport ensures getBoundingClientRect() returns real values
            # and the page doesn't render in a narrow mobile breakpoint.
            page.set_viewport_size({"width": 1280, "height": 900})
            # domcontentloaded is faster and more reliable than networkidle
            page.goto(FWD_URL, timeout=TIMEOUT_MS, wait_until="domcontentloaded")
            # Wait until __PRELOADED_STATE__ is populated by the JS framework.
            # Falls back to a fixed sleep if the function never resolves (e.g. CSP).
            try:
                page.wait_for_function(
                    "() => !!(window.__PRELOADED_STATE__ && window.__PRELOADED_STATE__.pageConfig)",
                    timeout=15_000,
                )
            except Exception:
                time.sleep(MIN_DELAY_S)

            # Strategy A: structured data from __PRELOADED_STATE__
            state = _extract_preloaded_state(page)
            if state:
                raw_products = _find_travel_promotions(state)
                if raw_products:
                    promotions = [_parse_promotion(prod) for prod in raw_products]
                    promotions = [p for p in promotions if p["title"]]
                    logger.info(
                        "Extracted %d Travel promotions from __PRELOADED_STATE__",
                        len(promotions),
                    )
                    return promotions
                logger.info("__PRELOADED_STATE__ parsed but Travel category empty; falling back to DOM")
            else:
                logger.info("__PRELOADED_STATE__ not found; falling back to DOM scraping")

            # Strategy B: parse fully rendered DOM via CTA-button anchor
            promotions = _scrape_rendered_cards(page)
            logger.info("Extracted %d Travel promotions from rendered DOM", len(promotions))
            return promotions
        finally:
            browser.close()
