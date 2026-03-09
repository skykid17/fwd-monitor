"""GitHub Gist-backed state store for promotion tracking."""

import json
import logging
import requests

logger = logging.getLogger(__name__)

DEFAULT_STATE = {"promotions": []}

GIST_FILENAME = "seen_promotions.json"


def load_state(gist_id: str, pat: str) -> dict:
    """Fetch seen_promotions.json from the private Gist. Returns default empty state on first run."""
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}

    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    gist_data = resp.json()
    files = gist_data.get("files", {})

    if GIST_FILENAME not in files:
        logger.info("Gist exists but %s not found — returning default state", GIST_FILENAME)
        return json.loads(json.dumps(DEFAULT_STATE))

    content = files[GIST_FILENAME].get("content", "")
    if not content.strip():
        return json.loads(json.dumps(DEFAULT_STATE))

    return json.loads(content)


def save_state(gist_id: str, pat: str, state: dict) -> None:
    """Write state back to the Gist (atomic update)."""
    url = f"https://api.github.com/gists/{gist_id}"
    headers = {"Authorization": f"token {pat}", "Accept": "application/vnd.github+json"}

    payload = {
        "files": {
            GIST_FILENAME: {
                "content": json.dumps(state, indent=2, ensure_ascii=False)
            }
        }
    }

    resp = requests.patch(url, headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    logger.info("State saved to Gist %s", gist_id)

def reset_state(gist_id: str, pat: str) -> None:
    """Reset the Gist state store to an empty promotions list."""
    save_state(gist_id, pat, DEFAULT_STATE)