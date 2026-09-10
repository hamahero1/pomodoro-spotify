"""Verifies that an existing SQLite DB from before the `note.folder` column
was added gets upgraded automatically instead of 500ing forever."""
import sqlite3

from app import create_app
from config import TestConfig
from extensions import db


def test_old_note_table_without_folder_column_gets_migrated(tmp_path):
    db_path = tmp_path / "old.db"

    # Simulate a database created by an earlier version of the app: a
    # `note` table with no `folder` column at all.
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE note (
            id INTEGER PRIMARY KEY,
            title VARCHAR(200) NOT NULL,
            filename VARCHAR(255) NOT NULL UNIQUE,
            created_at DATETIME NOT NULL,
            updated_at DATETIME NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO note (title, filename, created_at, updated_at) VALUES (?, ?, datetime('now'), datetime('now'))",
        ("Old note", "old-note-abc123.md"),
    )
    conn.commit()
    conn.close()

    class OldDbConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{db_path}"

    app = create_app(OldDbConfig)
    app.config["NOTES_DIR"] = str(tmp_path / "notes")

    with app.app_context():
        # If the migration didn't run, this raises OperationalError
        # ("no such column: note.folder") instead of returning cleanly.
        client = app.test_client()

    resp = client.get("/api/notes")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data) == 1
    assert data[0]["title"] == "Old note"
    assert data[0]["folder"] is None

    with app.app_context():
        db.session.remove()
