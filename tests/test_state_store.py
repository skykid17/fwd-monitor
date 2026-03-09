"""Tests for state_store module."""

import json
from unittest.mock import patch, MagicMock

from scripts.state_store import load_state, save_state, DEFAULT_STATE, GIST_FILENAME


def _mock_gist_response(content: dict | None = None):
    """Build a mock response mimicking the GitHub Gist API."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()

    if content is None:
        # Gist exists but no seen_promotions.json file
        mock_resp.json.return_value = {"files": {}}
    else:
        mock_resp.json.return_value = {
            "files": {
                GIST_FILENAME: {
                    "content": json.dumps(content)
                }
            }
        }
    return mock_resp


@patch("scripts.state_store.requests.get")
def test_load_state_returns_stored_data(mock_get):
    state = {"promotions": [{"id": "abc", "title": "Deal", "status": "active"}]}
    mock_get.return_value = _mock_gist_response(state)

    result = load_state("gist123", "pat123")
    assert result == state
    assert len(result["promotions"]) == 1


@patch("scripts.state_store.requests.get")
def test_load_state_returns_default_when_file_missing(mock_get):
    mock_get.return_value = _mock_gist_response(None)

    result = load_state("gist123", "pat123")
    assert result == DEFAULT_STATE


@patch("scripts.state_store.requests.get")
def test_load_state_returns_default_on_empty_content(mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"files": {GIST_FILENAME: {"content": "  "}}}
    mock_get.return_value = mock_resp

    result = load_state("gist123", "pat123")
    assert result == DEFAULT_STATE


@patch("scripts.state_store.requests.patch")
def test_save_state_sends_correct_payload(mock_patch):
    mock_patch.return_value = MagicMock(status_code=200)
    mock_patch.return_value.raise_for_status = MagicMock()

    state = {"promotions": [{"id": "abc", "title": "Deal"}]}
    save_state("gist123", "pat123", state)

    mock_patch.assert_called_once()
    call_kwargs = mock_patch.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
    assert GIST_FILENAME in payload["files"]
    saved_content = json.loads(payload["files"][GIST_FILENAME]["content"])
    assert saved_content == state


@patch("scripts.state_store.requests.get")
def test_load_state_uses_auth_header(mock_get):
    mock_get.return_value = _mock_gist_response(DEFAULT_STATE)
    load_state("gist123", "my_secret_pat")

    call_kwargs = mock_get.call_args
    headers = call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers")
    assert "token my_secret_pat" in headers["Authorization"]


@patch("scripts.state_store.requests.get")
def test_load_state_raises_on_api_error(mock_get):
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = Exception("401 Unauthorized")
    mock_get.return_value = mock_resp

    try:
        load_state("gist123", "bad_pat")
        assert False, "Should have raised"
    except Exception as e:
        assert "401" in str(e)
