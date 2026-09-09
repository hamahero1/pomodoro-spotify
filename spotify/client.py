"""Thin wrapper around the Spotify Accounts + Web API. No Flask/session code here."""
from __future__ import annotations

from urllib.parse import urlencode

import requests

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
API_BASE = "https://api.spotify.com/v1"

REQUEST_TIMEOUT = 8  # seconds — never let an upstream call hang the app forever


class SpotifyAPIError(RuntimeError):
    """Raised when a call to Spotify's API fails."""


def build_authorize_url(client_id: str, redirect_uri: str, scopes: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "show_dialog": "false",
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def exchange_code_for_token(
    code: str, redirect_uri: str, client_id: str, client_secret: str
) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
        auth=(client_id, client_secret),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise SpotifyAPIError(f"Token exchange failed: {resp.status_code} {resp.text}")
    return resp.json()


def refresh_access_token(refresh_token: str, client_id: str, client_secret: str) -> dict:
    resp = requests.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(client_id, client_secret),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise SpotifyAPIError(f"Token refresh failed: {resp.status_code} {resp.text}")
    return resp.json()


def _auth_headers(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}"}


def get_currently_playing(access_token: str) -> dict | None:
    """Returns the currently playing track, or None if nothing is playing."""
    resp = requests.get(
        f"{API_BASE}/me/player/currently-playing",
        headers=_auth_headers(access_token),
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 204 or not resp.content:
        return None
    if resp.status_code == 401:
        raise SpotifyAPIError("Access token expired or invalid")
    if resp.status_code != 200:
        raise SpotifyAPIError(f"Now-playing lookup failed: {resp.status_code} {resp.text}")

    data = resp.json()
    item = data.get("item")
    if not item:
        return None

    return {
        "is_playing": data.get("is_playing", False),
        "progress_ms": data.get("progress_ms"),
        "track_id": item.get("id"),
        "title": item.get("name"),
        "artist": ", ".join(a.get("name", "") for a in item.get("artists", [])),
        "album": item.get("album", {}).get("name"),
        "album_art_url": (item.get("album", {}).get("images") or [{}])[0].get("url"),
        "duration_ms": item.get("duration_ms"),
    }


def transfer_playback(access_token: str, device_id: str, play: bool = True) -> None:
    resp = requests.put(
        f"{API_BASE}/me/player",
        headers=_auth_headers(access_token),
        json={"device_ids": [device_id], "play": play},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code not in (200, 202, 204):
        raise SpotifyAPIError(f"Transfer playback failed: {resp.status_code} {resp.text}")


def get_user_playlists(access_token: str, limit: int = 50) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/me/playlists",
        headers=_auth_headers(access_token),
        params={"limit": limit},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 401:
        raise SpotifyAPIError("Access token expired or invalid")
    if resp.status_code != 200:
        raise SpotifyAPIError(f"Playlists lookup failed: {resp.status_code} {resp.text}")

    items = resp.json().get("items", [])
    return [
        {
            "id": p["id"],
            "name": p["name"],
            "image_url": (p.get("images") or [{}])[0].get("url"),
            "track_count": p.get("tracks", {}).get("total", 0),
            "owner": (p.get("owner") or {}).get("display_name"),
        }
        for p in items
        if p  # Spotify can return null entries for playlists you no longer have access to
    ]


def get_playlist_tracks(access_token: str, playlist_id: str, limit: int = 100) -> list[dict]:
    resp = requests.get(
        f"{API_BASE}/playlists/{playlist_id}/tracks",
        headers=_auth_headers(access_token),
        params={"limit": limit},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code == 401:
        raise SpotifyAPIError("Access token expired or invalid")
    if resp.status_code != 200:
        raise SpotifyAPIError(f"Playlist tracks lookup failed: {resp.status_code} {resp.text}")

    items = resp.json().get("items", [])
    tracks = []
    for entry in items:
        track = entry.get("track")
        if not track or not track.get("uri"):
            continue  # local files / removed tracks have no playable uri
        tracks.append(
            {
                "uri": track["uri"],
                "title": track.get("name"),
                "artist": ", ".join(a.get("name", "") for a in track.get("artists", [])),
                "album_art_url": (track.get("album", {}).get("images") or [{}])[0].get("url"),
                "duration_ms": track.get("duration_ms"),
            }
        )
    return tracks


def play_track(access_token: str, uri: str, device_id: str | None = None) -> None:
    params = {"device_id": device_id} if device_id else {}
    resp = requests.put(
        f"{API_BASE}/me/player/play",
        headers=_auth_headers(access_token),
        params=params,
        json={"uris": [uri]},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code not in (200, 202, 204):
        raise SpotifyAPIError(f"Play track failed: {resp.status_code} {resp.text}")


def player_command(access_token: str, action: str, device_id: str | None = None) -> None:
    """action: 'play' | 'pause' | 'next' | 'previous'."""
    method = {"play": "PUT", "pause": "PUT", "next": "POST", "previous": "POST"}[action]
    params = {"device_id": device_id} if device_id else {}
    resp = requests.request(
        method,
        f"{API_BASE}/me/player/{action}",
        headers=_auth_headers(access_token),
        params=params,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code not in (200, 202, 204):
        raise SpotifyAPIError(f"Player command '{action}' failed: {resp.status_code} {resp.text}")
