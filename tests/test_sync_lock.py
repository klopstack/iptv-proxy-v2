"""Tests for sync lock functionality"""
from datetime import datetime, timedelta, timezone

import pytest

from models import Account, db
from services.sync_service import recover_stale_sync_locks, sync_lock


class TestSyncLock:
    """Test sync lock context manager"""

    def test_sync_lock_acquires_and_releases(self, app):
        """Test that sync lock properly acquires and releases"""
        with app.app_context():
            # Create test account
            account = Account(name="Test Account", server="example.com:8080", username="test", password="test123")
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Verify initial state
            account = db.session.get(Account, account_id)
            assert account.sync_in_progress is False

            # Acquire lock
            with sync_lock(account_id):
                # Verify lock is acquired
                account = db.session.get(Account, account_id)
                assert account.sync_in_progress is True
                assert account.sync_started_at is not None

            # Verify lock is released
            account = db.session.get(Account, account_id)
            assert account.sync_in_progress is False
            assert account.sync_started_at is None

    def test_sync_lock_prevents_concurrent_sync(self, app):
        """Test that sync lock prevents concurrent syncs"""
        with app.app_context():
            # Create test account
            account = Account(name="Test Account", server="example.com:8080", username="test", password="test123")
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Acquire lock
            with sync_lock(account_id):
                # Try to acquire lock again - should fail
                with pytest.raises(ValueError, match="already in progress"):
                    with sync_lock(account_id):
                        pass

    def test_sync_lock_releases_on_exception(self, app):
        """Test that sync lock is released even if exception occurs"""
        with app.app_context():
            # Create test account
            account = Account(name="Test Account", server="example.com:8080", username="test", password="test123")
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Acquire lock and raise exception
            try:
                with sync_lock(account_id):
                    account = db.session.get(Account, account_id)
                    assert account.sync_in_progress is True
                    raise RuntimeError("Test exception")
            except RuntimeError:
                pass

            # Verify lock was released despite exception
            account = db.session.get(Account, account_id)
            assert account.sync_in_progress is False

    def test_sync_lock_nonexistent_account(self, app):
        """Test that sync lock fails gracefully for nonexistent account"""
        with app.app_context():
            with pytest.raises(ValueError, match="not found"):
                with sync_lock(99999):
                    pass

    def test_sync_endpoint_returns_409_when_locked(self, app, client):
        """Test that sync endpoint returns 409 when account is already syncing"""
        with app.app_context():
            # Create test account
            account = Account(name="Test Account", server="example.com:8080", username="test", password="test123")
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            # Acquire lock manually
            account = db.session.get(Account, account_id)
            account.sync_in_progress = True
            db.session.commit()

            try:
                # Try to sync - should get 409
                response = client.post(f"/api/accounts/{account_id}/sync")
                assert response.status_code == 409
                assert "already in progress" in response.json["error"].lower()
            finally:
                # Clean up
                account = db.session.get(Account, account_id)
                account.sync_in_progress = False
                account.sync_started_at = None
                db.session.commit()

    def test_atomic_lock_claim_fails_when_already_locked(self, app):
        """Second atomic claim fails when lock is held."""
        with app.app_context():
            account = Account(name="Locked", server="example.com:8080", username="t", password="t")
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            account.sync_in_progress = True
            account.sync_started_at = now
            db.session.commit()

            with pytest.raises(ValueError, match="already in progress"):
                with sync_lock(account_id):
                    pass

    def test_recover_stale_sync_locks(self, app):
        """Stale locks older than threshold are cleared on recovery."""
        with app.app_context():
            old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
            account = Account(
                name="Stale",
                server="example.com:8080",
                username="t",
                password="t",
                sync_in_progress=True,
                sync_started_at=old,
            )
            db.session.add(account)
            db.session.commit()

            recovered = recover_stale_sync_locks(max_age_minutes=30)
            assert recovered == 1

            account = db.session.get(Account, account.id)
            assert account.sync_in_progress is False
            assert account.sync_started_at is None
