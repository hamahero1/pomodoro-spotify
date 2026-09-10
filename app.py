"""Flask application entry point."""
from __future__ import annotations

from urllib.parse import urlparse

from flask import Flask, abort, jsonify, render_template, request
from sqlalchemy import inspect, text

from config import Config
from extensions import db


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)

    from spotify import spotify_bp
    from lyrics import lyrics_bp
    from tasks import tasks_bp
    from notes import notes_bp
    from dashboard import dashboard_bp

    app.register_blueprint(spotify_bp)
    app.register_blueprint(lyrics_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(dashboard_bp)

    with app.app_context():
        db.create_all()
        _migrate_schema()

    _register_security(app)
    _register_error_handlers(app)

    @app.route("/")
    def index():
        return render_template(
            "index.html", spotify_client_id=app.config["SPOTIFY_CLIENT_ID"]
        )

    return app


def _migrate_schema() -> None:
    """Lightweight, dependency-free auto-migration for existing SQLite DBs.

    db.create_all() only creates tables that don't exist yet — it never
    alters an existing table's columns. Any time a new column is added to
    a model after some users already have a database file on disk, this is
    what actually applies it, instead of leaving them with a 500 error
    (e.g. "no such column: note.folder") until they delete their data.
    Add one `_add_column_if_missing(...)` line here per new column.
    """
    inspector = inspect(db.engine)
    _add_column_if_missing(inspector, "note", "folder", "VARCHAR(100)")


def _add_column_if_missing(inspector, table: str, column: str, sql_type: str) -> None:
    if table not in inspector.get_table_names():
        return  # a fresh DB — db.create_all() already created it with every column
    existing = {c["name"] for c in inspector.get_columns(table)}
    if column in existing:
        return
    db.session.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
    db.session.commit()


def _register_security(app: Flask) -> None:
    """Lightweight, dependency-free CSRF mitigation + security headers.

    Every state-changing request (POST/PUT/PATCH/DELETE) to our own JSON API
    must come from our own frontend: the fetch() helper in static/js always
    sets X-Requested-With, and we cross-check the Origin/Referer host against
    the request's own Host. A cross-site form/page can't set that custom
    header, and can't spoof Origin, so this blocks cross-site request forgery
    without needing per-form tokens (there are no traditional HTML forms in
    this app — every mutation goes through fetch()).
    """

    @app.before_request
    def check_same_origin():
        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return None
        if not request.path.startswith("/api/") and not request.path.startswith("/spotify/"):
            return None

        if request.headers.get("X-Requested-With") != "fetch":
            abort(403, description="missing required header")

        origin = request.headers.get("Origin") or request.headers.get("Referer")
        if origin:
            origin_host = urlparse(origin).netloc
            if origin_host and origin_host != request.host:
                abort(403, description="cross-origin request blocked")
        return None

    @app.after_request
    def set_security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def handle_error(err):
        if request.path.startswith("/api/"):
            code = getattr(err, "code", 500)
            description = getattr(err, "description", "error")
            return jsonify({"error": description}), code
        return err


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=app.config["DEBUG"])
