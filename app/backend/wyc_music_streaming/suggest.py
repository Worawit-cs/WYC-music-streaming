"""Search-box suggestions from Google's YouTube suggest endpoint (not an official API).

Any failure gives an empty list: suggestions are a nice-to-have and must never break search.
"""
from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
SUGGEST_TIMEOUT = 3.0
MAX_SUGGESTIONS = 8


async def fetch_suggestions(http: httpx.AsyncClient, q: str) -> list[str]:
    """Return up to MAX_SUGGESTIONS strings. The endpoint answers ["q", ["s1", "s2", ...], ...]."""
    try:
        response = await http.get(SUGGEST_URL, params={"client": "firefox", "ds": "yt", "q": q})
        response.raise_for_status()
        data = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        log.warning("suggest failed: %s", exc)
        return []
    if not (isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list)):
        log.warning("suggest gave an unexpected shape: %.100r", data)
        return []
    words = [s.strip() for s in data[1] if isinstance(s, str) and s.strip()]
    return words[:MAX_SUGGESTIONS]
