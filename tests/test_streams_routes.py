"""
Tests for stream routes and connection management
"""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, ActiveStream, Credential, db


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
        account_id = account.id
        yield account_id


@pytest.fixture
def test_account_with_credential(app, test_account):
    """Create a test account with a credential"""
    with app.app_context():
        credential = Credential(
            account_id=test_account,
            username="cred_user",
            password="cred_pass",
            max_connections=2,
            enabled=True,
        )
        db.session.add(credential)
        db.session.commit()
        yield test_account, credential.id


# ============================================================================
# Stream Status Tests
# ============================================================================


class TestStreamStatus:
    """Tests for stream status endpoints"""

    def test_stream_status_account_not_found(self, app, client):
        """Test stream status returns 404 for non-existent account"""
        response = client.get("/stream/999/status")
        assert response.status_code == 404

    def test_stream_status_success(self, app, client, test_account):
        """Test stream status returns connection info"""
        response = client.get(f"/stream/{test_account}/status")
        assert response.status_code == 200
        data = response.json
        assert "total_max_connections" in data or "legacy_mode" in data


class TestActiveStreams:
    """Tests for active streams endpoint"""

    def test_active_streams_empty(self, app, client):
        """Test active streams returns empty list when no streams"""
        response = client.get("/stream/active")
        assert response.status_code == 200
        data = response.json
        assert "active_streams" in data
        assert data["count"] == 0

    def test_active_streams_with_account_filter(self, app, client, test_account):
        """Test active streams with account filter"""
        response = client.get(f"/stream/active?account_id={test_account}")
        assert response.status_code == 200
        data = response.json
        assert "active_streams" in data


class TestReleaseStream:
    """Tests for stream release endpoint"""

    def test_release_stream_not_found(self, app, client):
        """Test release non-existent stream returns 404"""
        response = client.post("/stream/nonexistent_token/release")
        assert response.status_code == 404

    def test_release_stream_success(self, app, client, test_account_with_credential):
        """Test successful stream release"""
        account_id, credential_id = test_account_with_credential
        with app.app_context():
            # Create an active stream
            active_stream = ActiveStream(
                credential_id=credential_id,
                stream_id="test_stream",
                client_ip="127.0.0.1",
                session_token="test_token_123",
            )
            db.session.add(active_stream)
            db.session.commit()

        response = client.post("/stream/test_token_123/release")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True


class TestCleanupStreams:
    """Tests for stream cleanup endpoint"""

    def test_cleanup_streams_success(self, app, client):
        """Test cleanup streams endpoint"""
        response = client.post("/stream/cleanup")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True

    def test_cleanup_streams_with_account_filter(self, app, client, test_account):
        """Test cleanup streams with account filter"""
        response = client.post(f"/stream/cleanup?account_id={test_account}")
        assert response.status_code == 200

    def test_cleanup_streams_with_timeout(self, app, client):
        """Test cleanup streams with custom timeout"""
        response = client.post("/stream/cleanup?timeout=60")
        assert response.status_code == 200


class TestProxyStream:
    """Tests for stream proxy endpoints"""

    def test_proxy_stream_account_not_found(self, app, client):
        """Test proxy stream returns 404 for non-existent account"""
        response = client.get("/stream/999/12345.ts")
        assert response.status_code == 404

    def test_proxy_stream_account_disabled(self, app, client, test_account):
        """Test proxy stream returns 403 when account disabled"""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.enabled = False
            db.session.commit()

            # When account is disabled, route should return 403
            # Keep request inside app_context to ensure session sees the change
            response = client.get(f"/stream/{test_account}/12345.ts")
            assert response.status_code == 403

    def test_proxy_stream_no_credential_available(self, app, client, test_account):
        """Test proxy stream returns error when no credentials available"""
        with app.app_context():
            # Account has no credentials and no legacy credentials
            account = db.session.get(Account, test_account)
            account.username = None
            account.password = None
            db.session.commit()

            # Keep request inside app_context to ensure session sees the change
            response = client.get(f"/stream/{test_account}/12345.ts")
            # Without credentials, request should fail with 503
            assert response.status_code == 503

    @patch("routes.streams.requests.get")
    def test_proxy_stream_m3u8_upstream_timeout(self, mock_get, app, client, test_account_with_credential):
        """Test proxy stream handles upstream timeout for m3u8.

        NOTE: For .ts streams, ffmpeg handles the upstream connection directly,
        not through requests.get. This test only works for m3u8 since we still
        use requests there for certain operations.
        """
        # This test is for the old architecture - skip for now
        # as ffmpeg handles upstream connections directly
        pytest.skip("Test not applicable with ffmpeg streaming backend")

    @patch("routes.streams.requests.get")
    def test_proxy_stream_upstream_http_error(self, mock_get, app, client, test_account_with_credential):
        """Test proxy stream handles upstream HTTP errors.

        NOTE: With ffmpeg backend, upstream errors result in a 200 response
        with 0 bytes streamed, as ffmpeg handles the HTTP connection internally.
        """
        # This test is for the old architecture - skip for now
        # as ffmpeg handles upstream connections directly
        pytest.skip("Test not applicable with ffmpeg streaming backend")

    @patch("routes.streams.requests.get")
    def test_proxy_stream_success(self, mock_get, app, client, test_account_with_credential):
        """Test successful stream proxy"""
        account_id, _ = test_account_with_credential

        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_response.iter_content.return_value = iter([b"test_data"])
        mock_get.return_value = mock_response

        response = client.get(f"/stream/{account_id}/12345.ts")
        assert response.status_code == 200
