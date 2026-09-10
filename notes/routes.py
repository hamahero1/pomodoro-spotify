"""Notes API: notes are stored as real .md files on disk (metadata in SQLite),
optionally organized into folders (also real subdirectories under NOTES_DIR).

Filenames are always generated server-side from a slug + short random id and
verified to resolve inside NOTES_DIR before every read/write/delete — this is
what prevents a crafted title (e.g. "../../secrets") from ever escaping the
notes directory (path traversal). Folder names are validated against a strict
allow-list of characters for the same reason before ever touching the
filesystem.

Note titles must be unique within their folder (root counts as one folder):
creating or renaming a note to a title that's already taken in that folder
auto-appends "1", "2", ... instead of erroring or silently colliding.
"""
from __future__ import annotations

import os
import re
import secrets

from flask import Blueprint, abort, current_app, jsonify, request
from werkzeug.utils import secure_filename

from extensions import db
from models import Note, NoteFolder

notes_bp = Blueprint("notes", __name__)

MAX_TITLE_LENGTH = 150
MAX_CONTENT_LENGTH = 500_000  # ~500 KB per note, plenty for text notes
FOLDER_NAME_RE = re.compile(r"^[A-Za-z0-9 _-]{1,60}$")
ROOT_SENTINEL = "__root__"  # ?folder=__root__ means "notes with no folder"


def _notes_dir() -> str:
    return current_app.config["NOTES_DIR"]


def _safe_path(filename: str, folder: str | None = None) -> str:
    """Resolves filename (optionally inside a folder) within NOTES_DIR, or
    aborts if it would ever escape it."""
    notes_dir = os.path.realpath(_notes_dir())
    rel = os.path.join(folder, filename) if folder else filename
    candidate = os.path.realpath(os.path.join(notes_dir, rel))
    if os.path.commonpath([notes_dir, candidate]) != notes_dir:
        abort(400, description="invalid path")
    return candidate


def _make_filename(title: str) -> str:
    slug = secure_filename(title).lower()
    slug = re.sub(r"[^a-z0-9-]+", "-", slug).strip("-") or "note"
    slug = slug[:60]
    unique = secrets.token_hex(4)
    return f"{slug}-{unique}.md"


def _validate_folder_name(name: str) -> str:
    name = (name or "").strip()
    if not name or not FOLDER_NAME_RE.match(name):
        abort(
            400,
            description="Folder name must be 1-60 characters: letters, numbers, spaces, - or _",
        )
    return name


def _unique_title(folder: str | None, desired_title: str, exclude_note_id: int | None = None) -> str:
    """If desired_title is already used by another note in the same folder,
    returns "desired_title 1", or "desired_title 2" if that's taken too, etc."""
    query = Note.query.filter(Note.folder == folder) if folder else Note.query.filter(Note.folder.is_(None))
    if exclude_note_id is not None:
        query = query.filter(Note.id != exclude_note_id)
    existing = {n.title.casefold() for n in query.all()}

    if desired_title.casefold() not in existing:
        return desired_title
    i = 1
    while f"{desired_title} {i}".casefold() in existing:
        i += 1
    return f"{desired_title} {i}"


# ---- Folders ----------------------------------------------------------


@notes_bp.route("/api/notes/folders", methods=["GET"])
def list_folders():
    folders = NoteFolder.query.order_by(NoteFolder.name).all()
    return jsonify([f.to_dict() for f in folders])


@notes_bp.route("/api/notes/folders", methods=["POST"])
def create_folder():
    data = request.get_json(silent=True) or {}
    name = _validate_folder_name(data.get("name"))

    existing = NoteFolder.query.filter(db.func.lower(NoteFolder.name) == name.lower()).first()
    if existing:
        return jsonify({"error": "A folder with that name already exists"}), 409

    os.makedirs(os.path.join(_notes_dir(), name), exist_ok=True)
    folder = NoteFolder(name=name)
    db.session.add(folder)
    db.session.commit()
    return jsonify(folder.to_dict()), 201


# ---- Notes --------------------------------------------------------------


@notes_bp.route("/api/notes", methods=["GET"])
def list_notes():
    query = Note.query
    folder_param = request.args.get("folder")
    if folder_param == ROOT_SENTINEL:
        query = query.filter(Note.folder.is_(None))
    elif folder_param:
        query = query.filter(Note.folder == folder_param)
    notes = query.order_by(Note.updated_at.desc()).all()
    return jsonify([n.to_dict() for n in notes])


@notes_bp.route("/api/notes", methods=["POST"])
def create_note():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip() or "Untitled note"
    content = data.get("content", "")
    folder = data.get("folder") or None

    if len(title) > MAX_TITLE_LENGTH:
        abort(400, description=f"title must be at most {MAX_TITLE_LENGTH} characters")
    if len(content) > MAX_CONTENT_LENGTH:
        abort(400, description="note is too large")
    if folder is not None:
        folder = _validate_folder_name(folder)
        if not NoteFolder.query.filter(db.func.lower(NoteFolder.name) == folder.lower()).first():
            abort(404, description="folder not found")

    title = _unique_title(folder, title)

    os.makedirs(os.path.join(_notes_dir(), folder) if folder else _notes_dir(), exist_ok=True)
    filename = _make_filename(title)
    path = _safe_path(filename, folder)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    note = Note(title=title, filename=filename, folder=folder)
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
    path = _safe_path(note.filename, note.folder)
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
            # Re-resolve uniqueness within this note's own folder if the
            # new title collides with a different note's title.
            note.title = _unique_title(note.folder, title, exclude_note_id=note.id)

    path = _safe_path(note.filename, note.folder)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    db.session.commit()  # bumps updated_at via onupdate
    return jsonify({**note.to_dict(), "content": content})


@notes_bp.route("/api/notes/<int:note_id>", methods=["DELETE"])
def delete_note(note_id: int):
    note = _get_note_or_404(note_id)
    path = _safe_path(note.filename, note.folder)
    if os.path.exists(path):
        os.remove(path)
    db.session.delete(note)
    db.session.commit()
    return jsonify({"ok": True})
