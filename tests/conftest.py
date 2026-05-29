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
os.environ["DISABLE_IN_WORKER_SCHEDULER"] = "true"
TEST_DB_PATH.parent.mkdir(parents=True, exist_ok=True)

# Import app and models AFTER setting environment
import app as app_module
from models import Account, Category, Channel, Credential
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


@pytest.fixture
def test_account(app):
    """Standard enabled account with credentials."""
    with app.app_context():
        account = Account(
            name="Test Account",
            server="example.com",
            enabled=True,
        )
        _db.session.add(account)
        _db.session.flush()
        cred = Credential(
            account_id=account.id, username="test_user", password="test_pass", max_connections=1, enabled=True
        )
        _db.session.add(cred)
        _db.session.commit()
        yield account.id


@pytest.fixture
def test_category(app, test_account):
    """Standard test category for test_account."""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="cat1",
            category_name="Test Category",
        )
        _db.session.add(category)
        _db.session.commit()
        yield category.id


@pytest.fixture
def test_account_with_channels(app, test_account, test_category):
    """Standard enabled account with a category and sample channels."""
    with app.app_context():
        for i in range(5):
            channel = Channel(
                account_id=test_account,
                stream_id=f"ch{i}",
                name=f"Test Channel {i}",
                cleaned_name=f"Test Channel {i}",
                category_id=test_category,
                is_active=True,
                is_visible=True,
            )
            _db.session.add(channel)
        _db.session.commit()
        yield test_account
