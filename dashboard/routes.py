"""Dashboard API: overview stats, calendar-by-date view, and Pomodoro session logging."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from flask import Blueprint, abort, jsonify, request
from sqlalchemy import func

from extensions import db
from models import SESSION_KINDS, STATUS_DONE, Task, TimerSession

dashboard_bp = Blueprint("dashboard", __name__)


def _parse_date(value: str | None) -> date:
    if not value:
        return datetime.now(timezone.utc).date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        abort(400, description="date must be in YYYY-MM-DD format")


@dashboard_bp.route("/api/dashboard/summary")
def summary():
    today = datetime.now(timezone.utc).date()

    completed_count = Task.query.filter(Task.status == STATUS_DONE).count()
    total_seconds = db.session.query(func.coalesce(func.sum(Task.logged_seconds), 0)).scalar()

    completed_today = Task.query.filter(
        Task.status == STATUS_DONE, func.date(Task.completed_at) == today.isoformat()
    ).count()

    # Time spent per day, last 14 days, from closed timer sessions of any kind.
    window_start = today - timedelta(days=13)
    rows = (
        db.session.query(
            func.date(TimerSession.started_at).label("day"),
            func.coalesce(func.sum(TimerSession.duration_seconds), 0).label("seconds"),
        )
        .filter(
            TimerSession.ended_at.isnot(None),
            func.date(TimerSession.started_at) >= window_start.isoformat(),
        )
        .group_by("day")
        .all()
    )
    by_day = {row.day: row.seconds for row in rows}
    last_14_days = [
        {
            "date": (window_start + timedelta(days=i)).isoformat(),
            "total_seconds": by_day.get((window_start + timedelta(days=i)).isoformat(), 0),
        }
        for i in range(14)
    ]

    return jsonify(
        {
            "completed_count": completed_count,
            "total_seconds": int(total_seconds or 0),
            "completed_today": completed_today,
            "last_14_days": last_14_days,
        }
    )


@dashboard_bp.route("/api/dashboard/calendar")
def calendar_day():
    day = _parse_date(request.args.get("date"))

    tasks = Task.query.filter(Task.date == day, Task.parent_task_id.is_(None)).all()

    total_seconds = (
        db.session.query(func.coalesce(func.sum(TimerSession.duration_seconds), 0))
        .filter(
            TimerSession.ended_at.isnot(None),
            func.date(TimerSession.started_at) == day.isoformat(),
        )
        .scalar()
    )

    return jsonify(
        {
            "date": day.isoformat(),
            "tasks": [t.to_dict() for t in tasks],
            "total_seconds": int(total_seconds or 0),
        }
    )


@dashboard_bp.route("/api/timer/session", methods=["POST"])
def log_timer_session():
    """Logs a completed Pomodoro work/break interval (for dashboard stats).

    Task-linked time tracking is logged automatically by /api/tasks/<id>/start
    and /stop instead — this endpoint is specifically for standalone or
    task-linked Pomodoro intervals the client-side timer completed.
    """
    data = request.get_json(silent=True) or {}
    kind = data.get("kind")
    if kind not in SESSION_KINDS:
        abort(400, description=f"kind must be one of {SESSION_KINDS}")

    duration_seconds = data.get("duration_seconds")
    try:
        duration_seconds = int(duration_seconds)
        if duration_seconds <= 0 or duration_seconds > 24 * 3600:
            raise ValueError
    except (TypeError, ValueError):
        abort(400, description="duration_seconds must be a positive integer (max 24h)")

    task_id = data.get("task_id")
    task = None
    if task_id is not None:
        task = db.session.get(Task, task_id)
        if not task:
            abort(404, description="task not found")

    now = datetime.now(timezone.utc)
    entry = TimerSession(
        task_id=task.id if task else None,
        kind=kind,
        started_at=now - timedelta(seconds=duration_seconds),
        ended_at=now,
        duration_seconds=duration_seconds,
    )
    db.session.add(entry)
    if task and kind == "task_tracking":
        task.logged_seconds += duration_seconds
    db.session.commit()
    return jsonify(entry.to_dict()), 201
