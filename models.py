"""SQLAlchemy models: Task (with subtasks), TimerSession, Note."""
from datetime import datetime, timezone

from extensions import db

STATUS_NOT_STARTED = "not_started"
STATUS_IN_PROGRESS = "in_progress"
STATUS_DONE = "done"
TASK_STATUSES = (STATUS_NOT_STARTED, STATUS_IN_PROGRESS, STATUS_DONE)

KIND_POMODORO_WORK = "pomodoro_work"
KIND_POMODORO_BREAK = "pomodoro_break"
KIND_TASK_TRACKING = "task_tracking"
SESSION_KINDS = (KIND_POMODORO_WORK, KIND_POMODORO_BREAK, KIND_TASK_TRACKING)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Task(db.Model):
    __tablename__ = "task"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_NOT_STARTED)
    estimated_minutes = db.Column(db.Integer, nullable=True)
    logged_seconds = db.Column(db.Integer, nullable=False, default=0)
    date = db.Column(db.Date, nullable=True)  # assigned date, for the calendar view
    parent_task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    subtasks = db.relationship(
        "Task",
        backref=db.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
        single_parent=True,
        order_by="Task.created_at",
    )
    timer_sessions = db.relationship(
        "TimerSession", backref="task", cascade="all, delete-orphan"
    )

    def total_logged_seconds(self) -> int:
        """This task's own time plus all its subtasks' time, recursively."""
        total = self.logged_seconds
        for sub in self.subtasks:
            total += sub.total_logged_seconds()
        return total

    def to_dict(self, include_subtasks: bool = True) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "estimated_minutes": self.estimated_minutes,
            "logged_seconds": self.logged_seconds,
            "total_logged_seconds": self.total_logged_seconds(),
            "date": self.date.isoformat() if self.date else None,
            "parent_task_id": self.parent_task_id,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
        if include_subtasks:
            data["subtasks"] = [s.to_dict(include_subtasks=True) for s in self.subtasks]
        return data


class TimerSession(db.Model):
    __tablename__ = "timer_session"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("task.id"), nullable=True)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utcnow)
    ended_at = db.Column(db.DateTime(timezone=True), nullable=True)
    duration_seconds = db.Column(db.Integer, nullable=True)
    kind = db.Column(db.String(20), nullable=False, default=KIND_TASK_TRACKING)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds,
            "kind": self.kind,
        }


class NoteFolder(db.Model):
    __tablename__ = "note_folder"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "created_at": self.created_at.isoformat()}


class Note(db.Model):
    __tablename__ = "note"
    # A note's title must be unique within its folder (NULL folder = root) —
    # enforced at creation/rename time in notes/routes.py by auto-appending
    # "1", "2", ... on collision, not by a hard DB constraint (so we control
    # the friendly auto-rename instead of a raw integrity error).

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(255), nullable=False, unique=True)
    folder = db.Column(db.String(100), nullable=True)  # NoteFolder.name, or NULL for root
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "filename": self.filename,
            "folder": self.folder,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
