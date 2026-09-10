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


def test_create_and_list_folder(client):
    resp = client.post("/api/notes/folders", json={"name": "Work"}, headers=api_headers())
    assert resp.status_code == 201
    assert resp.get_json()["name"] == "Work"

    resp = client.get("/api/notes/folders")
    names = [f["name"] for f in resp.get_json()]
    assert "Work" in names


def test_create_folder_rejects_duplicate(client):
    client.post("/api/notes/folders", json={"name": "Work"}, headers=api_headers())
    resp = client.post("/api/notes/folders", json={"name": "Work"}, headers=api_headers())
    assert resp.status_code == 409


def test_create_folder_rejects_bad_characters(client):
    resp = client.post("/api/notes/folders", json={"name": "../evil"}, headers=api_headers())
    assert resp.status_code == 400


def test_note_saved_into_folder_directory(client, app):
    client.post("/api/notes/folders", json={"name": "Work"}, headers=api_headers())
    resp = client.post(
        "/api/notes",
        json={"title": "Meeting notes", "content": "x", "folder": "Work"},
        headers=api_headers(),
    )
    assert resp.status_code == 201
    note = resp.get_json()
    assert note["folder"] == "Work"
    path = os.path.join(app.config["NOTES_DIR"], "Work", note["filename"])
    assert os.path.exists(path)


def test_note_requires_existing_folder(client):
    resp = client.post(
        "/api/notes",
        json={"title": "x", "content": "x", "folder": "NoSuchFolder"},
        headers=api_headers(),
    )
    assert resp.status_code == 404


def test_duplicate_title_in_same_folder_auto_increments(client):
    """First 'note' stays 'note'; a second one becomes 'note 1'; a third
    becomes 'note 2' — matches the exact behavior requested."""
    first = client.post("/api/notes", json={"title": "note", "content": "a"}, headers=api_headers()).get_json()
    second = client.post("/api/notes", json={"title": "note", "content": "b"}, headers=api_headers()).get_json()
    third = client.post("/api/notes", json={"title": "note", "content": "c"}, headers=api_headers()).get_json()

    assert first["title"] == "note"
    assert second["title"] == "note 1"
    assert third["title"] == "note 2"


def test_duplicate_title_allowed_in_different_folders(client):
    client.post("/api/notes/folders", json={"name": "Work"}, headers=api_headers())
    root_note = client.post("/api/notes", json={"title": "note"}, headers=api_headers()).get_json()
    work_note = client.post(
        "/api/notes", json={"title": "note", "folder": "Work"}, headers=api_headers()
    ).get_json()

    assert root_note["title"] == "note"
    assert work_note["title"] == "note"  # different folder, no collision


def test_rename_note_to_taken_title_auto_increments(client):
    client.post("/api/notes", json={"title": "note"}, headers=api_headers())
    other = client.post("/api/notes", json={"title": "other"}, headers=api_headers()).get_json()

    resp = client.put(f"/api/notes/{other['id']}", json={"title": "note"}, headers=api_headers())
    assert resp.get_json()["title"] == "note 1"
