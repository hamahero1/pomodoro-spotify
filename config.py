"""App configuration, loaded from environment variables (.env in dev)."""
import os
import secrets

from dotenv import load_dotenv

load_dotenv()


def _require(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return value


class Config:
    # In dev, fall back to a random key so the app still runs without setup;
    # in production this MUST be set explicitly (sessions/tokens depend on it).
    FLASK_ENV = os.environ.get("FLASK_ENV", "development")
    DEBUG = os.environ.get("FLASK_DEBUG", "1") == "1"

    if FLASK_ENV == "production":
        SECRET_KEY = _require("SECRET_KEY")
    else:
        SECRET_KEY = os.environ.get("SECRET_KEY") or secrets.token_hex(32)

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///pomodoro.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Spotify OAuth
    SPOTIFY_CLIENT_ID = os.environ.get("SPOTIFY_CLIENT_ID", "")
    SPOTIFY_CLIENT_SECRET = os.environ.get("SPOTIFY_CLIENT_SECRET", "")
    SPOTIFY_REDIRECT_URI = os.environ.get(
        "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/spotify/callback"
    )
    SPOTIFY_SCOPES = " ".join(
        [
            "streaming",
            "user-read-email",
            "user-read-private",
            "user-read-playback-state",
            "user-modify-playback-state",
            "user-read-currently-playing",
        ]
    )

    # Cookies / session hardening
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = FLASK_ENV == "production"

    # Notes storage
    NOTES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notes", "files")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SPOTIFY_CLIENT_ID = "test-client-id"
    SPOTIFY_CLIENT_SECRET = "test-client-secret"
    WTF_CSRF_ENABLED = False
