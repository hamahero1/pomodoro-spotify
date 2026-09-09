import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import create_app
from config import TestConfig
from extensions import db


@pytest.fixture()
def app(tmp_path):
    application = create_app(TestConfig)
    application.config["NOTES_DIR"] = str(tmp_path / "notes")

    with application.app_context():
        db.create_all()
        yield application
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def api_headers():
    return {"X-Requested-With": "fetch", "Content-Type": "application/json"}
