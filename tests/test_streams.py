"""
Tests for stream routes to boost coverage

Uses shared fixtures from conftest.py for proper test isolation.
"""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Credential, db

# app and client fixtures are provided by conftest.py


@pytest.fixture
def setup_account(app):
    """Create test account with credentials."""
    with app.app_context():
        account = Account(
            name="Test Account",
            server="test.example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        credential = Credential(
            account_id=account.id,
            username="testuser",
            password="testpass",
            enabled=True,
            max_connections=2,
        )
        db.session.add(credential)
        db.session.commit()

        # Return IDs to avoid detached instance issues
        return {"account_id": account.id, "credential_id": credential.id}


class TestStreamStatus:
    """Test stream status endpoints"""

    def test_stream_status_account_not_found(self, client, app):
        """Test stream status for non-existent account"""
        with app.app_context():
            response = client.get("/stream/99999/status")
            assert response.status_code == 404

    def test_stream_status_success(self, client, app, setup_account):
        """Test stream status for existing account"""
        with app.app_context():
            account_id = setup_account["account_id"]
            response = client.get(f"/stream/{account_id}/status")
            assert response.status_code in (200, 204)


class TestActiveStreams:
    """Test active streams endpoint"""

    def test_get_active_streams(self, client, app):
        """Test getting active streams"""
        with app.app_context():
            response = client.get("/stream/active")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert "active_streams" in data
            assert "count" in data

    def test_get_active_streams_with_account_filter(self, client, app, setup_account):
        """Test getting active streams filtered by account"""
        with app.app_context():
            account_id = setup_account["account_id"]
            response = client.get(f"/stream/active?account_id={account_id}")
            assert response.status_code in (200, 204)


class TestStreamRelease:
    """Test stream release endpoint"""

    def test_release_stream_not_found(self, client, app):
        """Test releasing non-existent stream"""
        with app.app_context():
            response = client.post("/stream/invalid-token/release")
            assert response.status_code == 404


class TestStreamCleanup:
    """Test stream cleanup endpoint"""

    def test_cleanup_streams(self, client, app):
        """Test cleanup streams"""
        with app.app_context():
            response = client.post("/stream/cleanup")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["success"] is True

    def test_cleanup_streams_with_account(self, client, app, setup_account):
        """Test cleanup streams for specific account"""
        with app.app_context():
            account_id = setup_account["account_id"]
            response = client.post(f"/stream/cleanup?account_id={account_id}")
            assert response.status_code in (200, 204)


class TestStreamTest:
    """Test stream test endpoint"""

    def test_stream_test_account_not_found(self, client, app):
        """Test stream test for non-existent account"""
        with app.app_context():
            response = client.get("/stream/99999/test123/test")
            assert response.status_code == 404

    def test_stream_test_account_disabled(self, client, app):
        """Test stream test for disabled account"""
        with app.app_context():
            account = Account(
                name="Disabled Account",
                server="test.example.com",
                enabled=False,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            response = client.get(f"/stream/{account_id}/test123/test")
            assert response.status_code == 403

    def test_stream_test_no_credentials(self, client, app):
        """Test stream test with no available credentials"""
        with app.app_context():
            account = Account(
                name="No Creds Account",
                server="test.example.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            response = client.get(f"/stream/{account_id}/test123/test")
            assert response.status_code == 503

    @patch("routes.streams.requests.head")
    def test_stream_test_success(self, mock_head, client, app, setup_account):
        """Test successful stream test"""
        with app.app_context():
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.headers = {"Content-Type": "video/mp2t"}
            mock_head.return_value = mock_response

            account_id = setup_account["account_id"]
            response = client.get(f"/stream/{account_id}/test123/test")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["success"] is True

    @patch("routes.streams.requests.head")
    def test_stream_test_timeout(self, mock_head, client, app, setup_account):
        """Test stream test with timeout"""
        import requests

        with app.app_context():
            mock_head.side_effect = requests.exceptions.Timeout("Connection timed out")

            account_id = setup_account["account_id"]
            response = client.get(f"/stream/{account_id}/test123/test")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["success"] is False
            # Error message contains "timed out" from the exception
            assert "timed out" in data["error"].lower()

    @patch("routes.streams.requests.head")
    def test_stream_test_connection_error(self, mock_head, client, app, setup_account):
        """Test stream test with connection error"""
        import requests

        with app.app_context():
            mock_head.side_effect = requests.exceptions.ConnectionError("Connection failed")

            account_id = setup_account["account_id"]
            response = client.get(f"/stream/{account_id}/test123/test")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["success"] is False

    @patch("routes.streams.requests.head")
    @patch("routes.streams.requests.get")
    def test_stream_test_head_not_supported(self, mock_get, mock_head, client, app, setup_account):
        """Test stream test when HEAD returns 405"""
        with app.app_context():
            # HEAD returns 405
            mock_head_response = MagicMock()
            mock_head_response.status_code = 405
            mock_head.return_value = mock_head_response

            # GET returns 200 with data
            mock_get_response = MagicMock()
            mock_get_response.status_code = 200
            mock_get_response.headers = {"Content-Type": "video/mp2t"}
            mock_get_response.iter_content.return_value = iter([b"test data"])
            mock_get.return_value = mock_get_response

            account_id = setup_account["account_id"]
            response = client.get(f"/stream/{account_id}/test123/test")
            assert response.status_code in (200, 204)
            data = response.get_json()
            assert data["success"] is True


class TestProxyStream:
    """Test stream proxy endpoint"""

    def test_proxy_stream_account_not_found(self, client, app):
        """Test proxy stream for non-existent account"""
        with app.app_context():
            response = client.get("/stream/99999/test123.ts")
            assert response.status_code == 404

    def test_proxy_stream_account_disabled(self, client, app):
        """Test proxy stream for disabled account"""
        with app.app_context():
            account = Account(
                name="Disabled Account",
                server="test.example.com",
                enabled=False,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            response = client.get(f"/stream/{account_id}/test123.ts")
            assert response.status_code == 403

    def test_proxy_stream_no_credentials(self, client, app):
        """Test proxy stream with no available credentials"""
        with app.app_context():
            account = Account(
                name="No Creds Account",
                server="test.example.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            response = client.get(f"/stream/{account_id}/test123.ts")
            assert response.status_code == 503
