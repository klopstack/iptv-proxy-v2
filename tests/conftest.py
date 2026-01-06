"""
Pytest configuration and shared fixtures for test suite

Provides Flask app, database, and client fixtures for testing.
"""
import os
import sys
from pathlib import Path

import pytest

# Add parent directory to path so we can import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set test database URI BEFORE importing app
# Use file-based database for testing to ensure proper connection handling
# This avoids in-memory database connection issues with nested app contexts
os.environ["DATABASE_URL"] = "sqlite:///test.db"

# Import app and models AFTER setting environment
import app as app_module
from models import db as _db


@pytest.fixture(scope="function")
def app():
    """
    Create Flask app configured for testing

    Uses SQLite file-based database that's reset between tests.
    """
    # Get the Flask app instance
    flask_app = app_module.app

    # Configure for testing
    flask_app.config["TESTING"] = True

    # Create all tables
    with flask_app.app_context():
        _db.create_all()
        yield flask_app
        # Properly dispose of all connections before dropping tables
        # This prevents "database is locked" errors with SQLite
        _db.session.remove()
        _db.engine.dispose()
        _db.drop_all()

    # Clean up test database file
    import pathlib

    test_db = pathlib.Path("test.db")
    if test_db.exists():
        test_db.unlink()


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
