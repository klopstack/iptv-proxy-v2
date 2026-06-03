"""
Tests for the scheduler service to improve coverage

Uses shared fixtures from conftest.py for proper test isolation.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import Account, EpgSource, SyncMetadata, db
from services.scheduler import (
    DEFAULT_EPG_INTERVAL_HOURS,
    DEFAULT_FCC_INTERVAL_HOURS,
    SCHEDULER_HEARTBEAT_TIMEOUT_SECONDS,
    SYNC_KEY_ACCOUNT_INTERVAL,
    SYNC_KEY_LAST_ACCOUNT_SYNC,
    SYNC_KEY_LAST_FCC_SYNC,
    SYNC_KEY_LAST_PPV_PREFETCH,
    SYNC_KEY_SCHEDULER_HEARTBEAT,
    SyncScheduler,
)
from services.scheduler_lock import SchedulerLock
from services.scheduler_registry import JobDefinition, build_scheduled_jobs

# app fixture is provided by conftest.py


@pytest.fixture
def scheduler(app, tmp_path):
    """Create a scheduler instance for testing."""
    sched = SyncScheduler(app, interval_hours=6)
    sched._lock = SchedulerLock(tmp_path / "scheduler.lock")
    yield sched
    # Always cleanup after test
    if sched.running:
        sched.stop()
    if sched.thread and sched.thread.is_alive():
        sched.thread.join(timeout=1)


class TestSchedulerJobRegistry:
    """Declarative job registry (TODO 89)."""

    def test_build_scheduled_jobs_returns_expected_jobs(self):
        jobs = build_scheduled_jobs()
        assert len(jobs) == 8
        assert all(isinstance(job, JobDefinition) for job in jobs)
        assert jobs[0].status_key == "accounts"
        assert any(job.status_key == "fcc" for job in jobs)

    @patch("services.scheduler_jobs.accounts.ChannelSyncService.sync_account")
    def test_registry_accounts_job_delegates_to_accounts_module(self, mock_sync_account, scheduler, app):
        mock_sync_account.return_value = {
            "success": True,
            "channels_added": 0,
            "channels_updated": 0,
            "channels_deactivated": 0,
        }
        with app.app_context():
            account = Account(
                name="Registry Account",
                server="http://example.com",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            assert scheduler._sync_accounts() is True
            mock_sync_account.assert_called_once_with(account.id)

    @patch.object(SyncScheduler, "_run_scheduled_job_def")
    @patch.object(SyncScheduler, "_sync_epg_sources_if_due")
    @patch.object(SyncScheduler, "_scan_channel_health")
    def test_check_and_sync_uses_registry_and_runs_epg_after_accounts(
        self, _mock_health, mock_epg, mock_run_job_def, scheduler, app
    ):
        with app.app_context():
            scheduler._check_and_sync()
        assert mock_run_job_def.call_count == 8
        accounts_idx = next(
            i for i, call in enumerate(mock_run_job_def.call_args_list) if call[0][0].status_key == "accounts"
        )
        assert mock_run_job_def.call_args_list[accounts_idx][0][0].status_key == "accounts"
        mock_epg.assert_called_once()


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
            assert "epg_sources" in status
            assert isinstance(status["epg_sources"], list)
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
            assert status["syncs"]["accounts"]["last_sync"].endswith("Z")
            assert status["syncs"]["accounts"]["next_sync"].endswith("Z")
            assert status["syncs"]["accounts"]["last_run_status"] == "success"

    def test_get_status_includes_all_registered_jobs(self, scheduler, app):
        with app.app_context():
            status = scheduler.get_status()
            for job_name in (
                "accounts",
                "epg",
                "fcc",
                "ppv_prefetch",
                "ppv_enrichment",
                "ppv_time_refresh",
                "sportsipy_refresh",
                "epg_program_cleanup",
                "health_check_cleanup",
                "event_cleanup",
                "image_cache_cleanup",
            ):
                job = status["syncs"][job_name]
                assert "last_failure_at" in job
                assert "last_error" in job
                assert "last_run_status" in job
                assert "last_success_at" in job


class TestSchedulerFailureMetadata:
    """Scheduler job failure metadata (TODO 91)."""

    def test_record_failure_does_not_advance_success_timestamp(self, scheduler, app):
        with app.app_context():
            old = datetime.now(timezone.utc) - timedelta(hours=200)
            SyncMetadata.set(SYNC_KEY_LAST_FCC_SYNC, old.isoformat())
            db.session.commit()

            scheduler._record_sync_failure(SYNC_KEY_LAST_FCC_SYNC, "FCC timeout")

            result = scheduler._get_last_sync_time(SYNC_KEY_LAST_FCC_SYNC)
            assert result is not None
            assert abs((result - old).total_seconds()) < 2
            assert SyncMetadata.get(scheduler._failure_error_key(SYNC_KEY_LAST_FCC_SYNC)) == "FCC timeout"

    def test_get_status_includes_failure_fields(self, scheduler, app):
        with app.app_context():
            scheduler._record_sync_failure(SYNC_KEY_LAST_PPV_PREFETCH, "prefetch failed")

            status = scheduler.get_status()
            job = status["syncs"]["ppv_prefetch"]
            assert job["last_run_status"] == "error"
            assert job["last_error"] == "prefetch failed"
            assert job["last_failure_at"] is not None
            assert job["last_failure_at"].endswith("Z")

    def test_success_clears_last_error_retains_failure_at(self, scheduler, app):
        with app.app_context():
            scheduler._record_sync_failure(SYNC_KEY_LAST_FCC_SYNC, "temporary error")
            failure_at = SyncMetadata.get(scheduler._failure_at_key(SYNC_KEY_LAST_FCC_SYNC))

            scheduler._record_sync_success(SYNC_KEY_LAST_FCC_SYNC)
            now = datetime.now(timezone.utc)
            scheduler._set_last_sync_time(SYNC_KEY_LAST_FCC_SYNC, now)

            status = scheduler.get_status()["syncs"]["fcc"]
            assert status["last_run_status"] == "success"
            assert status["last_error"] is None
            assert SyncMetadata.get(scheduler._failure_error_key(SYNC_KEY_LAST_FCC_SYNC)) is None
            assert SyncMetadata.get(scheduler._failure_at_key(SYNC_KEY_LAST_FCC_SYNC)) == failure_at

    @patch("services.scheduler.SyncScheduler._sync_fcc_data", return_value=False)
    def test_check_and_sync_records_fcc_failure_metadata(self, _mock_fcc, scheduler, app):
        with app.app_context():
            old = datetime.now(timezone.utc) - timedelta(hours=200)
            SyncMetadata.set(SYNC_KEY_LAST_FCC_SYNC, old.isoformat())
            db.session.commit()

            def needs_fcc_only(key, _interval_hours):
                return key == SYNC_KEY_LAST_FCC_SYNC

            with patch.object(scheduler, "_needs_sync", side_effect=needs_fcc_only):
                with patch.object(scheduler, "_scan_channel_health"):
                    with patch.object(scheduler, "_sync_epg_sources_if_due"):
                        scheduler._check_and_sync()

            assert SyncMetadata.get(scheduler._failure_error_key(SYNC_KEY_LAST_FCC_SYNC)) == "Job returned failure"
            status = scheduler.get_status()["syncs"]["fcc"]
            assert status["last_run_status"] == "error"


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

    @patch.object(SyncScheduler, "_run")
    def test_start_scheduler(self, mock_run, scheduler):
        """Test starting the scheduler"""
        scheduler.start()
        assert scheduler.running is True
        assert scheduler.thread is not None
        scheduler.stop()
        mock_run.assert_called()

    @patch.object(SyncScheduler, "_run")
    def test_start_scheduler_twice(self, mock_run, scheduler):
        """Test starting scheduler when already running"""
        scheduler.start()
        scheduler.start()  # Should log warning but not crash
        assert scheduler.running is True
        scheduler.stop()

    @patch.object(SyncScheduler, "_run")
    def test_stop_scheduler(self, mock_run, scheduler):
        """Test stopping the scheduler"""
        scheduler.start()
        scheduler.stop()
        assert scheduler.running is False
        mock_run.assert_called()


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
    """Test scheduler-driven EPG sync"""

    @patch("services.scheduler_jobs.accounts.ChannelSyncService.sync_account")
    def test_sync_accounts_marks_success(self, mock_sync_account, scheduler, app):
        """Successful sync sets account last_sync_status to success."""
        mock_sync_account.return_value = {
            "success": True,
            "channels_added": 0,
            "channels_updated": 0,
            "channels_deactivated": 0,
        }
        with app.app_context():
            account = Account(
                name="Scheduler Sync OK",
                server="http://example.com",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            assert scheduler._sync_accounts() is True
            db.session.refresh(account)
            assert account.last_sync_status == "success"

    @patch("services.scheduler_jobs.accounts.ChannelSyncService.sync_account")
    def test_sync_accounts_marks_error_on_failure(self, mock_sync_account, scheduler, app):
        """Failed sync must not report success."""
        mock_sync_account.return_value = {
            "success": False,
            "channels_added": 0,
            "channels_updated": 0,
            "channels_deactivated": 0,
            "errors": ["Channels sync error: timeout"],
        }
        with app.app_context():
            account = Account(
                name="Scheduler Sync Fail",
                server="http://example.com",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            assert scheduler._sync_accounts() is False
            db.session.refresh(account)
            assert account.last_sync_status == "error"

    @patch("services.scheduler.SyncScheduler._sync_fcc_data", return_value=False)
    def test_check_and_sync_skips_fcc_timestamp_on_failure(self, _mock_fcc, scheduler, app):
        """Failed FCC sync must not advance last_fcc_sync metadata."""
        with app.app_context():
            old = datetime.now(timezone.utc) - timedelta(hours=200)
            SyncMetadata.set(SYNC_KEY_LAST_FCC_SYNC, old.isoformat())
            db.session.commit()

            def needs_fcc_only(key, _interval_hours):
                return key == SYNC_KEY_LAST_FCC_SYNC

            with patch.object(scheduler, "_needs_sync", side_effect=needs_fcc_only):
                with patch.object(scheduler, "_scan_channel_health"):
                    with patch.object(scheduler, "_sync_epg_sources_if_due"):
                        scheduler._check_and_sync()

            result = scheduler._get_last_sync_time(SYNC_KEY_LAST_FCC_SYNC)
            assert result is not None
            assert abs((result - old).total_seconds()) < 2

    @patch("services.scheduler.SyncScheduler._sync_fcc_data", return_value=True)
    def test_check_and_sync_advances_fcc_timestamp_on_success(self, _mock_fcc, scheduler, app):
        """Successful FCC sync advances last_fcc_sync metadata."""
        with app.app_context():
            old = datetime.now(timezone.utc) - timedelta(hours=200)
            SyncMetadata.set(SYNC_KEY_LAST_FCC_SYNC, old.isoformat())
            db.session.commit()

            def needs_fcc_only(key, _interval_hours):
                return key == SYNC_KEY_LAST_FCC_SYNC

            with patch.object(scheduler, "_needs_sync", side_effect=needs_fcc_only):
                with patch.object(scheduler, "_scan_channel_health"):
                    with patch.object(scheduler, "_sync_epg_sources_if_due"):
                        scheduler._check_and_sync()

            result = scheduler._get_last_sync_time(SYNC_KEY_LAST_FCC_SYNC)
            assert result is not None
            assert result > old

    @patch("services.epg_sync_orchestrator.EpgSyncOrchestrator.sync_due_sources")
    def test_sync_epg_sources_if_due_calls_orchestrator(self, mock_sync_due, scheduler, app):
        """Due enabled sources trigger orchestrator sync_due_sources."""
        with app.app_context():
            mock_sync_due.return_value = {
                "sources_synced": 1,
                "total_sources": 1,
                "sources_skipped": 0,
            }

            scheduler._sync_epg_sources_if_due()

            mock_sync_due.assert_called_once()
            assert mock_sync_due.call_args[0][0] == scheduler._epg_interval_hours
            assert mock_sync_due.call_args[1]["parallel"] is True

    @patch("services.epg_sync_orchestrator.EpgSyncOrchestrator.sync_sources")
    def test_sync_epg_sources_if_due_skips_fresh_sources(self, mock_sync_sources, scheduler, app):
        """Recently synced sources are not passed to the orchestrator."""
        with app.app_context():
            source = EpgSource(
                name="Fresh Scheduler Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
                last_sync=datetime.now(timezone.utc).replace(tzinfo=None),
            )
            db.session.add(source)
            db.session.commit()

            scheduler._sync_epg_sources_if_due()
            mock_sync_sources.assert_not_called()


class TestEnsureSchedulerStarted:
    """Scheduler startup is attempted on each request until this worker is running."""

    def test_ensure_scheduler_calls_start_when_not_running(self, app, monkeypatch):
        import app as app_module

        monkeypatch.setattr(app_module, "_disable_scheduler", False)
        monkeypatch.setattr(app_module, "_disable_in_worker_scheduler", False)
        starts = []

        monkeypatch.setattr(app_module.sync_scheduler, "running", False)
        monkeypatch.setattr(app_module.sync_scheduler, "start", lambda: starts.append(True))

        app_module._ensure_scheduler_started()
        assert starts == [True]

        monkeypatch.setattr(app_module.sync_scheduler, "running", True)
        app_module._ensure_scheduler_started()
        assert starts == [True]


class TestSchedulerLock:
    """Only one process in the container should hold the scheduler lock."""

    def test_second_lock_attempt_fails(self, tmp_path):
        from services.scheduler_lock import SchedulerLock

        lock_path = tmp_path / "scheduler.lock"
        first = SchedulerLock(lock_path)
        second = SchedulerLock(lock_path)

        assert first.try_acquire() is True
        assert second.try_acquire() is False

        first.release()
        assert second.try_acquire() is True
        second.release()


class TestSchedulerHeartbeat:
    """Heartbeat keeps scheduler status accurate during long sync work"""

    def test_is_scheduler_alive_with_recent_heartbeat(self, scheduler, app):
        with app.app_context():
            scheduler._touch_heartbeat()
            assert scheduler._is_scheduler_alive() is True

    def test_is_scheduler_alive_stale_heartbeat(self, scheduler, app):
        with app.app_context():
            stale = datetime.now(timezone.utc) - timedelta(seconds=SCHEDULER_HEARTBEAT_TIMEOUT_SECONDS + 60)
            SyncMetadata.set(SYNC_KEY_SCHEDULER_HEARTBEAT, stale.isoformat())
            assert scheduler._is_scheduler_alive() is False

    def test_get_status_running_during_long_sync(self, scheduler, app):
        """Status stays 'running' while sync work is in progress."""
        with app.app_context():

            def slow_accounts():
                scheduler._touch_heartbeat()
                SyncMetadata.set(
                    SYNC_KEY_SCHEDULER_HEARTBEAT,
                    (datetime.now(timezone.utc) - timedelta(seconds=300)).isoformat(),
                )
                scheduler._touch_heartbeat()

            def needs_sync_only_accounts(key, _interval_hours):
                return key == SYNC_KEY_LAST_ACCOUNT_SYNC

            with patch.object(scheduler, "_sync_accounts", side_effect=slow_accounts):
                with patch.object(scheduler, "_needs_sync", side_effect=needs_sync_only_accounts):
                    with patch.object(scheduler, "_set_last_sync_time"):
                        with patch.object(scheduler, "_scan_channel_health"):
                            with patch.object(scheduler, "_sync_epg_sources_if_due"):
                                scheduler._check_and_sync()

            assert scheduler.get_status()["running"] is True
