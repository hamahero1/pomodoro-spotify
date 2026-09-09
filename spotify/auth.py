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
    url = client.build_authorize_url(
        client_id=_cfg()["SPOTIFY_CLIENT_ID"],
        redirect_uri=_cfg()["SPOTIFY_REDIRECT_URI"],
        scopes=_cfg()["SPOTIFY_SCOPES"],
        state=state,
    )
    return redirect(url)


@spotify_bp.route("/spotify/callback")
def callback():
    error = request.args.get("error")
    if error:
        return redirect(url_for("index", spotify_error=error))

    state = request.args.get("state")
    expected_state = session.pop(SESSION_STATE_KEY, None)
    # Verifying state prevents CSRF on the OAuth callback (an attacker tricking
    # your browser into completing a login flow they initiated).
    if not state or not expected_state or state != expected_state:
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
    except client.SpotifyAPIError:
        return redirect(url_for("index", spotify_error="token_exchange_failed"))

    _store_tokens(token_data)
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
    except client.SpotifyAPIError:
        return jsonify({"error": "spotify_error"}), 502
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
    except client.SpotifyAPIError:
        return jsonify({"error": "spotify_error"}), 502
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
    except client.SpotifyAPIError:
        return jsonify({"error": "spotify_error"}), 502
    return jsonify({"ok": True})
