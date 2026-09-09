def test_login_redirects_to_spotify_authorize(client):
    resp = client.get("/spotify/login")
    assert resp.status_code == 302
    assert resp.headers["Location"].startswith("https://accounts.spotify.com/authorize")
    assert "show_dialog=false" in resp.headers["Location"]


def test_login_can_force_consent_dialog(client):
    # Used by the "Reconnect Spotify" flow after adding new scopes, so
    # Spotify actually re-prompts instead of silently reusing an old grant.
    resp = client.get("/spotify/login?show_dialog=true")
    assert "show_dialog=true" in resp.headers["Location"]


def test_callback_rejects_mismatched_state(client):
    # No login step happened, so there's no state in the session to match —
    # this simulates a forged/replayed callback (CSRF on the OAuth flow).
    resp = client.get("/spotify/callback?code=fake&state=not-the-real-state")
    assert resp.status_code == 302
    assert "spotify_error=invalid_state" in resp.headers["Location"]


def test_status_when_not_connected(client):
    resp = client.get("/api/spotify/status")
    assert resp.status_code == 200
    assert resp.get_json()["connected"] is False


def test_now_playing_requires_connection(client):
    resp = client.get("/api/spotify/now-playing")
    assert resp.status_code == 401
