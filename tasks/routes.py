"""Task manager REST API: create/list/start/stop/complete tasks & subtasks."""
from __future__ import annotations

from datetime import date, datetime, timezone

from flask import Blueprint, abort, jsonify, request

from extensions import db
from models import Task, TimerSession, STATUS_DONE, STATUS_IN_PROGRESS, STATUS_NOT_STARTED

tasks_bp = Blueprint("tasks", __name__)

MAX_TITLE_LENGTH = 200


def _utcnow():
    return datetime.now(timezone.utc)


def _parse_date(value: str | None):
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        abort(400, description="date must be in YYYY-MM-DD format")


@tasks_bp.route("/api/tasks", methods=["GET"])
def list_tasks():
    """Top-level tasks (with nested subtasks). Optional ?date=YYYY-MM-DD filter."""
    query = Task.query.filter(Task.parent_task_id.is_(None))
    date_filter = request.args.get("date")
    if date_filter:
        query = query.filter(Task.date == _parse_date(date_filter))
    tasks = query.order_by(Task.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tasks])


@tasks_bp.route("/api/tasks", methods=["POST"])
def create_task():
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "").strip()
    if not title:
        abort(400, description="title is required")
    if len(title) > MAX_TITLE_LENGTH:
        abort(400, description=f"title must be at most {MAX_TITLE_LENGTH} characters")

    parent_id = data.get("parent_task_id")
    parent = None
    if parent_id is not None:
        parent = db.session.get(Task, parent_id)
        if not parent:
            abort(404, description="parent task not found")

    estimated_minutes = data.get("estimated_minutes")
    if estimated_minutes is not None:
        try:
            estimated_minutes = int(estimated_minutes)
            if estimated_minutes < 0:
                raise ValueError
        except (TypeError, ValueError):
            abort(400, description="estimated_minutes must be a non-negative integer")

    task = Task(
        title=title,
        parent_task_id=parent.id if parent else None,
        estimated_minutes=estimated_minutes,
        date=_parse_date(data.get("date")),
    )
    db.session.add(task)
    db.session.commit()
    return jsonify(task.to_dict()), 201


def _get_task_or_404(task_id: int) -> Task:
    task = db.session.get(Task, task_id)
    if not task:
        abort(404, description="task not found")
    return task


@tasks_bp.route("/api/tasks/<int:task_id>", methods=["GET"])
def get_task(task_id: int):
    return jsonify(_get_task_or_404(task_id).to_dict())


@tasks_bp.route("/api/tasks/<int:task_id>", methods=["PATCH"])
def update_task(task_id: int):
    task = _get_task_or_404(task_id)
    data = request.get_json(silent=True) or {}

    if "title" in data:
        title = (data["title"] or "").strip()
        if not title or len(title) > MAX_TITLE_LENGTH:
            abort(400, description="invalid title")
        task.title = title
    if "estimated_minutes" in data:
        task.estimated_minutes = data["estimated_minutes"]
    if "date" in data:
        task.date = _parse_date(data["date"])

    db.session.commit()
    return jsonify(task.to_dict())


@tasks_bp.route("/api/tasks/<int:task_id>", methods=["DELETE"])
def delete_task(task_id: int):
    task = _get_task_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return jsonify({"ok": True})


def _close_open_session(task: Task) -> None:
    open_session = (
        TimerSession.query.filter_by(task_id=task.id, ended_at=None)
        .order_by(TimerSession.started_at.desc())
        .first()
    )
    if not open_session:
        return
    now = _utcnow()
    open_session.ended_at = now
    started_at = open_session.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    duration = int((now - started_at).total_seconds())
    open_session.duration_seconds = max(duration, 0)
    task.logged_seconds += open_session.duration_seconds


@tasks_bp.route("/api/tasks/<int:task_id>/start", methods=["POST"])
def start_task(task_id: int):
    task = _get_task_or_404(task_id)
    if task.status == STATUS_DONE:
        abort(400, description="task is already done")

    # Only one running timer per task at a time.
    already_running = TimerSession.query.filter_by(task_id=task.id, ended_at=None).first()
    if not already_running:
        db.session.add(TimerSession(task_id=task.id, kind="task_tracking"))
    task.status = STATUS_IN_PROGRESS
    db.session.commit()
    return jsonify(task.to_dict())


@tasks_bp.route("/api/tasks/<int:task_id>/stop", methods=["POST"])
def stop_task(task_id: int):
    task = _get_task_or_404(task_id)
    _close_open_session(task)
    if task.status == STATUS_IN_PROGRESS:
        task.status = STATUS_NOT_STARTED
    db.session.commit()
    return jsonify(task.to_dict())


@tasks_bp.route("/api/tasks/<int:task_id>/complete", methods=["POST"])
def complete_task(task_id: int):
    task = _get_task_or_404(task_id)
    _close_open_session(task)
    task.status = STATUS_DONE
    task.completed_at = _utcnow()
    db.session.commit()
    return jsonify(task.to_dict())


@tasks_bp.route("/api/tasks/<int:task_id>/reopen", methods=["POST"])
def reopen_task(task_id: int):
    task = _get_task_or_404(task_id)
    task.status = STATUS_NOT_STARTED
    task.completed_at = None
    db.session.commit()
    return jsonify(task.to_dict())
