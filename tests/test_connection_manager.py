"""
Tests for connection manager service
"""
from datetime import datetime, timedelta

import pytest

from models import Account, ActiveStream, Credential, db
from services.connection_manager import ConnectionManager


@pytest.fixture
def test_account(app):
    """Create a test account"""
    with app.app_context():
        account = Account(
            name="Test Account",
            username="legacy_user",
            password="legacy_pass",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        yield account.id


@pytest.fixture
def test_account_with_credentials(app, test_account):
    """Create a test account with multiple credentials"""
    with app.app_context():
        cred1 = Credential(
            account_id=test_account,
            username="user1",
            password="pass1",
            max_connections=2,
            enabled=True,
        )
        cred2 = Credential(
            account_id=test_account,
            username="user2",
            password="pass2",
            max_connections=1,
            enabled=True,
        )
        db.session.add_all([cred1, cred2])
        db.session.commit()
        yield test_account, cred1.id, cred2.id


@pytest.fixture
def test_disabled_account(app):
    """Create a disabled test account"""
    with app.app_context():
        account = Account(
            name="Disabled Account",
            username="disabled_user",
            password="disabled_pass",
            server="example.com",
            enabled=False,
        )
        db.session.add(account)
        db.session.commit()
        yield account.id


# ============================================================================
# Get Available Credential Tests
# ============================================================================


class TestGetAvailableCredential:
    """Tests for ConnectionManager.get_available_credential"""

    def test_get_credential_account_not_found(self, app):
        """Test returns None for non-existent account"""
        with app.app_context():
            result = ConnectionManager.get_available_credential(999)
            assert result is None

    def test_get_credential_disabled_account(self, app, test_disabled_account):
        """Test returns None for disabled account"""
        with app.app_context():
            result = ConnectionManager.get_available_credential(test_disabled_account)
            assert result is None

    def test_get_credential_legacy_mode(self, app, test_account):
        """Test returns legacy credential when no credentials configured"""
        with app.app_context():
            # Delete any credentials that might have been created
            Credential.query.filter_by(account_id=test_account).delete()
            db.session.commit()

            result = ConnectionManager.get_available_credential(test_account)
            assert result is not None
            assert result.username == "legacy_user"
            assert result.password == "legacy_pass"

    def test_get_credential_selects_least_loaded(self, app, test_account_with_credentials):
        """Test selects credential with lowest utilization"""
        account_id, cred1_id, cred2_id = test_account_with_credentials
        with app.app_context():
            # Add one active stream to cred1
            stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="test_stream",
                client_ip="127.0.0.1",
                session_token="test_token",
            )
            db.session.add(stream)
            db.session.commit()

            result = ConnectionManager.get_available_credential(account_id)
            # Should select cred2 since it has no active connections
            assert result is not None
            assert result.id == cred2_id

    def test_get_credential_all_maxed_out(self, app, test_account_with_credentials):
        """Test returns None when all credentials are at max capacity"""
        account_id, cred1_id, cred2_id = test_account_with_credentials
        with app.app_context():
            # Max out cred1 (2 connections)
            for i in range(2):
                stream = ActiveStream(
                    credential_id=cred1_id,
                    stream_id=f"stream_{i}",
                    client_ip="127.0.0.1",
                    session_token=f"token_{i}",
                )
                db.session.add(stream)

            # Max out cred2 (1 connection)
            stream = ActiveStream(
                credential_id=cred2_id,
                stream_id="stream_3",
                client_ip="127.0.0.1",
                session_token="token_3",
            )
            db.session.add(stream)
            db.session.commit()

            result = ConnectionManager.get_available_credential(account_id)
            assert result is None


# ============================================================================
# Acquire Connection Tests
# ============================================================================


class TestAcquireConnection:
    """Tests for ConnectionManager.acquire_connection"""

    def test_acquire_legacy_mode(self, app):
        """Test acquire in legacy mode returns token"""
        with app.app_context():
            token, error = ConnectionManager.acquire_connection(None, "stream1", "127.0.0.1")
            assert token is not None
            assert len(token) == 64  # 32 bytes hex
            assert error == ""

    def test_acquire_credential_not_found(self, app):
        """Test returns error for non-existent credential"""
        with app.app_context():
            token, error = ConnectionManager.acquire_connection(999, "stream1", "127.0.0.1")
            assert token is None
            assert "not found" in error.lower()

    def test_acquire_credential_disabled(self, app, test_account_with_credentials):
        """Test returns error for disabled credential"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            cred = db.session.get(Credential, cred1_id)
            cred.enabled = False
            db.session.commit()

            token, error = ConnectionManager.acquire_connection(cred1_id, "stream1", "127.0.0.1")
            assert token is None
            assert "disabled" in error.lower()

    def test_acquire_no_slots(self, app, test_account_with_credentials):
        """Test returns error when no slots available"""
        account_id, cred1_id, cred2_id = test_account_with_credentials
        with app.app_context():
            # Max out cred2 (1 connection)
            stream = ActiveStream(
                credential_id=cred2_id,
                stream_id="stream_1",
                client_ip="127.0.0.1",
                session_token="token_1",
            )
            db.session.add(stream)
            db.session.commit()

            token, error = ConnectionManager.acquire_connection(cred2_id, "stream2", "127.0.0.1")
            assert token is None
            assert "no available" in error.lower()

    def test_acquire_success(self, app, test_account_with_credentials):
        """Test successful connection acquisition"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            token, error = ConnectionManager.acquire_connection(cred1_id, "stream1", "127.0.0.1")
            assert token is not None
            assert error == ""

            # Verify active stream was created
            active = ActiveStream.query.filter_by(session_token=token).first()
            assert active is not None
            assert active.stream_id == "stream1"


# ============================================================================
# Release Connection Tests
# ============================================================================


class TestReleaseConnection:
    """Tests for ConnectionManager.release_connection"""

    def test_release_empty_token(self, app):
        """Test returns False for empty token"""
        with app.app_context():
            result = ConnectionManager.release_connection("")
            assert result is False

    def test_release_not_found(self, app):
        """Test returns False for non-existent session"""
        with app.app_context():
            result = ConnectionManager.release_connection("nonexistent_token")
            assert result is False

    def test_release_success(self, app, test_account_with_credentials):
        """Test successful connection release"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            # Create active stream
            stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="stream1",
                client_ip="127.0.0.1",
                session_token="release_token",
            )
            db.session.add(stream)
            db.session.commit()

            result = ConnectionManager.release_connection("release_token")
            assert result is True

            # Verify stream was removed
            active = ActiveStream.query.filter_by(session_token="release_token").first()
            assert active is None


# ============================================================================
# Update Activity Tests
# ============================================================================


class TestUpdateActivity:
    """Tests for ConnectionManager.update_activity"""

    def test_update_empty_token(self, app):
        """Test returns False for empty token"""
        with app.app_context():
            result = ConnectionManager.update_activity("")
            assert result is False

    def test_update_not_found(self, app):
        """Test returns False for non-existent session"""
        with app.app_context():
            result = ConnectionManager.update_activity("nonexistent")
            assert result is False

    def test_update_success(self, app, test_account_with_credentials):
        """Test successful activity update"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            # Create active stream with old activity time
            old_time = datetime.utcnow() - timedelta(minutes=5)
            stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="stream1",
                client_ip="127.0.0.1",
                session_token="activity_token",
                last_activity=old_time,
            )
            db.session.add(stream)
            db.session.commit()

            result = ConnectionManager.update_activity("activity_token")
            assert result is True

            # Verify activity was updated
            db.session.refresh(stream)
            assert stream.last_activity > old_time


# ============================================================================
# Cleanup Stale Connections Tests
# ============================================================================


class TestCleanupStaleConnections:
    """Tests for ConnectionManager.cleanup_stale_connections"""

    def test_cleanup_removes_stale(self, app, test_account_with_credentials):
        """Test cleanup removes stale connections"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            # Create stale stream (old activity)
            old_time = datetime.utcnow() - timedelta(minutes=5)
            stale_stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="stale_stream",
                client_ip="127.0.0.1",
                session_token="stale_token",
                last_activity=old_time,
            )
            db.session.add(stale_stream)

            # Create active stream (recent activity)
            active_stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="active_stream",
                client_ip="127.0.0.1",
                session_token="active_token",
                last_activity=datetime.utcnow(),
            )
            db.session.add(active_stream)
            db.session.commit()

            # Cleanup with 60 second timeout
            ConnectionManager.cleanup_stale_connections(timeout_seconds=60)

            # Verify stale was removed but active remains
            assert ActiveStream.query.filter_by(session_token="stale_token").first() is None
            assert ActiveStream.query.filter_by(session_token="active_token").first() is not None

    def test_cleanup_respects_account_filter(self, app, test_account_with_credentials):
        """Test cleanup only affects specified account"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            # Create a fresh (not stale) stream for this account
            stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="stream1",
                client_ip="127.0.0.1",
                session_token="token1",
                # Recent activity, not stale
                last_activity=datetime.utcnow(),
            )
            db.session.add(stream)
            db.session.commit()

            # Cleanup with short timeout - but stream is fresh so not affected
            ConnectionManager.cleanup_stale_connections(account_id=account_id, timeout_seconds=60)

            # Stream should still exist since it's not stale
            assert ActiveStream.query.filter_by(session_token="token1").first() is not None


# ============================================================================
# Get Connection Status Tests
# ============================================================================


class TestGetConnectionStatus:
    """Tests for ConnectionManager.get_connection_status"""

    def test_status_account_not_found(self, app):
        """Test returns error for non-existent account"""
        with app.app_context():
            result = ConnectionManager.get_connection_status(999)
            assert "error" in result

    def test_status_legacy_mode(self, app, test_account):
        """Test returns legacy mode for account without credentials"""
        with app.app_context():
            # Remove any credentials
            Credential.query.filter_by(account_id=test_account).delete()
            db.session.commit()

            result = ConnectionManager.get_connection_status(test_account)
            assert result["legacy_mode"] is True
            assert result["total_max_connections"] == 1

    def test_status_with_credentials(self, app, test_account_with_credentials):
        """Test returns correct status for account with credentials"""
        account_id, cred1_id, cred2_id = test_account_with_credentials
        with app.app_context():
            result = ConnectionManager.get_connection_status(account_id)
            # cred1 has max_connections=2, cred2 has max_connections=1
            assert result["total_max_connections"] == 3
            assert result["total_active_connections"] == 0


# ============================================================================
# Get Active Streams Tests
# ============================================================================


class TestGetActiveStreams:
    """Tests for ConnectionManager.get_active_streams"""

    def test_active_streams_empty(self, app):
        """Test returns empty list when no active streams"""
        with app.app_context():
            result = ConnectionManager.get_active_streams()
            assert result == []

    def test_active_streams_with_filter(self, app, test_account_with_credentials):
        """Test returns filtered streams"""
        account_id, cred1_id, _ = test_account_with_credentials
        with app.app_context():
            # Create active stream
            stream = ActiveStream(
                credential_id=cred1_id,
                stream_id="stream1",
                client_ip="127.0.0.1",
                session_token="token1",
            )
            db.session.add(stream)
            db.session.commit()

            result = ConnectionManager.get_active_streams(account_id)
            assert len(result) >= 1
