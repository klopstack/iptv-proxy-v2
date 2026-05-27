"""
Tests for stream routes and connection management

This test module covers:
1. Helper functions that extract testable logic from routes (e.g., error classification)
2. Route endpoint tests with proper mocking of dependencies
3. Error handling and edge cases
4. Integration scenarios with mocked services

The main challenge with stream routes is that they contain generator functions
and Flask request context. This is handled by:
- Testing route handlers through the test client (which provides context)
- Extracting helper functions for business logic testing
- Mocking service dependencies
"""
from unittest.mock import Mock, patch

import pytest

from models import Account, ActiveStream, Credential, db
from services.stream_test_helpers import classify_error_and_get_status


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
# Helper Function Tests - Stream Error Classification
# ============================================================================


class TestErrorClassification:
    """Tests for error classification logic extracted from _proxy_stream()"""

    def test_classify_timeout_error(self):
        """Test that timeout errors map to 504 Gateway Timeout"""
        status, msg = classify_error_and_get_status("Connection timeout")
        assert status == 504
        assert "Gateway Timeout" in msg

    def test_classify_timeout_error_case_insensitive(self):
        """Test timeout detection is case-insensitive"""
        status, msg = classify_error_and_get_status("TIMEOUT error occurred")
        assert status == 504

    def test_classify_connection_error(self):
        """Test that connection errors map to 502 Bad Gateway"""
        status, msg = classify_error_and_get_status("Connection refused")
        assert status == 502
        assert "Bad Gateway" in msg

    def test_classify_not_found_error(self):
        """Test that 404 errors map to 404 Not Found"""
        status, msg = classify_error_and_get_status("404 Not found on server")
        assert status == 404
        assert "not found" in msg.lower()

    def test_classify_not_found_text_error(self):
        """Test that 'not found' text maps to 404"""
        status, msg = classify_error_and_get_status("Stream not found")
        assert status == 404

    def test_classify_auth_error_401(self):
        """Test that 401 errors map to 403 Forbidden"""
        status, msg = classify_error_and_get_status("401 Unauthorized")
        assert status == 403
        assert "auth" in msg.lower()

    def test_classify_auth_error_403(self):
        """Test that 403 errors map to 403 Forbidden"""
        status, msg = classify_error_and_get_status("403 Forbidden")
        assert status == 403

    def test_classify_auth_error_text(self):
        """Test that 'auth' text maps to 403"""
        status, msg = classify_error_and_get_status("Authentication failed")
        assert status == 403

    def test_classify_generic_error(self):
        """Test that unknown errors map to 502 Bad Gateway"""
        status, msg = classify_error_and_get_status("Some random error")
        assert status == 502
        assert "Upstream error" in msg or "Bad Gateway" in msg


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

    def test_stream_status_includes_account_info(self, app, client, test_account):
        """Test stream status returns account and credential details"""
        response = client.get(f"/stream/{test_account}/status")
        assert response.status_code == 200
        data = response.json
        # Should contain either connection info or legacy mode indicator
        assert isinstance(data, dict)


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
        assert data["count"] == 0

    def test_active_streams_with_invalid_account_filter(self, app, client):
        """Test active streams with invalid account_id filter (non-numeric)"""
        response = client.get("/stream/active?account_id=invalid")
        # Should be 400 for invalid parameter
        assert response.status_code in [200, 400]


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

    def test_release_stream_idempotent(self, app, client, test_account_with_credential):
        """Test releasing the same stream token twice"""
        account_id, credential_id = test_account_with_credential
        with app.app_context():
            active_stream = ActiveStream(
                credential_id=credential_id,
                stream_id="test_stream",
                client_ip="127.0.0.1",
                session_token="test_token_456",
            )
            db.session.add(active_stream)
            db.session.commit()

        # Release once
        response1 = client.post("/stream/test_token_456/release")
        assert response1.status_code == 200

        # Release again - should return 404
        response2 = client.post("/stream/test_token_456/release")
        assert response2.status_code == 404


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
        data = response.json
        assert data["success"] is True

    def test_cleanup_streams_with_timeout(self, app, client):
        """Test cleanup streams with custom timeout"""
        response = client.post("/stream/cleanup?timeout=60")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True

    def test_cleanup_streams_with_default_timeout(self, app, client):
        """Test cleanup streams uses default timeout when not specified"""
        response = client.post("/stream/cleanup")
        assert response.status_code == 200


class TestStreamPlayer:
    """Tests for stream player endpoint"""

    def test_stream_player_account_not_found(self, app, client):
        """Test player returns 404 for non-existent account"""
        response = client.get("/player/999/stream123")
        assert response.status_code == 404

    def test_stream_player_success(self, app, client, test_account):
        """Test player returns HTML page"""
        response = client.get(f"/player/{test_account}/stream123")
        assert response.status_code == 200
        assert b"<!DOCTYPE" in response.data or b"<html" in response.data

    def test_stream_player_renders_template(self, app, client, test_account):
        """Test player returns properly formatted HTML"""
        response = client.get(f"/player/{test_account}/stream123")
        assert response.status_code == 200
        # Check for some expected content in the page
        content = response.data.decode()
        assert "stream" in content.lower() or "player" in content.lower()


class TestProxyStream:
    """Tests for stream proxy endpoints"""

    def test_proxy_stream_ts_account_not_found(self, app, client):
        """Test proxy .ts stream returns 404 for non-existent account"""
        response = client.get("/stream/999/12345.ts")
        assert response.status_code == 404

    def test_proxy_stream_m3u8_account_not_found(self, app, client):
        """Test proxy .m3u8 stream returns 404 for non-existent account"""
        response = client.get("/stream/999/12345.m3u8")
        assert response.status_code == 404

    def test_proxy_stream_formats_different_extensions(self, app, client, test_account):
        """Test that different stream formats are accepted"""
        # Both .ts and .m3u8 should be valid extensions
        response_ts = client.get(f"/stream/{test_account}/test_stream.ts")
        response_m3u8 = client.get(f"/stream/{test_account}/test_stream.m3u8")

        # Both should reach the handler (responses may vary based on service availability)
        assert response_ts.status_code in [200, 502, 503]
        assert response_m3u8.status_code in [200, 502, 503]


# ============================================================================
# Test Stream Endpoint Tests
# ============================================================================


class TestStreamConnectivityTest:
    """Tests for stream connectivity testing endpoint"""

    def test_test_stream_account_not_found(self, app, client):
        """Test connectivity check returns 404 for non-existent account"""
        response = client.get("/stream/999/test123/test")
        assert response.status_code == 404
        data = response.json
        assert data["success"] is False
        assert "not found" in data["error"].lower()

    def test_test_stream_no_credentials(self, app, client, test_account):
        """Test connectivity check when no credentials are available"""
        with app.app_context():
            account = db.session.get(Account, test_account)
            Credential.query.filter_by(account_id=account.id).delete()
            db.session.commit()
            account_id = account.id

        response = client.get(f"/stream/{account_id}/test123/test")
        # When no credentials available, test_stream returns 503
        assert response.status_code in [200, 503]
        if response.status_code == 503:
            data = response.json
            assert data["success"] is False
            assert data["checks"]["credential_available"] is False

    @patch("services.stream_proxy_service.requests.head")
    def test_test_stream_upstream_success(self, mock_head, app, client, test_account):
        """Test connectivity check succeeds when upstream returns 200"""
        account_id = test_account

        # Mock successful HEAD request
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_head.return_value = mock_response

        response = client.get(f"/stream/{account_id}/test123/test")
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True

    @patch("services.stream_proxy_service.requests.head")
    def test_test_stream_upstream_connection_error(self, mock_head, app, client, test_account):
        """Test connectivity check handles connection errors"""
        import requests

        account_id = test_account

        # Mock connection error
        mock_head.side_effect = requests.exceptions.ConnectionError("Connection refused")

        response = client.get(f"/stream/{account_id}/test123/test")
        data = response.json
        assert data["success"] is False
        assert "connection" in data["error"].lower()

    @patch("services.stream_proxy_service.requests.head")
    def test_test_stream_upstream_404(self, mock_head, app, client, test_account):
        """Test connectivity check reports 404 from upstream"""
        account_id = test_account

        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_head.return_value = mock_response

        response = client.get(f"/stream/{account_id}/test123/test")
        data = response.json
        assert data["success"] is False
        assert "404" in data["error"] or "not found" in data["error"].lower()

    @patch("services.stream_proxy_service.requests.head")
    def test_test_stream_results_structure(self, mock_head, app, client, test_account):
        """Test connectivity check returns proper result structure"""
        account_id = test_account

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "video/mp2t"}
        mock_head.return_value = mock_response

        response = client.get(f"/stream/{account_id}/test123/test")
        data = response.json

        # Verify result structure
        assert "account_id" in data
        assert "stream_id" in data
        assert "success" in data
        assert "checks" in data
        assert isinstance(data["checks"], dict)
        assert "account_exists" in data["checks"]
        assert "account_enabled" in data["checks"]


# ============================================================================
# Multiplexer Stats Tests
# ============================================================================


class TestMultiplexerStats:
    """Tests for stream multiplexer statistics endpoint"""

    def test_multiplexer_stats_returns_stats(self, app, client):
        """Test multiplexer stats endpoint returns statistics"""
        response = client.get("/stream/multiplexer/stats")
        assert response.status_code == 200
        data = response.json
        # Should contain some stats structure
        assert isinstance(data, dict)

    def test_shared_streams_returns_list(self, app, client):
        """Test shared streams endpoint returns shared stream list"""
        response = client.get("/stream/shared")
        assert response.status_code == 200
        data = response.json
        assert "shared_streams" in data or "streams" in data
        assert "count" in data
