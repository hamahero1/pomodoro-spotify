"""Lyrics API for the frontend — looks up whatever is currently playing."""
from flask import Blueprint, jsonify, request

from spotify.auth import get_valid_access_token
from spotify import client as spotify_client

from . import lrclib_client

lyrics_bp = Blueprint("lyrics", __name__)


@lyrics_bp.route("/api/lyrics/current")
def current_lyrics():
    """Lyrics for whatever's currently playing on Spotify.

    Falls back to found=False (frontend shows the music icon) if nothing is
    playing or no lyrics exist for the track.
    """
    access_token = get_valid_access_token()
    if not access_token:
        return jsonify({"error": "not_connected"}), 401

    try:
        track = spotify_client.get_currently_playing(access_token)
    except spotify_client.SpotifyAPIError:
        return jsonify({"error": "spotify_error"}), 502

    if not track:
        return jsonify({"found": False, "track": None})

    lyrics = lrclib_client.find_lyrics(
        title=track["title"], artist=track["artist"], album=track.get("album")
    )
    return jsonify({"found": lyrics is not None, "track": track, "lyrics": lyrics})


@lyrics_bp.route("/api/lyrics/search")
def search_lyrics():
    """Manual lookup, e.g. for testing without a live Spotify session."""
    title = request.args.get("title", "").strip()
    artist = request.args.get("artist", "").strip()
    if not title or not artist:
        return jsonify({"error": "title and artist are required"}), 400
    lyrics = lrclib_client.find_lyrics(title=title, artist=artist)
    return jsonify({"found": lyrics is not None, "lyrics": lyrics})
