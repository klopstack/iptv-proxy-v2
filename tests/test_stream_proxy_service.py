"""
Tests for stream proxy service - decomposed logic from routes/streams.py
"""
from unittest.mock import Mock, patch

import requests

from models import Account
from services.mediaflow_stream_service import MediaFlowStreamService
from services.stream_proxy_service import StreamConnectivityTester, StreamProxyService

# ============================================================================
# StreamProxyService Tests
# ============================================================================


class TestStreamProxyService:
    """Tests for StreamProxyService methods"""

    @patch("services.stream_proxy_service.ConnectionManager.get_available_credential")
    def test_handle_credential_shortage_with_idle_streams(self, mock_get_cred, app):
        """Test credential acquisition by releasing idle streams"""
        # Setup
        mock_stream_service = Mock()
        mock_stream_service.get_idle_stream_count.return_value = 2
        mock_stream_service.release_idle_streams_for_account.return_value = 1
        mock_credential = Mock(id=1, username="user", password="pass")
        mock_get_cred.return_value = mock_credential

        # Execute
        result = StreamProxyService.handle_credential_shortage(1, mock_stream_service)

        # Verify
        assert result is mock_credential
        mock_stream_service.get_idle_stream_count.assert_called_once_with(1)
        mock_stream_service.release_idle_streams_for_account.assert_called_once_with(1)
        mock_get_cred.assert_called_once()

    @patch("services.stream_proxy_service.ConnectionManager.get_available_credential")
    def test_handle_credential_shortage_mediaflow_no_attribute_error(self, mock_get_cred, app):
        """MediaFlow backend exposes idle-stream API as no-ops (no AttributeError)."""
        service = MediaFlowStreamService()
        mock_get_cred.return_value = None

        result = StreamProxyService.handle_credential_shortage(1, service)

        assert result is None
        assert service.get_idle_stream_count(1) == 0
        assert service.release_idle_streams_for_account(1) == 0

    @patch("services.stream_proxy_service.ConnectionManager.get_available_credential")
    def test_handle_credential_shortage_no_idle_streams(self, mock_get_cred, app):
        """Test when no idle streams available"""
        mock_stream_service = Mock()
        mock_stream_service.get_idle_stream_count.return_value = 0

        result = StreamProxyService.handle_credential_shortage(1, mock_stream_service)

        assert result is None
        mock_stream_service.release_idle_streams_for_account.assert_not_called()

    @patch("services.stream_proxy_service.ConnectionManager.get_available_credential")
    def test_handle_credential_shortage_release_fails(self, mock_get_cred, app):
        """Test when releasing idle streams doesn't free up credentials"""
        mock_stream_service = Mock()
        mock_stream_service.get_idle_stream_count.return_value = 2
        mock_stream_service.release_idle_streams_for_account.return_value = 0
        mock_get_cred.return_value = None

        result = StreamProxyService.handle_credential_shortage(1, mock_stream_service)

        assert result is None

    def test_build_stream_response_headers_new_stream(self):
        """Test response headers for new stream"""
        headers = StreamProxyService.build_stream_response_headers(
            session_token="abc123def456", subscriber_id="sub_xyz789", is_shared=False
        )

        assert headers["Cache-Control"] == "no-cache, no-store, must-revalidate"
        assert headers["Pragma"] == "no-cache"
        assert headers["Expires"] == "0"
        assert headers["X-Session-Token"] == "abc123def456"
        assert headers["X-Stream-Shared"] == "false"
        assert headers["X-Subscriber-Id"] == "sub_xyz7"

    def test_build_stream_response_headers_shared_stream(self):
        """Test response headers for shared stream"""
        headers = StreamProxyService.build_stream_response_headers(
            session_token="token", subscriber_id="subscriber123", is_shared=True
        )

        assert headers["X-Stream-Shared"] == "true"
        assert headers["X-Subscriber-Id"] == "subscrib"

    def test_build_stream_response_headers_subscriber_id_truncation(self):
        """Test that subscriber ID is truncated to 8 chars"""
        headers = StreamProxyService.build_stream_response_headers(
            session_token="token", subscriber_id="very_long_subscriber_id_12345", is_shared=False
        )

        # Should be first 8 characters
        assert headers["X-Subscriber-Id"] == "very_lon"


# ============================================================================
# StreamConnectivityTester Tests
# ============================================================================


class TestStreamConnectivityTester:
    """Tests for StreamConnectivityTester methods"""

    def test_build_test_result_success(self):
        """Test building success result"""
        result = StreamConnectivityTester.build_test_result(account_id=1, stream_id="stream123", success=True)

        assert result["account_id"] == 1
        assert result["stream_id"] == "stream123"
        assert result["success"] is True
        assert result["error"] is None
        assert isinstance(result["checks"], dict)

    def test_build_test_result_failure(self):
        """Test building failure result"""
        result = StreamConnectivityTester.build_test_result(
            account_id=2, stream_id="stream456", success=False, error="Connection failed"
        )

        assert result["account_id"] == 2
        assert result["stream_id"] == "stream456"
        assert result["success"] is False
        assert result["error"] == "Connection failed"

    def test_check_account_prerequisites_account_not_found(self, app):
        """Test account check when account doesn't exist"""
        is_valid, error, status = StreamConnectivityTester.check_account_prerequisites(None)

        assert is_valid is False
        assert error == "Account not found"
        assert status == 404

    def test_check_account_prerequisites_account_disabled(self, app):
        """Test account check when account is disabled"""
        with app.app_context():
            account = Account(
                name="Test",
                username="user",
                password="pass",
                server="example.com",
                enabled=False,
            )

        is_valid, error, status = StreamConnectivityTester.check_account_prerequisites(account)

        assert is_valid is False
        assert error == "Account is disabled"
        assert status == 403

    def test_check_account_prerequisites_valid(self, app):
        """Test account check when account is valid"""
        with app.app_context():
            account = Account(
                name="Test",
                username="user",
                password="pass",
                server="example.com",
                enabled=True,
            )

        is_valid, error, status = StreamConnectivityTester.check_account_prerequisites(account)

        assert is_valid is True
        assert error is None
        assert status == 200

    def test_check_credential_prerequisites_none(self):
        """Test credential check when credential is None"""
        is_valid, error, status = StreamConnectivityTester.check_credential_prerequisites(None)

        assert is_valid is False
        assert error == "No available credentials"
        assert status == 503

    def test_check_credential_prerequisites_valid(self):
        """Test credential check when credential is valid"""
        credential = Mock(id=1, username="user", password="pass")

        is_valid, error, status = StreamConnectivityTester.check_credential_prerequisites(credential)

        assert is_valid is True
        assert error is None
        assert status == 200

    @patch("services.stream_proxy_service.requests.head")
    def test_test_upstream_head_success(self, mock_head):
        """Test successful HEAD request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "video/mp2t", "Content-Length": "1000"}
        mock_head.return_value = mock_response

        status, headers, error = StreamConnectivityTester.test_upstream_head(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status == 200
        assert headers == {"Content-Type": "video/mp2t", "Content-Length": "1000"}
        assert error is None
        mock_head.assert_called_once()

    @patch("services.stream_proxy_service.requests.head")
    def test_test_upstream_head_timeout(self, mock_head):
        """Test HEAD request with timeout"""
        mock_head.side_effect = requests.exceptions.Timeout("Connection timed out")

        status, headers, error = StreamConnectivityTester.test_upstream_head(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status is None
        assert headers is None
        assert "timed out" in error.lower()

    @patch("services.stream_proxy_service.requests.head")
    def test_test_upstream_head_connection_error(self, mock_head):
        """Test HEAD request with connection error"""
        mock_head.side_effect = requests.exceptions.ConnectionError("Connection refused")

        status, headers, error = StreamConnectivityTester.test_upstream_head(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status is None
        assert headers is None
        assert "Connection failed" in error

    @patch("services.stream_proxy_service.requests.head")
    def test_test_upstream_head_404(self, mock_head):
        """Test HEAD request returns 404"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.headers = {}
        mock_head.return_value = mock_response

        status, headers, error = StreamConnectivityTester.test_upstream_head(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status == 404
        assert headers == {}
        assert error is None

    @patch("services.stream_proxy_service.requests.get")
    def test_test_upstream_get_success(self, mock_get):
        """Test successful GET request"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {"Content-Type": "video/mp2t"}
        # iter_content needs to return an iterator, not a list
        mock_response.iter_content = Mock(return_value=iter([b"data_chunk_1"]))
        mock_response.close = Mock()
        mock_get.return_value = mock_response

        status, headers, data_size, error = StreamConnectivityTester.test_upstream_get(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status == 200
        assert headers == {"Content-Type": "video/mp2t"}
        assert data_size == 12  # len(b"data_chunk_1")
        assert error is None
        mock_response.close.assert_called_once()

    @patch("services.stream_proxy_service.requests.get")
    def test_test_upstream_get_no_data(self, mock_get):
        """Test GET request with no data"""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.iter_content = Mock(return_value=iter([]))
        mock_response.close = Mock()
        mock_get.return_value = mock_response

        status, headers, data_size, error = StreamConnectivityTester.test_upstream_get(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status == 200
        assert data_size == 0
        assert error is None

    @patch("services.stream_proxy_service.requests.get")
    def test_test_upstream_get_timeout(self, mock_get):
        """Test GET request with timeout"""
        mock_get.side_effect = requests.exceptions.Timeout("timeout")

        status, headers, data_size, error = StreamConnectivityTester.test_upstream_get(
            "http://example.com/stream.ts", "okhttp/3.14.9"
        )

        assert status is None
        assert headers is None
        assert data_size == 0
        assert "timed out" in error.lower()

    def test_determine_test_success_and_error_head_200(self):
        """Test success determination when HEAD returns 200"""
        success, error = StreamConnectivityTester.determine_test_success_and_error(
            head_status=200, head_error=None, get_status=None, get_error=None
        )

        assert success is True
        assert error is None

    def test_determine_test_success_and_error_head_405_get_200(self):
        """Test success determination when HEAD returns 405 and GET returns 200"""
        success, error = StreamConnectivityTester.determine_test_success_and_error(
            head_status=405, head_error=None, get_status=200, get_error=None
        )

        assert success is True
        assert error is None

    def test_determine_test_success_and_error_head_405_get_404(self):
        """Test failure when HEAD returns 405 and GET returns 404"""
        success, error = StreamConnectivityTester.determine_test_success_and_error(
            head_status=405, head_error=None, get_status=404, get_error=None
        )

        assert success is False
        # Error comes from get_status when HEAD is 405 and GET fails
        assert "404" in error or "Upstream returned" in error

    def test_determine_test_success_and_error_head_error(self):
        """Test failure with HEAD error"""
        success, error = StreamConnectivityTester.determine_test_success_and_error(
            head_status=None, head_error="Connection timeout", get_status=None, get_error=None
        )

        assert success is False
        assert "Connection timeout" in error

    def test_determine_test_success_and_error_head_500(self):
        """Test failure with HEAD returning 500"""
        success, error = StreamConnectivityTester.determine_test_success_and_error(
            head_status=500, head_error=None, get_status=None, get_error=None
        )

        assert success is False
        assert "500" in error

    def test_determine_test_success_and_error_get_error(self):
        """Test failure with GET error"""
        success, error = StreamConnectivityTester.determine_test_success_and_error(
            head_status=405, head_error=None, get_status=None, get_error="Connection refused"
        )

        assert success is False
        assert "Connection refused" in error
