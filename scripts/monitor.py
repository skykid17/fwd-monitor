"""FWD Promotion Monitor — orchestrator pipeline."""

import json
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Allow `python scripts/monitor.py` to resolve sibling modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from scripts.scraper import scrape_promotions
from scripts.comparator import detect_changes, generate_promotion_id, generate_content_hash
from scripts.notifier import send_new_or_updated, send_removal, send_error_alert
from scripts.state_store import load_state, save_state

SGT = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run() -> None:
    bot_token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    gist_pat = os.environ["GIST_PAT"]
    gist_id = os.environ["GIST_ID"]

    # 1. Load state
    logger.info("Loading state from Gist %s", gist_id)
    state = load_state(gist_id, gist_pat)

    # 2. Scrape
    try:
        promotions = scrape_promotions()
    except Exception as exc:
        logger.error("Scraper failed: %s", exc)
        send_error_alert(bot_token, chat_id, f"Scraper failed: {exc}")
        sys.exit(1)

    if not promotions:
        logger.error("Scraper returned 0 promotions — possible DOM change")
        send_error_alert(
            bot_token, chat_id,
            "Scraper returned 0 Travel Insurance promotions. Possible DOM structure change. State not updated.",
        )
        sys.exit(1)

    # 3. Detect changes
    new_promos, updated_promos, removed_promos = detect_changes(promotions, state)

    now_iso = datetime.now(SGT).isoformat()
    notifications_sent = 0

    # 4. Send notifications
    for promo in new_promos:
        try:
            send_new_or_updated(bot_token, chat_id, promo, tag="NEW")
            notifications_sent += 1
        except Exception as exc:
            logger.error("Failed to send NEW notification for '%s': %s", promo["title"], exc)

    for promo in updated_promos:
        try:
            send_new_or_updated(bot_token, chat_id, promo, tag="UPDATED")
            notifications_sent += 1
        except Exception as exc:
            logger.error("Failed to send UPDATED notification for '%s': %s", promo["title"], exc)

    for promo in removed_promos:
        try:
            send_removal(bot_token, chat_id, promo)
            notifications_sent += 1
        except Exception as exc:
            logger.error("Failed to send REMOVED notification for '%s': %s", promo["title"], exc)

    # 5. Update state
    stored_by_id = {p["id"]: p for p in state.get("promotions", [])}

    # Add/update scraped promotions
    for promo in promotions:
        pid = promo.get("id") or generate_promotion_id(promo["title"])
        content_hash = promo.get("content_hash") or generate_content_hash(promo)

        if pid in stored_by_id:
            stored_by_id[pid]["content_hash"] = content_hash
            stored_by_id[pid]["last_seen"] = now_iso
            stored_by_id[pid]["status"] = "active"
            # Update fields that may have changed
            stored_by_id[pid]["title"] = promo["title"]
            stored_by_id[pid]["discount"] = promo.get("discount", "")
            stored_by_id[pid]["expiry"] = promo.get("expiry", "")
            stored_by_id[pid]["description"] = promo.get("description", "")
            stored_by_id[pid]["promo_code"] = promo.get("promo_code", "")
            stored_by_id[pid]["link"] = promo.get("link", "")
        else:
            stored_by_id[pid] = {
                "id": pid,
                "title": promo["title"],
                "discount": promo.get("discount", ""),
                "expiry": promo.get("expiry", ""),
                "description": promo.get("description", ""),
                "promo_code": promo.get("promo_code", ""),
                "link": promo.get("link", ""),
                "content_hash": content_hash,
                "notified_at": now_iso,
                "last_seen": now_iso,
                "status": "active",
            }

    # Mark removed promotions
    scraped_ids = {promo.get("id") or generate_promotion_id(promo["title"]) for promo in promotions}
    for pid, stored in stored_by_id.items():
        if pid not in scraped_ids and stored.get("status") == "active":
            stored["status"] = "removed"

    state["promotions"] = list(stored_by_id.values())

    # 6. Save state
    save_state(gist_id, gist_pat, state)

    # Structured summary log
    summary = {
        "promotions_found": len(promotions),
        "new": len(new_promos),
        "updated": len(updated_promos),
        "removed": len(removed_promos),
        "notifications_sent": notifications_sent,
    }
    logger.info("Run complete: %s", json.dumps(summary))


if __name__ == "__main__":
    run()
