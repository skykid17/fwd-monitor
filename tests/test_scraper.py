"""Tests for scraper module."""

import json
from unittest.mock import patch, MagicMock

from scripts.scraper import _extract_preloaded_state, _find_travel_promotions, _parse_promotion, _parse_dom_card


def _make_preloaded_state(travel_products=None):
    """Build a minimal __PRELOADED_STATE__ structure."""
    if travel_products is None:
        travel_products = [
            {
                "product_title": "Travel",
                "product_code": "TRAVEL",
                "product_promo_image": "https://www.fwd.com.sg/wp-content/uploads/travel.webp",
                "product_promo_image_alt": "Get 25% off travel insurance",
                "promo_title": "25% off Premium",
                "promo_expiry": "31 Dec 2026",
                "promo_description": "Limited time travel deal",
                "tc_caption": "T&C Applies",
                "button": {
                    "is_visible": True,
                    "text": "Check your price",
                    "link": "/travel-insurance/#quote_builder",
                },
            }
        ]

    return {
        "pageConfig": {
            "acf_fields": [
                {"acf_fc_layout": "hero_banner"},
                {
                    "acf_fc_layout": "promotion_categories",
                    "categories": [
                        {"category_name": "All promotions", "products": []},
                        {"category_name": "Travel", "products": travel_products},
                        {"category_name": "Motor", "products": []},
                    ],
                },
            ]
        }
    }


def test_find_travel_promotions():
    state = _make_preloaded_state()
    products = _find_travel_promotions(state)
    assert len(products) == 1
    assert products[0]["product_code"] == "TRAVEL"


def test_find_travel_promotions_empty():
    state = _make_preloaded_state(travel_products=[])
    products = _find_travel_promotions(state)
    assert len(products) == 0


def test_find_travel_promotions_no_layout():
    state = {"pageConfig": {"acf_fields": []}}
    products = _find_travel_promotions(state)
    assert products == []


def test_parse_promotion_basic():
    raw = {
        "product_title": "Travel",
        "product_code": "TRAVEL",
        "promo_title": "25% off",
        "promo_expiry": "31 Dec 2026",
        "promo_description": "Great deal",
        "product_promo_image_alt": "",
        "button": {"link": "/travel-insurance/#quote_builder"},
    }
    result = _parse_promotion(raw)
    assert result["title"] == "Travel"
    assert result["discount"] == "25% off"
    assert result["expiry"] == "31 Dec 2026"
    assert result["description"] == "Great deal"
    assert result["link"] == "https://www.fwd.com.sg/travel-insurance/#quote_builder"


def test_parse_promotion_extracts_discount_from_alt():
    raw = {
        "product_title": "Travel",
        "product_code": "TRAVEL",
        "product_promo_image_alt": "Get 30% off travel insurance",
        "button": {"link": "https://www.fwd.com.sg/travel-insurance/"},
    }
    result = _parse_promotion(raw)
    assert "30% off" in result["discount"]


def test_parse_promotion_absolute_link_preserved():
    raw = {
        "product_title": "Travel",
        "button": {"link": "https://www.fwd.com.sg/travel-insurance/"},
    }
    result = _parse_promotion(raw)
    assert result["link"] == "https://www.fwd.com.sg/travel-insurance/"


def test_extract_preloaded_state_from_evaluate():
    """Test extraction via page.evaluate()."""
    state = _make_preloaded_state()
    mock_page = MagicMock()
    mock_page.evaluate.return_value = state

    result = _extract_preloaded_state(mock_page)
    assert result == state


def test_extract_preloaded_state_fallback_to_html():
    """If evaluate returns None, fall back to regex on page source."""
    state = _make_preloaded_state()
    mock_page = MagicMock()
    mock_page.evaluate.return_value = None
    mock_page.content.return_value = (
        f"<script>window.__PRELOADED_STATE__ = {json.dumps(state)};</script>"
    )

    result = _extract_preloaded_state(mock_page)
    assert result is not None
    assert "pageConfig" in result


def test_parse_promotion_extracts_promo_code_from_field():
    raw = {
        "product_title": "Travel",
        "promo_code": "TRAVEL40",
        "button": {"link": "/travel-insurance/"},
    }
    result = _parse_promotion(raw)
    assert result["promo_code"] == "TRAVEL40"


def test_parse_promotion_extracts_promo_code_from_description():
    raw = {
        "product_title": "Travel",
        "promo_description": "Use promo code MEGA2024 at checkout",
        "button": {"link": "/travel-insurance/"},
    }
    result = _parse_promotion(raw)
    assert result["promo_code"] == "MEGA2024"


def test_parse_promotion_no_promo_code():
    raw = {
        "product_title": "Travel",
        "promo_description": "No code required",
        "button": {"link": "/travel-insurance/"},
    }
    result = _parse_promotion(raw)
    assert result["promo_code"] == ""


# --- _parse_dom_card tests ---

def test_parse_dom_card_splits_discount_and_expiry():
    """'40% off Ends in1d 6h 6m' should split into separate discount and expiry."""
    lines = ["40% off Ends in1d 6h 6m", "Buy travel insurance", "Find out more"]
    card_text = "\n".join(lines)
    result = _parse_dom_card(lines, card_text, "/travel-insurance/")
    assert result is not None
    assert result["discount"] == "40% off"
    assert result["expiry"].lower().startswith("ends in")


def test_parse_dom_card_faq_returns_none():
    """Cards with no discount/expiry (FAQ entries) should return None."""
    lines = [
        'What does "Cancel For Any Reason" optional benefit cover?',
        "Trip cut short for any reason: We will pay this benefit if your trip has commenced.",
        "Find out more",
    ]
    card_text = "\n".join(lines)
    result = _parse_dom_card(lines, card_text, "/travel-insurance/faq/")
    assert result is None


def test_parse_dom_card_extracts_promo_code():
    """Promo code embedded in card text should be extracted."""
    lines = ["40% off", "Use promo code MEGA2024 at checkout", "Valid until 31 Dec 2026", "Get a quote"]
    card_text = "\n".join(lines)
    result = _parse_dom_card(lines, card_text, "/travel-insurance/")
    assert result is not None
    assert result["promo_code"] == "MEGA2024"


def test_parse_dom_card_separate_expiry_line():
    """When discount and expiry are on different lines both are captured."""
    lines = ["40% off", "Valid until 31 Dec 2026", "Great travel coverage", "Buy now"]
    card_text = "\n".join(lines)
    result = _parse_dom_card(lines, card_text, "/travel-insurance/")
    assert result is not None
    assert result["discount"] == "40% off"
    assert result["expiry"] == "Valid until 31 Dec 2026"
