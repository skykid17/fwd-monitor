"""Telegram Bot API notification sender (HTML parse_mode)."""

import logging
from datetime import datetime, timezone, timedelta

import requests

logger = logging.getLogger(__name__)

SGT = timezone(timedelta(hours=8))

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _send_message(bot_token: str, chat_id: str, text: str) -> None:
    """Send an HTML-formatted message via Telegram Bot API."""
    url = TELEGRAM_API.format(token=bot_token)
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()
    logger.info("Telegram message sent to chat %s", chat_id)


def send_new_or_updated(bot_token: str, chat_id: str, promotion: dict, tag: str = "NEW") -> None:
    """Send a new/updated promotion notification."""
    now = datetime.now(SGT).strftime("%Y-%m-%d %H:%M SGT")
    expiry = promotion.get("expiry") or "Not specified"
    description = promotion.get("description", "")
    if len(description) > 120:
        description = description[:117] + "..."
    link = promotion.get("link", "https://www.fwd.com.sg/insurance-promotions/")

    text = (
        f"\U0001f389 <b>FWD Travel Insurance Promotion</b> [{tag}]\n"
        f"\n"
        f"\u2022 <b>Title:</b> {promotion.get('title', 'N/A')}\n"
        f"\u2022 <b>Discount:</b> {promotion.get('discount', 'N/A')}\n"
        f"\u2022 <b>Valid until:</b> {expiry}\n"
        f"\u2022 <b>Terms:</b> {description}\n"
        f"\n"
        f"\U0001f517 <a href='{link}'>More info</a>\n"
        f"\n"
        f"<i>Checked: {now}</i>"
    )
    _send_message(bot_token, chat_id, text)


def send_removal(bot_token: str, chat_id: str, promotion: dict) -> None:
    """Send a removal notification for a promotion that disappeared."""
    notified_at = promotion.get("notified_at", "Unknown")
    last_seen = promotion.get("last_seen", "Unknown")

    text = (
        f"\U0001f5d1\ufe0f <b>FWD Travel Insurance Promotion Removed</b>\n"
        f"\n"
        f"\u2022 <b>Title:</b> {promotion.get('title', 'N/A')}\n"
        f"\u2022 <b>Originally notified:</b> {notified_at}\n"
        f"\u2022 <b>Last seen:</b> {last_seen}\n"
        f"\n"
        f"\U0001f517 <a href='https://www.fwd.com.sg/insurance-promotions/'>View promotions page</a>"
    )
    _send_message(bot_token, chat_id, text)


def send_error_alert(bot_token: str, chat_id: str, error_message: str) -> None:
    """Send an error alert when the scraper fails."""
    now = datetime.now(SGT).strftime("%Y-%m-%d %H:%M SGT")

    text = (
        f"\u26a0\ufe0f <b>FWD Monitor Error</b>\n"
        f"\n"
        f"{error_message}\n"
        f"\n"
        f"<i>{now}</i>"
    )
    _send_message(bot_token, chat_id, text)
