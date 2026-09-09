import os

from .conftest import api_headers


def test_create_and_read_note(client, app):
    resp = client.post(
        "/api/notes", json={"title": "Ideas", "content": "# hello"}, headers=api_headers()
    )
    assert resp.status_code == 201
    note = resp.get_json()
    assert note["content"] == "# hello"

    # File actually landed on disk, inside NOTES_DIR.
    path = os.path.join(app.config["NOTES_DIR"], note["filename"])
    assert os.path.exists(path)
    with open(path, encoding="utf-8") as f:
        assert f.read() == "# hello"


def test_update_note_content(client):
    note = client.post(
        "/api/notes", json={"title": "Draft", "content": "v1"}, headers=api_headers()
    ).get_json()

    resp = client.put(
        f"/api/notes/{note['id']}", json={"content": "v2"}, headers=api_headers()
    )
    assert resp.status_code == 200
    assert resp.get_json()["content"] == "v2"


def test_delete_note_removes_file(client, app):
    note = client.post(
        "/api/notes", json={"title": "Temp", "content": "x"}, headers=api_headers()
    ).get_json()
    path = os.path.join(app.config["NOTES_DIR"], note["filename"])
    assert os.path.exists(path)

    resp = client.delete(f"/api/notes/{note['id']}", headers=api_headers())
    assert resp.status_code == 200
    assert not os.path.exists(path)


def test_malicious_title_cannot_escape_notes_dir(client, app):
    """A title crafted to look like a path traversal must not create a file
    outside NOTES_DIR."""
    resp = client.post(
        "/api/notes",
        json={"title": "../../../evil", "content": "pwned"},
        headers=api_headers(),
    )
    assert resp.status_code == 201
    note = resp.get_json()

    notes_dir = os.path.realpath(app.config["NOTES_DIR"])
    file_path = os.path.realpath(os.path.join(notes_dir, note["filename"]))
    assert os.path.commonpath([notes_dir, file_path]) == notes_dir

    outside_path = os.path.realpath(os.path.join(notes_dir, "..", "..", "..", "evil.md"))
    assert not os.path.exists(outside_path)
