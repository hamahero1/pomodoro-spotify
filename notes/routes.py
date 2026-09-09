"""Notes API: notes are stored as real .md files on disk (metadata in SQLite).

Filenames are always generated server-side from a slug + short random id and
verified to resolve inside NOTES_DIR before every read/write/delete — this is
what prevents a crafted title (e.g. "../../secrets") from ever escaping the
notes directory (path traversal).
"""
from __future__ import annotations

import os
import re
import secrets

from flask import Blueprint, abort, current_app, jsonify, request
from werkzeug.utils import secure_filename

from extensions import db
from models import Note

notes_bp = Blueprint("notes", __name__)

MAX_TITLE_LENGTH = 150
MAX_CONTENT_LENGTH = 500_000  # ~500 KB per note, plenty for text notes


def _notes_dir() -> str:
    return current_app.config["NOTES_DIR"]


def _safe_path(filename: str) -> str:
    """Resolves filename inside NOTES_DIR, or aborts if it would escape it."""
    notes_dir = os.path.realpath(_notes_dir())
    candidate = os.path.realpath(os.path.join(notes_dir, filename))
    if os.path.commonpath([notes_dir, candidate]) != notes_dir:
        abort(400, description="invalid filename")
    return candidate


def _make_filename(title: str) -> str:
    slug = secure_filename(title).lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-") or "note"
    slug = slug[:60]
    unique = secrets.token_hex(4)
    return f"{slug}-{unique}.md"


@notes_bp.route("/api/notes", methods=["GET"])
def list_notes():
    notes = Note.query.order_by(Note.updated_at.desc()).all()
    return jsonify([n.to_dict() for n in notes])


@notes_bp.route("/api/notes", methods=["POST"])
def create_note():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip() or "Untitled note"
    content = data.get("content", "")

    if len(title) > MAX_TITLE_LENGTH:
        abort(400, description=f"title must be at most {MAX_TITLE_LENGTH} characters")
    if len(content) > MAX_CONTENT_LENGTH:
        abort(400, description="note is too large")

    os.makedirs(_notes_dir(), exist_ok=True)
    filename = _make_filename(title)
    path = _safe_path(filename)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    note = Note(title=title, filename=filename)
    db.session.add(note)
    db.session.commit()
    return jsonify({**note.to_dict(), "content": content}), 201


def _get_note_or_404(note_id: int) -> Note:
    note = db.session.get(Note, note_id)
    if not note:
        abort(404, description="note not found")
    return note


@notes_bp.route("/api/notes/<int:note_id>", methods=["GET"])
def get_note(note_id: int):
    note = _get_note_or_404(note_id)
    path = _safe_path(note.filename)
    content = ""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    return jsonify({**note.to_dict(), "content": content})


@notes_bp.route("/api/notes/<int:note_id>", methods=["PUT"])
def save_note(note_id: int):
    note = _get_note_or_404(note_id)
    data = request.get_json(silent=True) or {}
    content = data.get("content", "")
    if len(content) > MAX_CONTENT_LENGTH:
        abort(400, description="note is too large")

    if "title" in data:
        title = (data["title"] or "").strip()
        if title and len(title) <= MAX_TITLE_LENGTH:
            note.title = title

    path = _safe_path(note.filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    db.session.commit()  # bumps updated_at via onupdate
    return jsonify({**note.to_dict(), "content": content})


@notes_bp.route("/api/notes/<int:note_id>", methods=["DELETE"])
def delete_note(note_id: int):
    note = _get_note_or_404(note_id)
    path = _safe_path(note.filename)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(note)
    db.session.commit()
    return jsonify({"ok": True})
