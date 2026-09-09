from unittest.mock import patch

from .conftest import api_headers


def test_playlists_requires_connection(client):
    resp = client.get("/api/spotify/playlists")
    assert resp.status_code == 401


def test_playlist_tracks_requires_connection(client):
    resp = client.get("/api/spotify/playlists/abc123/tracks")
    assert resp.status_code == 401


def test_play_track_requires_connection(client):
    resp = client.post(
        "/api/spotify/player/play-track", json={"uri": "spotify:track:x"}, headers=api_headers()
    )
    # This route is PUT-only; POST should 404/405, not silently succeed.
    assert resp.status_code in (404, 405)


def _connect(client):
    with patch("spotify.auth.client.exchange_code_for_token") as mock_exchange:
        mock_exchange.return_value = {
            "access_token": "fake-token",
            "refresh_token": "fake-refresh",
            "expires_in": 3600,
        }
        resp = client.get("/spotify/login")
        from urllib.parse import urlparse, parse_qs

        state = parse_qs(urlparse(resp.headers["Location"]).query)["state"][0]
        client.get(f"/spotify/callback?code=fake&state={state}")


def test_playlists_lists_when_connected(client):
    _connect(client)
    with patch("spotify.client.get_user_playlists") as mock_playlists:
        mock_playlists.return_value = [
            {"id": "p1", "name": "Focus Mix", "image_url": None, "track_count": 12, "owner": "me"}
        ]
        resp = client.get("/api/spotify/playlists")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["playlists"][0]["name"] == "Focus Mix"


def test_playlist_tracks_when_connected(client):
    _connect(client)
    with patch("spotify.client.get_playlist_tracks") as mock_tracks:
        mock_tracks.return_value = [
            {"uri": "spotify:track:1", "title": "Song A", "artist": "Artist", "album_art_url": None, "duration_ms": 1000}
        ]
        resp = client.get("/api/spotify/playlists/p1/tracks")
    assert resp.status_code == 200
    assert resp.get_json()["tracks"][0]["title"] == "Song A"


def test_play_track_when_connected(client):
    _connect(client)
    with patch("spotify.client.play_track") as mock_play:
        resp = client.put(
            "/api/spotify/player/play-track",
            json={"uri": "spotify:track:1"},
            headers=api_headers(),
        )
    assert resp.status_code == 200
    mock_play.assert_called_once()


def test_play_track_requires_uri(client):
    _connect(client)
    resp = client.put("/api/spotify/player/play-track", json={}, headers=api_headers())
    assert resp.status_code == 400
