"""Fuzzy matching and change detection for promotions."""

import hashlib
import logging
import os
import re

from thefuzz import fuzz

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = int(os.environ.get("FUZZY_THRESHOLD", "90"))


def normalise_text(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def generate_promotion_id(title: str) -> str:
    """MD5 hex digest of the normalised title."""
    return hashlib.md5(normalise_text(title).encode("utf-8")).hexdigest()


def generate_content_hash(promotion: dict) -> str:
    """MD5 hash of all scraped fields concatenated."""
    parts = [
        promotion.get("title", ""),
        promotion.get("discount", ""),
        promotion.get("expiry", ""),
        promotion.get("description", ""),
        promotion.get("promo_code", ""),
        promotion.get("link", ""),
    ]
    combined = "|".join(parts)
    return hashlib.md5(combined.encode("utf-8")).hexdigest()


def compare_promotions(stored_text: str, scraped_text: str) -> int:
    """Return token_sort_ratio score (0-100) between stored and scraped text."""
    return fuzz.token_sort_ratio(stored_text, scraped_text)


def _build_comparable_text(promo: dict) -> str:
    """Build a single string from promotion fields for fuzzy comparison."""
    parts = [
        promo.get("title", ""),
        promo.get("discount", ""),
        promo.get("expiry", ""),
        promo.get("description", ""),
    ]
    return " ".join(p for p in parts if p)


def detect_changes(current_scrape: list[dict], stored_state: dict) -> tuple[list, list, list]:
    """Compare scraped promotions against stored state.

    Returns (new_promotions, updated_promotions, removed_promotions).
    Each item in new/updated is the scraped promotion dict.
    Each item in removed is the stored promotion dict.
    """
    stored_promos = {p["id"]: p for p in stored_state.get("promotions", []) if p.get("status") == "active"}
    scraped_ids = set()

    new_promotions = []
    updated_promotions = []

    for promo in current_scrape:
        promo_id = generate_promotion_id(promo["title"])
        promo["id"] = promo_id
        promo["content_hash"] = generate_content_hash(promo)
        scraped_ids.add(promo_id)

        if promo_id not in stored_promos:
            new_promotions.append(promo)
            logger.info("NEW promotion: %s", promo["title"])
        else:
            stored = stored_promos[promo_id]
            # Quick check: if content hash unchanged, skip fuzzy match
            if stored.get("content_hash") == promo["content_hash"]:
                continue

            stored_text = _build_comparable_text(stored)
            scraped_text = _build_comparable_text(promo)
            score = compare_promotions(stored_text, scraped_text)
            logger.info("Fuzzy score for '%s': %d (threshold: %d)", promo["title"], score, FUZZY_THRESHOLD)

            if score < FUZZY_THRESHOLD:
                updated_promotions.append(promo)

    # Removed: in store as active but not in current scrape
    removed_promotions = [p for pid, p in stored_promos.items() if pid not in scraped_ids]
    for p in removed_promotions:
        logger.info("REMOVED promotion: %s", p["title"])

    return new_promotions, updated_promotions, removed_promotions
