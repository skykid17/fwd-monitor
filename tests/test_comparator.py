"""Tests for comparator module."""

import os
import pytest

# Set threshold before importing comparator so it picks up the env var
os.environ.setdefault("FUZZY_THRESHOLD", "90")

from scripts.comparator import (
    normalise_text,
    generate_promotion_id,
    generate_content_hash,
    compare_promotions,
    detect_changes,
)


def test_normalise_text():
    assert normalise_text("Up to 30% off!") == "up to 30 off"
    assert normalise_text("  Hello   World  ") == "hello world"


def test_generate_promotion_id_deterministic():
    id1 = generate_promotion_id("25% off Premium")
    id2 = generate_promotion_id("25% off Premium")
    assert id1 == id2


def test_generate_promotion_id_normalises():
    id1 = generate_promotion_id("25% off Premium!")
    id2 = generate_promotion_id("  25% Off Premium  ")
    assert id1 == id2


def test_generate_content_hash():
    promo = {"title": "Travel Deal", "discount": "25%", "expiry": "", "description": "Save now", "link": "/travel"}
    h = generate_content_hash(promo)
    assert isinstance(h, str) and len(h) == 32


def test_compare_identical():
    score = compare_promotions("25% off travel insurance", "25% off travel insurance")
    assert score == 100


def test_compare_word_order_insensitive():
    score = compare_promotions("Up to 30% off travel", "Travel - up to 30% off")
    assert score >= 90


def test_compare_genuine_change():
    score = compare_promotions("25% off travel insurance", "50% off travel insurance with free addon")
    assert score < 90


def test_detect_new_promotion():
    scraped = [{"title": "New Deal", "discount": "10%", "expiry": "", "description": "", "link": "/deal"}]
    state = {"promotions": []}
    new, updated, removed = detect_changes(scraped, state)
    assert len(new) == 1
    assert new[0]["title"] == "New Deal"
    assert len(updated) == 0
    assert len(removed) == 0


def test_detect_identical_no_notification():
    promo_id = generate_promotion_id("Existing Deal")
    content_hash = generate_content_hash(
        {"title": "Existing Deal", "discount": "20%", "expiry": "", "description": "terms", "link": "/link"}
    )
    scraped = [{"title": "Existing Deal", "discount": "20%", "expiry": "", "description": "terms", "link": "/link"}]
    state = {
        "promotions": [
            {
                "id": promo_id,
                "title": "Existing Deal",
                "discount": "20%",
                "expiry": "",
                "description": "terms",
                "link": "/link",
                "content_hash": content_hash,
                "status": "active",
                "notified_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:00:00",
            }
        ]
    }
    new, updated, removed = detect_changes(scraped, state)
    assert len(new) == 0
    assert len(updated) == 0
    assert len(removed) == 0


def test_trivial_change_no_notification():
    """Punctuation-only change should NOT trigger update (score >= 90)."""
    promo_id = generate_promotion_id("25% off travel insurance")
    scraped = [
        {"title": "25% off travel insurance", "discount": "25% off.", "expiry": "", "description": "terms", "link": "/link"}
    ]
    state = {
        "promotions": [
            {
                "id": promo_id,
                "title": "25% off travel insurance",
                "discount": "25% off",
                "expiry": "",
                "description": "terms",
                "link": "/link",
                "content_hash": "different_hash",
                "status": "active",
                "notified_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:00:00",
            }
        ]
    }
    new, updated, removed = detect_changes(scraped, state)
    assert len(updated) == 0


def test_genuine_update_triggers_notification():
    """Significant content change should trigger update (score < 90)."""
    promo_id = generate_promotion_id("Travel deal")
    scraped = [
        {"title": "Travel deal", "discount": "50% off + free baggage", "expiry": "2026-12-31", "description": "Brand new offer with extras", "link": "/travel"}
    ]
    state = {
        "promotions": [
            {
                "id": promo_id,
                "title": "Travel deal",
                "discount": "10%",
                "expiry": "",
                "description": "basic",
                "link": "/travel",
                "content_hash": "old_hash",
                "status": "active",
                "notified_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:00:00",
            }
        ]
    }
    new, updated, removed = detect_changes(scraped, state)
    assert len(updated) == 1


def test_detect_removed_promotion():
    promo_id = generate_promotion_id("Old Deal")
    scraped = []  # nothing scraped
    state = {
        "promotions": [
            {
                "id": promo_id,
                "title": "Old Deal",
                "discount": "",
                "expiry": "",
                "description": "",
                "link": "/old",
                "content_hash": "hash",
                "status": "active",
                "notified_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:00:00",
            }
        ]
    }
    new, updated, removed = detect_changes(scraped, state)
    assert len(removed) == 1
    assert removed[0]["title"] == "Old Deal"


def test_already_removed_not_renotified():
    """A promotion with status=removed should not appear in removed list again."""
    promo_id = generate_promotion_id("Gone Deal")
    scraped = []
    state = {
        "promotions": [
            {
                "id": promo_id,
                "title": "Gone Deal",
                "discount": "",
                "expiry": "",
                "description": "",
                "link": "/gone",
                "content_hash": "hash",
                "status": "removed",
                "notified_at": "2026-01-01T00:00:00",
                "last_seen": "2026-01-01T00:00:00",
            }
        ]
    }
    new, updated, removed = detect_changes(scraped, state)
    assert len(removed) == 0
