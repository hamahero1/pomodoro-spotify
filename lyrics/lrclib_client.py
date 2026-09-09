"""Wrapper around lrclib.net — free, no-API-key lyrics lookup."""
from __future__ import annotations

import requests

SEARCH_URL = "https://lrclib.net/api/search"
REQUEST_TIMEOUT = 6


def find_lyrics(title: str, artist: str, album: str | None = None) -> dict | None:
    """Best-effort lyrics lookup. Returns None if nothing is found (caller
    should fall back to showing the album art / a music icon instead)."""
    if not title or not artist:
        return None

    params = {"track_name": title, "artist_name": artist}
    if album:
        params["album_name"] = album

    try:
        resp = requests.get(SEARCH_URL, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return None

    if resp.status_code != 200:
        return None

    results = resp.json()
    if not results:
        return None

    best = results[0]
    plain = best.get("plainLyrics")
    synced = best.get("syncedLyrics")
    if not plain and not synced:
        return None

    return {
        "plain_lyrics": plain,
        "synced_lyrics": synced,
        "instrumental": best.get("instrumental", False),
    }
