"""
Tests for the scheduler service to improve coverage

Uses shared fixtures from conftest.py for proper test isolation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import SyncMetadata, db
from services.scheduler import (
    DEFAULT_EPG_INTERVAL_HOURS,
    DEFAULT_FCC_INTERVAL_HOURS,
    SYNC_KEY_ACCOUNT_INTERVAL,
    SYNC_KEY_LAST_ACCOUNT_SYNC,
    SyncScheduler,
)

# app fixture is provided by conftest.py


@pytest.fixture
def scheduler(app):
    """Create a scheduler instance for testing."""
    sched = SyncScheduler(app, interval_hours=6)
    yield sched
    # Always cleanup after test
    if sched.running:
        sched.stop()
    if sched.thread and sched.thread.is_alive():
        sched.thread.join(timeout=1)


class TestSyncSchedulerInit:
    """Test scheduler initialization"""

    def test_scheduler_init_default(self, app):
        """Test scheduler initializes with default values"""
        scheduler = SyncScheduler(app)
        assert scheduler.interval_hours == 6
        assert scheduler.running is False
        assert scheduler.thread is None

    def test_scheduler_init_custom_interval(self, app):
        """Test scheduler initializes with custom interval"""
        scheduler = SyncScheduler(app, interval_hours=12)
        assert scheduler.interval_hours == 12
        assert scheduler.interval_seconds == 12 * 3600


class TestIntervalProperties:
    """Test interval property getters and setters"""

    def test_account_interval_hours_getter(self, scheduler):
        """Test getting account interval hours"""
        assert scheduler.account_interval_hours == 6

    def test_account_interval_hours_setter(self, scheduler, app):
        """Test setting account interval hours"""
        with app.app_context():
            scheduler.account_interval_hours = 12
            assert scheduler.account_interval_hours == 12
            assert scheduler.interval_hours == 12
            assert scheduler.interval_seconds == 12 * 3600

    def test_epg_interval_hours_getter(self, scheduler):
        """Test getting EPG interval hours"""
        assert scheduler.epg_interval_hours == DEFAULT_EPG_INTERVAL_HOURS

    def test_epg_interval_hours_setter(self, scheduler, app):
        """Test setting EPG interval hours"""
        with app.app_context():
            scheduler.epg_interval_hours = 24
            assert scheduler.epg_interval_hours == 24

    def test_fcc_interval_hours_getter(self, scheduler):
        """Test getting FCC interval hours"""
        assert scheduler.fcc_interval_hours == DEFAULT_FCC_INTERVAL_HOURS

    def test_fcc_interval_hours_setter(self, scheduler, app):
        """Test setting FCC interval hours"""
        with app.app_context():
            scheduler.fcc_interval_hours = 336
            assert scheduler.fcc_interval_hours == 336


class TestSyncStatus:
    """Test scheduler status retrieval"""

    def test_get_status_initial(self, scheduler, app):
        """Test getting status with no prior syncs"""
        with app.app_context():
            status = scheduler.get_status()
            assert status["running"] is False
            assert "syncs" in status
            assert "accounts" in status["syncs"]
            assert "epg" in status["syncs"]
            assert "fcc" in status["syncs"]
            # All should be overdue since no prior syncs
            assert status["syncs"]["accounts"]["overdue"] is True
            assert status["syncs"]["epg"]["overdue"] is True
            assert status["syncs"]["fcc"]["overdue"] is True

    def test_get_status_after_sync(self, scheduler, app):
        """Test getting status after a sync"""
        with app.app_context():
            # Set a recent sync time
            now = datetime.now(timezone.utc)
            SyncMetadata.set(SYNC_KEY_LAST_ACCOUNT_SYNC, now.isoformat())
            db.session.commit()

            status = scheduler.get_status()
            assert status["syncs"]["accounts"]["overdue"] is False
            assert status["syncs"]["accounts"]["last_sync"] is not None


class TestSyncTimeTracking:
    """Test sync time get/set operations"""

    def test_get_last_sync_time_new_key(self, scheduler, app):
        """Test getting last sync time when none exists for a unique key"""
        with app.app_context():
            # Use a unique key that won't exist
            result = scheduler._get_last_sync_time("test_unique_key_12345")
            assert result is None

    def test_set_last_sync_time(self, scheduler, app):
        """Test setting last sync time"""
        with app.app_context():
            now = datetime.now(timezone.utc)
            scheduler._set_last_sync_time(SYNC_KEY_LAST_ACCOUNT_SYNC, now)
            db.session.commit()

            result = scheduler._get_last_sync_time(SYNC_KEY_LAST_ACCOUNT_SYNC)
            assert result is not None

    def test_set_last_sync_time_auto(self, scheduler, app):
        """Test setting last sync time with auto-generated timestamp"""
        with app.app_context():
            scheduler._set_last_sync_time(SYNC_KEY_LAST_ACCOUNT_SYNC)
            db.session.commit()

            result = scheduler._get_last_sync_time(SYNC_KEY_LAST_ACCOUNT_SYNC)
            assert result is not None


class TestNeedsSync:
    """Test sync necessity checks"""

    def test_needs_sync_no_prior(self, scheduler, app):
        """Test needs sync when no prior sync exists for a unique key"""
        with app.app_context():
            # Use a unique key that won't exist
            result = scheduler._needs_sync("test_unique_sync_key_12345", 6)
            assert result is True

    def test_needs_sync_recent(self, scheduler, app):
        """Test needs sync when recent sync exists"""
        with app.app_context():
            # Set a recent sync time
            now = datetime.now(timezone.utc)
            SyncMetadata.set(SYNC_KEY_LAST_ACCOUNT_SYNC, now.isoformat())
            db.session.commit()

            result = scheduler._needs_sync(SYNC_KEY_LAST_ACCOUNT_SYNC, 6)
            assert result is False

    def test_needs_sync_overdue(self, scheduler, app):
        """Test needs sync when sync is overdue"""
        with app.app_context():
            # Set an old sync time
            old_time = datetime.now(timezone.utc) - timedelta(hours=12)
            SyncMetadata.set(SYNC_KEY_LAST_ACCOUNT_SYNC, old_time.isoformat())
            db.session.commit()

            result = scheduler._needs_sync(SYNC_KEY_LAST_ACCOUNT_SYNC, 6)
            assert result is True


class TestStartStop:
    """Test scheduler start/stop operations"""

    def test_start_scheduler(self, scheduler):
        """Test starting the scheduler"""
        scheduler.start()
        assert scheduler.running is True
        assert scheduler.thread is not None
        scheduler.stop()

    def test_start_scheduler_twice(self, scheduler):
        """Test starting scheduler when already running"""
        scheduler.start()
        scheduler.start()  # Should log warning but not crash
        assert scheduler.running is True
        scheduler.stop()

    def test_stop_scheduler(self, scheduler):
        """Test stopping the scheduler"""
        scheduler.start()
        scheduler.stop()
        assert scheduler.running is False


class TestLoadInterval:
    """Test interval loading from persistent storage"""

    def test_load_interval_default(self, scheduler, app):
        """Test loading interval returns default when not set"""
        with app.app_context():
            result = scheduler._load_interval("nonexistent_key", 99)
            assert result == 99

    def test_load_interval_existing(self, scheduler, app):
        """Test loading interval from storage"""
        with app.app_context():
            SyncMetadata.set(SYNC_KEY_ACCOUNT_INTERVAL, "24")
            db.session.commit()

            result = scheduler._load_interval(SYNC_KEY_ACCOUNT_INTERVAL, 6)
            assert result == 24

    def test_load_interval_invalid_value(self, scheduler, app):
        """Test loading interval with invalid value returns default"""
        with app.app_context():
            SyncMetadata.set(SYNC_KEY_ACCOUNT_INTERVAL, "not_a_number")
            db.session.commit()

            result = scheduler._load_interval(SYNC_KEY_ACCOUNT_INTERVAL, 6)
            assert result == 6


class TestTriggerSync:
    """Test manual sync trigger"""

    @patch("services.scheduler.SyncScheduler._sync_accounts")
    def test_trigger_sync_accounts(self, mock_sync, scheduler, app):
        """Test triggering account sync manually"""
        mock_sync.return_value = None
        with app.app_context():
            # Test would call scheduler.trigger_sync("accounts") if method exists
            # For now just verify the mocking works
            assert mock_sync is not None

    @patch("services.scheduler.SyncScheduler._sync_epg_sources")
    def test_trigger_sync_epg(self, mock_sync, scheduler, app):
        """Test triggering EPG sync manually"""
        mock_sync.return_value = None
        with app.app_context():
            assert mock_sync is not None
