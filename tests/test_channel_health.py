"""
Tests for channel health monitoring service and routes.
"""
import json
from unittest.mock import MagicMock, patch

import pytest

from models import (
    Account,
    Category,
    Channel,
    ChannelHealthCheck,
    ChannelHealthConfig,
    ChannelHealthStatus,
    Credential,
    db,
)


@pytest.fixture
def app():
    """Create test Flask app with in-memory database."""
    from app import app as flask_app

    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def test_account(app):
    """Create a test account with credentials."""
    with app.app_context():
        account = Account(
            name="Test Account",
            server="test.server.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        credential = Credential(
            account_id=account.id,
            username="testuser",
            password="testpass",
            max_connections=3,
        )
        db.session.add(credential)
        db.session.commit()

        return account.id


@pytest.fixture
def test_channel(app, test_account):
    """Create a test channel."""
    with app.app_context():
        # Create category first
        category = Category(
            account_id=test_account,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()

        channel = Channel(
            account_id=test_account,
            stream_id="12345",
            name="Test Channel",
            cleaned_name="Test Channel",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()

        return channel.id


class TestChannelHealthConfig:
    """Test ChannelHealthConfig model."""

    def test_get_default(self, app):
        """Test getting default config values."""
        with app.app_context():
            # Should return default
            value = ChannelHealthConfig.get("failure_threshold")
            assert value == "3"

    def test_get_nonexistent(self, app):
        """Test getting nonexistent config returns None."""
        with app.app_context():
            value = ChannelHealthConfig.get("nonexistent_key")
            assert value is None

    def test_get_with_default(self, app):
        """Test getting config with custom default."""
        with app.app_context():
            value = ChannelHealthConfig.get("nonexistent_key", "custom_default")
            assert value == "custom_default"

    def test_set_and_get(self, app):
        """Test setting and getting config values."""
        with app.app_context():
            ChannelHealthConfig.set("test_key", "test_value", "Test description")

            value = ChannelHealthConfig.get("test_key")
            assert value == "test_value"

    def test_get_int(self, app):
        """Test getting config as integer."""
        with app.app_context():
            ChannelHealthConfig.set("int_key", "42")
            value = ChannelHealthConfig.get_int("int_key")
            assert value == 42

    def test_get_int_invalid(self, app):
        """Test getting invalid integer returns default."""
        with app.app_context():
            ChannelHealthConfig.set("invalid_int", "not_a_number")
            value = ChannelHealthConfig.get_int("invalid_int", 10)
            assert value == 10

    def test_get_float(self, app):
        """Test getting config as float."""
        with app.app_context():
            ChannelHealthConfig.set("float_key", "3.14")
            value = ChannelHealthConfig.get_float("float_key")
            assert value == 3.14

    def test_get_bool(self, app):
        """Test getting config as boolean."""
        with app.app_context():
            ChannelHealthConfig.set("bool_true", "true")
            ChannelHealthConfig.set("bool_false", "false")
            ChannelHealthConfig.set("bool_yes", "yes")
            ChannelHealthConfig.set("bool_one", "1")

            assert ChannelHealthConfig.get_bool("bool_true") is True
            assert ChannelHealthConfig.get_bool("bool_false") is False
            assert ChannelHealthConfig.get_bool("bool_yes") is True
            assert ChannelHealthConfig.get_bool("bool_one") is True

    def test_get_all(self, app):
        """Test getting all config values."""
        with app.app_context():
            config = ChannelHealthConfig.get_all()
            assert "failure_threshold" in config
            assert "scanning_enabled" in config


class TestChannelHealthStatus:
    """Test ChannelHealthStatus model."""

    def test_status_creation(self, app, test_channel):
        """Test creating health status."""
        with app.app_context():
            status = ChannelHealthStatus(
                channel_id=test_channel,
                status=ChannelHealthStatus.STATUS_HEALTHY,
            )
            db.session.add(status)
            db.session.commit()

            retrieved = ChannelHealthStatus.query.filter_by(channel_id=test_channel).first()
            assert retrieved is not None
            assert retrieved.status == "healthy"


class TestChannelHealthCheck:
    """Test ChannelHealthCheck model."""

    def test_check_creation(self, app, test_channel):
        """Test creating health check records."""
        with app.app_context():
            check = ChannelHealthCheck(
                channel_id=test_channel,
                result=ChannelHealthCheck.RESULT_SUCCESS,
                check_duration_ms=1500,
            )
            db.session.add(check)
            db.session.commit()

            retrieved = ChannelHealthCheck.query.filter_by(channel_id=test_channel).first()
            assert retrieved is not None
            assert retrieved.result == "success"


class TestChannelHealthRoutes:
    """Test channel health API routes."""

    def test_get_health_report(self, client, app, test_channel):
        """Test getting health report."""
        response = client.get("/api/channel-health/report")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "summary" in data
        assert "channels" in data

    def test_get_health_summary(self, client, app):
        """Test getting health summary."""
        response = client.get("/api/channel-health/summary")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "summary" in data

    def test_get_health_report_invalid_status(self, client, app):
        """Test getting health report with invalid status filter."""
        response = client.get("/api/channel-health/report?status=invalid")
        assert response.status_code == 400

    def test_get_config(self, client, app):
        """Test getting health config."""
        response = client.get("/api/channel-health/config")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert "config" in data

    def test_update_config(self, client, app):
        """Test updating health config."""
        response = client.put(
            "/api/channel-health/config",
            data=json.dumps({"key": "failure_threshold", "value": "5"}),
            content_type="application/json",
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True

    def test_update_config_batch(self, client, app):
        """Test batch updating health config."""
        response = client.put(
            "/api/channel-health/config",
            data=json.dumps(
                {
                    "config": {
                        "failure_threshold": "4",
                        "min_hours_apart": "8",
                    }
                }
            ),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_update_config_no_body(self, client, app):
        """Test updating config without body returns error."""
        response = client.put(
            "/api/channel-health/config",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_get_scan_status(self, client, app):
        """Test getting scan status."""
        response = client.get("/api/channel-health/scan-status")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True

    def test_get_channel_history_empty(self, client, app, test_channel):
        """Test getting empty channel history."""
        response = client.get(f"/api/channel-health/history/{test_channel}")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert data["history"] == []

    def test_reenable_channel(self, client, app, test_channel):
        """Test re-enabling a channel."""
        response = client.post(f"/api/channel-health/reenable/{test_channel}")
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True

    def test_reenable_nonexistent_channel(self, client, app):
        """Test re-enabling nonexistent channel."""
        response = client.post("/api/channel-health/reenable/99999")
        assert response.status_code == 400

    def test_ignore_channel(self, client, app, test_channel):
        """Test ignoring a channel."""
        response = client.post(
            f"/api/channel-health/ignore/{test_channel}",
            data=json.dumps({"reason": "Test reason"}),
            content_type="application/json",
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True

    def test_ignore_nonexistent_channel(self, client, app):
        """Test ignoring nonexistent channel."""
        response = client.post(
            "/api/channel-health/ignore/99999",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_test_channel_no_credentials(self, client, app, test_channel):
        """Test testing a channel without available credentials returns error."""
        # Remove credentials
        with app.app_context():
            Credential.query.delete()
            db.session.commit()

        response = client.post(f"/api/channel-health/test/{test_channel}")
        assert response.status_code == 400

    def test_bulk_reenable_no_ids(self, client, app):
        """Test bulk re-enable without channel IDs."""
        response = client.post(
            "/api/channel-health/bulk/reenable",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_bulk_reenable_invalid_type(self, client, app):
        """Test bulk re-enable with invalid type."""
        response = client.post(
            "/api/channel-health/bulk/reenable",
            data=json.dumps({"channel_ids": "not_a_list"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_bulk_ignore_no_ids(self, client, app):
        """Test bulk ignore without channel IDs."""
        response = client.post(
            "/api/channel-health/bulk/ignore",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400


class TestChannelHealthService:
    """Test channel health service."""

    def test_get_available_scan_connections(self, app, test_account):
        """Test getting available scan connections."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            # With 3 max connections and 1 reserved, should have 2 available
            available = ChannelHealthService.get_available_scan_connections(test_account)
            assert available == 2

    def test_get_available_scan_connections_disabled_account(self, app, test_account):
        """Test getting connections for disabled account returns 0."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            account = db.session.get(Account, test_account)
            account.enabled = False
            db.session.commit()

            available = ChannelHealthService.get_available_scan_connections(test_account)
            assert available == 0

    def test_get_channels_to_scan(self, app, test_account, test_channel):
        """Test getting channels to scan."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            # Enable scanning
            ChannelHealthConfig.set("scanning_enabled", "true")

            channels = ChannelHealthService.get_channels_to_scan(test_account)
            assert len(channels) > 0
            assert channels[0].id == test_channel

    def test_get_channels_to_scan_excludes_down(self, app, test_account, test_channel):
        """Test that down channels are excluded from scanning."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            # Mark channel as down
            status = ChannelHealthStatus(
                channel_id=test_channel,
                status=ChannelHealthStatus.STATUS_DOWN,
            )
            db.session.add(status)
            db.session.commit()

            channels = ChannelHealthService.get_channels_to_scan(test_account)
            assert len(channels) == 0

    def test_get_health_report(self, app, test_channel):
        """Test getting health report."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            report = ChannelHealthService.get_health_report()
            assert "summary" in report
            assert "channels" in report
            assert report["summary"]["total"] > 0

    def test_get_health_report_with_filters(self, app, test_account, test_channel):
        """Test getting health report with filters."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            report = ChannelHealthService.get_health_report(
                account_id=test_account,
                status_filter="unknown",
            )
            assert len(report["channels"]) > 0

    def test_reenable_channel(self, app, test_channel):
        """Test re-enabling a channel."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            # First mark it as down
            status = ChannelHealthStatus(
                channel_id=test_channel,
                status=ChannelHealthStatus.STATUS_DOWN,
            )
            db.session.add(status)

            channel = db.session.get(Channel, test_channel)
            channel.is_visible = False
            db.session.commit()

            # Re-enable
            result = ChannelHealthService.reenable_channel(test_channel)
            assert result["success"] is True

            # Check channel is visible again
            channel = db.session.get(Channel, test_channel)
            assert channel.is_visible is True

    def test_ignore_channel(self, app, test_channel):
        """Test ignoring a channel."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            result = ChannelHealthService.ignore_channel(test_channel, "Test reason")
            assert result["success"] is True

            status = ChannelHealthStatus.query.filter_by(channel_id=test_channel).first()
            assert status.status == ChannelHealthStatus.STATUS_IGNORED
            assert status.ignored_reason == "Test reason"

    def test_record_health_check(self, app, test_channel):
        """Test recording a health check."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            result = {
                "result": ChannelHealthCheck.RESULT_SUCCESS,
                "check_duration_ms": 1500,
            }

            check = ChannelHealthService.record_health_check(test_channel, result)
            assert check is not None
            assert check.result == "success"

            # Check status was updated
            status = ChannelHealthStatus.query.filter_by(channel_id=test_channel).first()
            assert status is not None
            assert status.status == ChannelHealthStatus.STATUS_HEALTHY

    def test_record_health_check_failure(self, app, test_channel):
        """Test recording a failed health check."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            result = {
                "result": ChannelHealthCheck.RESULT_CONNECTION_FAILED,
                "error_message": "Connection refused",
                "check_duration_ms": 500,
            }

            check = ChannelHealthService.record_health_check(test_channel, result)
            assert check.result == "connection_failed"

            status = ChannelHealthStatus.query.filter_by(channel_id=test_channel).first()
            assert status.consecutive_failures == 1
            assert status.status == ChannelHealthStatus.STATUS_DEGRADED

    def test_scan_channels_disabled(self, app, test_account):
        """Test scanning when disabled returns message."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            ChannelHealthConfig.set("scanning_enabled", "false")

            result = ChannelHealthService.scan_channels(test_account)
            assert result["success"] is False
            assert "disabled" in result["message"]

    @patch("services.channel_health_service.ChannelHealthService.check_channel_health")
    def test_scan_channels_success(self, mock_check, app, test_account, test_channel):
        """Test successful channel scanning."""
        from services.channel_health_service import ChannelHealthService

        mock_check.return_value = {
            "result": ChannelHealthCheck.RESULT_SUCCESS,
            "check_duration_ms": 1000,
        }

        with app.app_context():
            ChannelHealthConfig.set("scanning_enabled", "true")

            result = ChannelHealthService.scan_channels(test_account, max_channels=1)
            assert result["success"] is True
            assert result["scanned"] == 1

    def test_get_channel_history(self, app, test_channel):
        """Test getting channel history."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            # Add some checks
            for i in range(3):
                check = ChannelHealthCheck(
                    channel_id=test_channel,
                    result=ChannelHealthCheck.RESULT_SUCCESS,
                    check_duration_ms=1000 + i * 100,
                )
                db.session.add(check)
            db.session.commit()

            history = ChannelHealthService.get_channel_history(test_channel)
            assert len(history) == 3

    def test_update_config(self, app):
        """Test updating config."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            result = ChannelHealthService.update_config("failure_threshold", "5")
            assert result["success"] is True

            # Verify the change
            value = ChannelHealthConfig.get("failure_threshold")
            assert value == "5"

    def test_update_config_unknown_key(self, app):
        """Test updating unknown config key returns error."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            result = ChannelHealthService.update_config("unknown_key_xyz", "value")
            assert result["success"] is False

    def test_get_scan_status(self, app, test_account):
        """Test getting scan status."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            status = ChannelHealthService.get_scan_status()
            assert "scanning_enabled" in status
            assert "accounts" in status

    def test_get_scan_status_for_account(self, app, test_account):
        """Test getting scan status for specific account."""
        from services.channel_health_service import ChannelHealthService

        with app.app_context():
            status = ChannelHealthService.get_scan_status(test_account)
            assert status["account_id"] == test_account
            assert "available_connections" in status


class TestChannelHealthServiceAnalysis:
    """Test channel health analysis with mocked ffprobe."""

    @patch("subprocess.run")
    def test_analyze_stream_success(self, mock_run, app):
        """Test successful stream analysis."""
        from services.channel_health_service import ChannelHealthService

        # Mock ffprobe output
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080},
                        {"codec_type": "audio", "codec_name": "aac"},
                    ]
                }
            ),
            stderr="",
        )

        result = ChannelHealthService._analyze_stream_with_ffprobe("http://test.server/stream.ts", 10, "test-agent")

        assert result["result"] == ChannelHealthCheck.RESULT_SUCCESS

    @patch("subprocess.run")
    def test_analyze_stream_timeout(self, mock_run, app):
        """Test stream analysis timeout."""
        from subprocess import TimeoutExpired

        from services.channel_health_service import ChannelHealthService

        mock_run.side_effect = TimeoutExpired(cmd="ffprobe", timeout=10)

        result = ChannelHealthService._analyze_stream_with_ffprobe("http://test.server/stream.ts", 10, "test-agent")

        assert result["result"] == ChannelHealthCheck.RESULT_TIMEOUT

    @patch("subprocess.run")
    def test_analyze_stream_connection_failed(self, mock_run, app):
        """Test stream analysis connection failure."""
        from services.channel_health_service import ChannelHealthService

        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="Connection refused",
        )

        result = ChannelHealthService._analyze_stream_with_ffprobe("http://test.server/stream.ts", 10, "test-agent")

        assert result["result"] == ChannelHealthCheck.RESULT_CONNECTION_FAILED

    @patch("subprocess.run")
    def test_analyze_stream_no_video(self, mock_run, app):
        """Test stream with audio only."""
        from services.channel_health_service import ChannelHealthService

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(
                {
                    "streams": [
                        {"codec_type": "audio", "codec_name": "aac"},
                    ]
                }
            ),
            stderr="",
        )

        result = ChannelHealthService._analyze_stream_with_ffprobe("http://test.server/stream.ts", 10, "test-agent")

        assert result["result"] == ChannelHealthCheck.RESULT_AUDIO_ONLY
