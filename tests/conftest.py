"""
Pytest configuration and shared fixtures for test suite

Provides Flask app, database, and client fixtures for testing.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import text

# Add parent directory to path so we can import app modules
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_DEFAULT_SQLITE_PATH = PROJECT_ROOT / "instance" / "pytest.db"


def _resolve_test_db_url() -> str:
    """Resolve test DATABASE_URL; SQLite gets per-xdist-worker files."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        worker = os.environ.get("PYTEST_XDIST_WORKER")
        if worker and worker != "master":
            path = PROJECT_ROOT / "instance" / f"pytest_{worker}.db"
        else:
            path = _DEFAULT_SQLITE_PATH
        return f"sqlite:///{path}"

    if url.startswith("sqlite:///"):
        worker = os.environ.get("PYTEST_XDIST_WORKER")
        if worker and worker != "master":
            base = Path(url.replace("sqlite:///", ""))
            path = base.with_name(f"{base.stem}_{worker}{base.suffix}")
            return f"sqlite:///{path}"
    return url


TEST_DB_URL = _resolve_test_db_url()


def is_sqlite_backend() -> bool:
    return TEST_DB_URL.startswith("sqlite")


def _sqlite_path_from_url() -> Path:
    return Path(TEST_DB_URL.replace("sqlite:///", ""))


def _cleanup_test_db() -> None:
    """Remove SQLite test database and WAL/SHM sidecar files."""
    if not is_sqlite_backend():
        return
    path = _sqlite_path_from_url()
    for suffix in ("", "-wal", "-shm"):
        db_file = Path(f"{path}{suffix}")
        if db_file.exists():
            db_file.unlink()


def _reset_pg_database(engine) -> None:
    """Drop and recreate public schema (cleaner than drop_all on PostgreSQL)."""
    engine.dispose()
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.execute(text("GRANT ALL ON SCHEMA public TO public"))
        db_user = engine.url.username
        if db_user:
            conn.execute(text(f'GRANT ALL ON SCHEMA public TO "{db_user}"'))


def _reset_test_db(flask_app) -> None:
    """Close connections and reset the test database."""
    with flask_app.app_context():
        _db.session.remove()
        _db.engine.dispose()
        if not is_sqlite_backend():
            _reset_pg_database(_db.engine)
            _db.engine.dispose()
            return
    _cleanup_test_db()


def pytest_configure(config):
    config.addinivalue_line("markers", "sqlite_only: test requires SQLite backend")


def pytest_runtest_setup(item):
    if "sqlite_only" in item.keywords and not is_sqlite_backend():
        pytest.skip("requires SQLite backend")


# Set test database URI BEFORE importing app
os.environ["DATABASE_URL"] = TEST_DB_URL
os.environ["DISABLE_IN_WORKER_SCHEDULER"] = "true"
if not is_sqlite_backend():
    os.environ["IPTV_PG_TEST"] = "1"
if is_sqlite_backend():
    _sqlite_path_from_url().parent.mkdir(parents=True, exist_ok=True)

# Import app and models AFTER setting environment
import app as app_module
from models import Account, Category, Channel, Credential, EpgSource
from models import db as _db


@pytest.fixture(scope="function")
def app():
    """
    Create Flask app configured for testing

    Uses SQLite file-based database or PostgreSQL per DATABASE_URL.
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
        if is_sqlite_backend():
            _db.drop_all()
            _db.engine.dispose()
        # PostgreSQL: next test's setup resets via DROP SCHEMA; skip teardown to avoid deadlocks

    if is_sqlite_backend():
        _cleanup_test_db()


@pytest.fixture(scope="function")
def client(app):
    """
    Flask test client for making HTTP requests

    Use client.get(), client.post(), etc. to test routes.
    """
    return app.test_client()


def api_data(response):
    """Extract ``data`` from a standardized collection/resource GET response."""
    payload = response.get_json()
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def api_mutation_data(response):
    """Extract ``data`` from a standardized mutation success response."""
    payload = response.get_json()
    if isinstance(payload, dict) and payload.get("success") and "data" in payload:
        return payload["data"]
    return payload


def api_error_payload(response):
    """Return parsed JSON error body (standardized envelope)."""
    return response.get_json()


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


@pytest.fixture(autouse=True)
def _no_live_thesportsdb_v2_in_unit_tests(request):
    """
    TheSportsDB unit tests must not hit the live V2 API when THESPORTSDB_API_KEY is set.

    Service tests patch call_thesportsdb_api; this guards retry/api modules that still
    invoke try_v2_sdk_call before the V1 SDK path.
    """
    node_path = Path(str(getattr(request.node, "path", request.node.fspath)))
    if node_path.name.startswith("test_thesportsdb"):
        with patch("services.thesportsdb_api.try_v2_sdk_call", return_value=None):
            yield
    else:
        yield


@pytest.fixture
def sample_account(client):
    """Create a sample account and return its API resource dict."""
    response = client.post(
        "/api/accounts",
        json={
            "name": "Test Account",
            "server": "test.server.com",
            "username": "testuser",
            "password": "testpass",
            "enabled": True,
        },
    )
    return api_mutation_data(response)


@pytest.fixture
def test_epg_source(app, test_account):
    """Create a baseline XMLTV URL EPG source (returns source id)."""
    with app.app_context():
        source = EpgSource(
            name="Test EPG Source",
            source_type="xmltv_url",
            url="http://example.com/epg.xml",
            priority=100,
            enabled=True,
        )
        _db.session.add(source)
        _db.session.commit()
        yield source.id
