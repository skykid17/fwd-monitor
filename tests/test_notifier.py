"""Tests for notifier module."""

from unittest.mock import patch, MagicMock

from scripts.notifier import send_new_or_updated, send_removal, send_error_alert


@patch("scripts.notifier.requests.post")
def test_send_new_promotion(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "25% off Travel Insurance",
        "discount": "25%",
        "expiry": "2026-12-31",
        "description": "Limited time offer on travel plans",
        "link": "https://www.fwd.com.sg/travel-insurance/",
    }
    send_new_or_updated("fake_token", "12345", promo, tag="NEW")

    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert payload["parse_mode"] == "HTML"
    assert "[NEW]" in payload["text"]
    assert "25% off Travel Insurance" in payload["text"]


@patch("scripts.notifier.requests.post")
def test_send_updated_promotion(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "Travel Deal",
        "discount": "30%",
        "expiry": "",
        "description": "Now with more coverage",
        "link": "https://www.fwd.com.sg/travel-insurance/",
    }
    send_new_or_updated("fake_token", "12345", promo, tag="UPDATED")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert "[UPDATED]" in payload["text"]


@patch("scripts.notifier.requests.post")
def test_send_removal(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "Old Deal",
        "notified_at": "2026-01-01T00:00:00",
        "last_seen": "2026-03-01T00:00:00",
    }
    send_removal("fake_token", "12345", promo)

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert "Removed" in payload["text"]
    assert "Old Deal" in payload["text"]
    assert payload["parse_mode"] == "HTML"


@patch("scripts.notifier.requests.post")
def test_send_error_alert(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    send_error_alert("fake_token", "12345", "Scraper failed: timeout")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert "Error" in payload["text"]
    assert "Scraper failed: timeout" in payload["text"]


@patch("scripts.notifier.requests.post")
def test_description_truncated_at_120(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "Long Description Deal",
        "discount": "10%",
        "expiry": "",
        "description": "A" * 200,
        "link": "https://www.fwd.com.sg/",
    }
    send_new_or_updated("fake_token", "12345", promo, tag="NEW")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    # The truncated description should be 117 chars + "..."
    assert "A" * 117 + "..." in payload["text"]


@patch("scripts.notifier.requests.post")
def test_missing_expiry_shows_not_specified(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "No Expiry Deal",
        "discount": "15%",
        "expiry": "",
        "description": "Some terms",
        "link": "https://www.fwd.com.sg/",
    }
    send_new_or_updated("fake_token", "12345", promo, tag="NEW")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert "Not specified" in payload["text"]


@patch("scripts.notifier.requests.post")
def test_promo_code_included_when_present(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "Promo Deal",
        "discount": "40%",
        "expiry": "2026-12-31",
        "description": "Use code to redeem",
        "promo_code": "TRAVEL40",
        "link": "https://www.fwd.com.sg/",
    }
    send_new_or_updated("fake_token", "12345", promo, tag="NEW")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert "TRAVEL40" in payload["text"]
    assert "Promo code" in payload["text"]


@patch("scripts.notifier.requests.post")
def test_promo_code_omitted_when_absent(mock_post):
    mock_post.return_value = MagicMock(status_code=200)
    mock_post.return_value.raise_for_status = MagicMock()

    promo = {
        "title": "No Code Deal",
        "discount": "20%",
        "expiry": "",
        "description": "No code needed",
        "link": "https://www.fwd.com.sg/",
    }
    send_new_or_updated("fake_token", "12345", promo, tag="NEW")

    payload = mock_post.call_args.kwargs.get("json") or mock_post.call_args[1].get("json")
    assert "Promo code" not in payload["text"]
