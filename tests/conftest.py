"""
Pytest configuration and shared fixtures for test suite

Provides Flask app, database, and client fixtures for testing.
"""
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path so we can import app modules
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Use an absolute, dedicated test DB path so stale repo-root or instance/test.db
# files cannot interfere regardless of working directory or leftover WAL files.
TEST_DB_PATH = PROJECT_ROOT / "instance" / "pytest.db"


def _cleanup_test_db() -> None:
    """Remove the test database and any SQLite WAL/SHM sidecar files."""
    for suffix in ("", "-wal", "-shm"):
        db_file = Path(f"{TEST_DB_PATH}{suffix}")
        if db_file.exists():
            db_file.unlink()


def _reset_test_db(flask_app) -> None:
    """Close all DB connections, then remove the test database files."""
    with flask_app.app_context():
        _db.session.remove()
        _db.engine.dispose()
    _cleanup_test_db()


# Set test database URI BEFORE importing app
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Import app and models AFTER setting environment
import app as app_module
from models import db as _db


@pytest.fixture(scope="function")
def app():
    """
    Create Flask app configured for testing

    Uses SQLite file-based database that's reset between tests.
    """
    flask_app = app_module.app
    flask_app.config["TESTING"] = True

    _reset_test_db(flask_app)

    # Create all tables
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        # Properly dispose of all connections before dropping tables
        # This prevents "database is locked" errors with SQLite
        _db.session.remove()
        _db.engine.dispose()
        _db.drop_all()
        _db.engine.dispose()

    _cleanup_test_db()


@pytest.fixture(scope="function")
def client(app):
    """
    Flask test client for making HTTP requests

    Use client.get(), client.post(), etc. to test routes.
    """
    return app.test_client()


@pytest.fixture(scope="function")
def db(app):
    """
    Database fixture with app context

    Provides access to db.session for direct database operations.
    """
    with app.app_context():
        yield _db
