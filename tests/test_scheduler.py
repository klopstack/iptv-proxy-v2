"""
Tests for sync scheduler service
"""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, db
from services.scheduler import SyncScheduler


@pytest.fixture
def test_account(app):
    """Create a test account"""
    with app.app_context():
        account = Account(
            name="Test Account",
            username="test_user",
            password="test_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        yield account.id


class TestSyncScheduler:
    """Tests for SyncScheduler"""

    def test_scheduler_init(self, app):
        """Test scheduler initialization"""
        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=6)
            assert scheduler.interval_hours == 6
            assert scheduler.interval_seconds == 6 * 3600
            assert scheduler.running is False
            assert scheduler.thread is None

    def test_scheduler_start(self, app):
        """Test scheduler start"""
        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=1)

            # Mock the _run method to prevent actual thread execution
            with patch.object(scheduler, "_run"):
                scheduler.start()
                assert scheduler.running is True
                assert scheduler.thread is not None

                # Cleanup
                scheduler.stop()

    def test_scheduler_start_already_running(self, app, caplog):
        """Test scheduler warns when already running"""
        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=1)
            scheduler.running = True  # Simulate already running

            scheduler.start()
            assert "already running" in caplog.text.lower()

    def test_scheduler_stop(self, app):
        """Test scheduler stop"""
        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=1)
            scheduler.running = True
            scheduler.thread = MagicMock()

            scheduler.stop()
            assert scheduler.running is False
            scheduler.thread.join.assert_called_once()

    @patch("services.sync_service.ChannelSyncService.sync_account")
    def test_scheduler_sync_all(self, mock_sync, app, test_account):
        """Test scheduler syncs all enabled accounts"""
        mock_sync.return_value = {
            "channels_added": 10,
            "channels_updated": 5,
            "channels_deactivated": 2,
        }

        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=1)
            scheduler._sync_all()

            # Verify sync was called for the enabled account
            mock_sync.assert_called()

    @patch("services.sync_service.ChannelSyncService.sync_account")
    def test_scheduler_sync_handles_errors(self, mock_sync, app, test_account, caplog):
        """Test scheduler handles sync errors gracefully"""
        mock_sync.side_effect = Exception("Sync failed")

        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=1)
            # Should not raise exception
            scheduler._sync_all()
            assert "error" in caplog.text.lower()

    def test_scheduler_skips_disabled_accounts(self, app, test_account):
        """Test scheduler skips disabled accounts"""
        with app.app_context():
            # Disable the account
            account = db.session.get(Account, test_account)
            account.enabled = False
            db.session.commit()

            with patch("services.sync_service.ChannelSyncService.sync_account") as mock_sync:
                scheduler = SyncScheduler(app, interval_hours=1)
                scheduler._sync_all()

                # sync_account should not be called for disabled accounts
                mock_sync.assert_not_called()
