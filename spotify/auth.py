"""Spotify OAuth login/callback/logout, and small JSON endpoints the frontend polls."""
from __future__ import annotations

import secrets
import time

from flask import Blueprint, current_app, jsonify, redirect, request, session, url_for

from . import client

spotify_bp = Blueprint("spotify", __name__)

SESSION_STATE_KEY = "spotify_oauth_state"
SESSION_TOKENS_KEY = "spotify_tokens"  # {access_token, refresh_token, expires_at}


def _cfg():
    return current_app.config


@spotify_bp.route("/spotify/login")
def login():
    state = secrets.token_urlsafe(24)
    session[SESSION_STATE_KEY] = state
    # ?show_dialog=true forces Spotify's consent screen to appear even if
    # this browser already has an active authorization — used when
    # reconnecting after adding new scopes, so the new permission is
    # actually re-prompted instead of silently reusing an old grant.
    show_dialog = request.args.get("show_dialog", "false").lower() == "true"
    url = client.build_authorize_url(
        client_id=_cfg()["SPOTIFY_CLIENT_ID"],
        redirect_uri=_cfg()["SPOTIFY_REDIRECT_URI"],
        scopes=_cfg()["SPOTIFY_SCOPES"],
        state=state,
        show_dialog=show_dialog,
    )
    return redirect(url)


@spotify_bp.route("/spotify/callback")
def callback():
    error = request.args.get("error")
    if error:
        current_app.logger.warning("Spotify callback returned an error param: %s", error)
        return redirect(url_for("index", spotify_error=error))

    state = request.args.get("state")
    expected_state = session.pop(SESSION_STATE_KEY, None)
    # Verifying state prevents CSRF on the OAuth callback (an attacker tricking
    # your browser into completing a login flow they initiated).
    if not state or not expected_state or state != expected_state:
        current_app.logger.warning(
            "Spotify callback state mismatch (got=%r, expected=%r) — likely a stale "
            "session cookie or a second login attempt overwriting the first.",
            state, expected_state,
        )
        return redirect(url_for("index", spotify_error="invalid_state"))

    code = request.args.get("code")
    if not code:
        return redirect(url_for("index", spotify_error="missing_code"))

    try:
        token_data = client.exchange_code_for_token(
            code=code,
            redirect_uri=_cfg()["SPOTIFY_REDIRECT_URI"],
            client_id=_cfg()["SPOTIFY_CLIENT_ID"],
            client_secret=_cfg()["SPOTIFY_CLIENT_SECRET"],
        )
    except client.SpotifyAPIError as e:
        # Logged in full server-side (never sent to the browser) — this is
        # almost always a redirect_uri mismatch between what's registered on
        # the Spotify dashboard and SPOTIFY_REDIRECT_URI in .env.
        current_app.logger.error("Spotify token exchange failed: %s", e)
        return redirect(url_for("index", spotify_error="token_exchange_failed"))

    _store_tokens(token_data)
    current_app.logger.info("Spotify connected successfully.")
    return redirect(url_for("index"))


@spotify_bp.route("/spotify/logout", methods=["POST"])
def logout():
    session.pop(SESSION_TOKENS_KEY, None)
    return jsonify({"ok": True})


def _store_tokens(token_data: dict) -> None:
    tokens = session.get(SESSION_TOKENS_KEY, {})
    tokens["access_token"] = token_data["access_token"]
    tokens["expires_at"] = time.time() + token_data.get("expires_in", 3600) - 30
    # Spotify only returns a refresh_token on the *first* authorization.
    if token_data.get("refresh_token"):
        tokens["refresh_token"] = token_data["refresh_token"]
    session[SESSION_TOKENS_KEY] = tokens
    session.permanent = True


def get_valid_access_token() -> str | None:
    """Returns a live access token, refreshing it first if it's expired.

    Tokens live only in the server-side session — never written into the
    rendered page — except via /api/spotify/token, which the Web Playback
    SDK needs client-side by design (it's short-lived and scoped to this
    user's own session).
    """
    tokens = session.get(SESSION_TOKENS_KEY)
    if not tokens:
        return None

    if time.time() < tokens.get("expires_at", 0):
        return tokens["access_token"]

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        session.pop(SESSION_TOKENS_KEY, None)
        return None

    try:
        token_data = client.refresh_access_token(
            refresh_token=refresh_token,
            client_id=_cfg()["SPOTIFY_CLIENT_ID"],
            client_secret=_cfg()["SPOTIFY_CLIENT_SECRET"],
        )
    except client.SpotifyAPIError:
        session.pop(SESSION_TOKENS_KEY, None)
        return None

    _store_tokens(token_data)
    return session[SESSION_TOKENS_KEY]["access_token"]


def _spotify_error_response(e: client.SpotifyAPIError, action: str):
    """Logs the real Spotify error server-side and returns a JSON response
    that's actually useful to the frontend instead of a generic string."""
    current_app.logger.error("Spotify API error during %s: %s", action, e)
    if e.status_code == 403:
        # Almost always: the current session's access token was granted
        # before a scope this endpoint needs was added — reconnecting
        # re-runs the OAuth flow and picks up the new scope.
        return jsonify(
            {
                "error": "insufficient_scope",
                "message": "Reconnect Spotify to grant the permissions this needs.",
            }
        ), 403
    if e.status_code == 401:
        return jsonify({"error": "not_connected"}), 401
    return jsonify({"error": "spotify_error", "message": str(e)}), 502


# ---- JSON API used by the frontend ----------------------------------------


@spotify_bp.route("/api/spotify/status")
def status():
    return jsonify({"connected": get_valid_access_token() is not None})


@spotify_bp.route("/api/spotify/token")
def token():
    """Access token for the Web Playback SDK. Requires an active session."""
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    return jsonify({"access_token": access_token})


@spotify_bp.route("/api/spotify/now-playing")
def now_playing():
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    try:
        track = client.get_currently_playing(access_token)
    except client.SpotifyAPIError as e:
        return _spotify_error_response(e, "now-playing")
    return jsonify({"track": track})


@spotify_bp.route("/api/spotify/player/<action>", methods=["PUT"])
def player_action(action: str):
    if action not in ("play", "pause", "next", "previous"):
        return jsonify({"error": "invalid_action"}), 400
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    device_id = request.args.get("device_id")
    try:
        client.player_command(access_token, action, device_id)
    except client.SpotifyAPIError as e:
        return _spotify_error_response(e, f"player {action}")
    return jsonify({"ok": True})


@spotify_bp.route("/api/spotify/player/transfer", methods=["PUT"])
def player_transfer():
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    data = request.get_json(silent=True) or {}
    device_id = data.get("device_id")
    if not device_id:
        return jsonify({"error": "missing_device_id"}), 400
    try:
        client.transfer_playback(access_token, device_id)
    except client.SpotifyAPIError as e:
        return _spotify_error_response(e, "player transfer")
    return jsonify({"ok": True})


@spotify_bp.route("/api/spotify/playlists")
def playlists():
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    try:
        items = client.get_user_playlists(access_token)
    except client.SpotifyAPIError as e:
        return _spotify_error_response(e, "playlists lookup")
    return jsonify({"playlists": items})


@spotify_bp.route("/api/spotify/playlists/<playlist_id>/tracks")
def playlist_tracks(playlist_id: str):
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    try:
        tracks = client.get_playlist_tracks(access_token, playlist_id)
    except client.SpotifyAPIError as e:
        return _spotify_error_response(e, "playlist tracks lookup")
    return jsonify({"tracks": tracks})


@spotify_bp.route("/api/spotify/player/play-track", methods=["PUT"])
def player_play_track():
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401
    data = request.get_json(silent=True) or {}
    uri = data.get("uri")
    if not uri:
        return jsonify({"error": "missing_uri"}), 400
    try:
        client.play_track(access_token, uri, data.get("device_id"))
    except client.SpotifyAPIError as e:
        return _spotify_error_response(e, "play track")
    return jsonify({"ok": True})
