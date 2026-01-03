"""Tests for sync date service."""

import sqlite3
from datetime import datetime

import pytest

from services.sync_date_service import SyncDateService


class TestSyncDateService:
    """Tests for SyncDateService."""

    @pytest.fixture
    def temp_db(self, tmp_path):
        """Create a temporary database for testing."""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create sync_metadata table
        cursor.execute(
            """
            CREATE TABLE sync_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(255) UNIQUE NOT NULL,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.commit()
        conn.close()

        return db_path

    def test_get_last_sync_time_exists(self, temp_db):
        """Test getting last sync time when it exists."""
        # Insert a sync time
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        sync_time = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO sync_metadata (key, value) VALUES (?, ?)",
            ("last_account_sync", sync_time),
        )
        conn.commit()
        conn.close()

        result = SyncDateService.get_last_sync_time(temp_db)
        assert result is not None
        assert isinstance(result, datetime)

    def test_get_last_sync_time_with_z_timezone(self, temp_db):
        """Test parsing sync time with Z timezone."""
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        sync_time = "2026-01-02T10:30:00Z"
        cursor.execute(
            "INSERT INTO sync_metadata (key, value) VALUES (?, ?)",
            ("last_account_sync", sync_time),
        )
        conn.commit()
        conn.close()

        result = SyncDateService.get_last_sync_time(temp_db)
        assert result is not None
        assert isinstance(result, datetime)

    def test_get_last_sync_time_not_found(self, temp_db):
        """Test getting last sync time when it doesn't exist."""
        result = SyncDateService.get_last_sync_time(temp_db)
        assert result is None

    def test_get_last_sync_time_invalid_db(self):
        """Test getting last sync time with invalid database."""
        result = SyncDateService.get_last_sync_time("/nonexistent/path.db")
        assert result is None

    def test_get_reference_date_with_sync_time(self, temp_db):
        """Test getting reference date when sync time exists."""
        # Insert a sync time
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        sync_time = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO sync_metadata (key, value) VALUES (?, ?)",
            ("last_account_sync", sync_time),
        )
        conn.commit()
        conn.close()

        result = SyncDateService.get_reference_date(temp_db)
        assert result is not None
        assert isinstance(result, datetime)
        # Should be roughly the same time (within a few seconds)
        assert abs((result - datetime.now()).total_seconds()) < 5

    def test_get_reference_date_without_sync_time(self, temp_db):
        """Test getting reference date when sync time doesn't exist."""
        result = SyncDateService.get_reference_date(temp_db)
        assert result is not None
        assert isinstance(result, datetime)
        # Should be very close to now
        assert abs((result - datetime.now()).total_seconds()) < 1

    def test_get_reference_date_no_db_path(self, temp_db, monkeypatch):
        """Test getting reference date with no db_path provided."""
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{temp_db}")

        # Insert a sync time
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        sync_time = datetime.now().isoformat()
        cursor.execute(
            "INSERT INTO sync_metadata (key, value) VALUES (?, ?)",
            ("last_account_sync", sync_time),
        )
        conn.commit()
        conn.close()

        result = SyncDateService.get_reference_date(None)
        assert result is not None
        assert isinstance(result, datetime)
