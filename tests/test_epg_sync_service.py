"""
Tests for EpgSyncService - EPG source synchronization dispatcher

Tests the dispatcher logic that routes to correct sync methods.
Individual sync methods are integration tests tested via route tests.
"""
from datetime import datetime, timezone
from unittest.mock import Mock, patch

from services.epg_sync_service import EpgSyncService


class TestSyncSourceDispatcher:
    """Test the dispatcher method that routes to correct sync method"""

    def test_sync_source_handles_invalid_type(self):
        """Invalid source type returns error"""
        source = Mock()
        source.source_type = "invalid_type"

        success, message, stats = EpgSyncService.sync_source(source)

        assert success is False
        assert "unknown" in message.lower()

    def test_sync_source_handles_none_type(self):
        """None source type returns error"""
        source = Mock()
        source.source_type = None

        success, message, stats = EpgSyncService.sync_source(source)

        assert success is False

    def test_sync_source_dispatches_provider(self):
        """Sync source dispatches to provider method for provider type"""
        source = Mock()
        source.source_type = "provider"

        with patch.object(EpgSyncService, "sync_provider_source", return_value=(True, "OK", {})) as mock_sync:
            success, message, stats = EpgSyncService.sync_source(source)

            assert success is True
            mock_sync.assert_called_once_with(source)

    def test_sync_source_dispatches_xmltv_url(self):
        """Sync source dispatches to xmltv_url method"""
        source = Mock()
        source.source_type = "xmltv_url"

        with patch.object(EpgSyncService, "sync_xmltv_url_source", return_value=(True, "OK", {})) as mock_sync:
            success, message, stats = EpgSyncService.sync_source(source)

            assert success is True
            mock_sync.assert_called_once_with(source)

    def test_sync_source_dispatches_schedules_direct(self):
        """Sync source dispatches to schedules_direct method"""
        source = Mock()
        source.source_type = "schedules_direct"

        with patch.object(EpgSyncService, "sync_schedules_direct_source", return_value=(True, "OK", {})) as mock_sync:
            success, message, stats = EpgSyncService.sync_source(source)

            assert success is True
            mock_sync.assert_called_once_with(source)

    def test_sync_source_dispatches_xmltv_grabber(self):
        """Sync source dispatches to xmltv_grabber method"""
        source = Mock()
        source.source_type = "xmltv_grabber"

        with patch.object(EpgSyncService, "sync_xmltv_grabber_source", return_value=(True, "OK", {})) as mock_sync:
            success, message, stats = EpgSyncService.sync_source(source)

            assert success is True
            mock_sync.assert_called_once_with(source)

    def test_sync_source_dispatches_ppv_events(self):
        """Sync source dispatches to ppv_events method"""
        source = Mock()
        source.source_type = "ppv_events"

        with patch.object(EpgSyncService, "sync_ppv_events_source", return_value=(True, "OK", {})) as mock_sync:
            success, message, stats = EpgSyncService.sync_source(source)

            assert success is True
            mock_sync.assert_called_once_with(source)


class TestSyncProviderSource:
    """Test sync_provider_source method"""

    def test_sync_provider_source_no_account(self):
        """Sync fails if source has no account"""
        source = Mock()
        source.account = None

        success, message, stats = EpgSyncService.sync_provider_source(source)

        assert success is False
        assert "no associated account" in message.lower()
        assert stats == {}

    @patch("services.epg_sync_service.IPTVService")
    @patch("services.epg_sync_service.sync_epg_source")
    @patch("services.epg_sync_service.save_to_cache")
    def test_sync_provider_source_with_credential(self, mock_cache, mock_sync_epg, mock_iptv_service):
        """Sync provider with credential object"""
        # Setup mocks
        cred = Mock()
        cred.username = "test_user"
        cred.password = "test_pass"

        account = Mock()
        account.server = "http://example.com"
        account.username = "account_user"
        account.password = "account_pass"
        account.user_agent = "test-agent"
        account.get_primary_credential.return_value = cred

        source = Mock()
        source.id = 1
        source.account = account

        iptv_instance = Mock()
        iptv_instance.get_xmltv.return_value = b"<xml>test</xml>"
        mock_iptv_service.return_value = iptv_instance

        mock_sync_epg.return_value = {"channels_added": 5, "channels_updated": 3}

        # Execute
        success, message, stats = EpgSyncService.sync_provider_source(source)

        # Verify
        assert success is True
        assert "5" in message or "8" in message  # channels_synced count
        mock_iptv_service.assert_called_once_with("http://example.com", "test_user", "test_pass", "test-agent")
        mock_cache.assert_called_once_with(1, b"<xml>test</xml>")

    @patch("services.epg_sync_service.IPTVService")
    @patch("services.epg_sync_service.sync_epg_source")
    @patch("services.epg_sync_service.save_to_cache")
    def test_sync_provider_source_without_credential(self, mock_cache, mock_sync_epg, mock_iptv_service):
        """Sync provider using account credentials if no credential object"""
        account = Mock()
        account.server = "http://example.com"
        account.username = "account_user"
        account.password = "account_pass"
        account.user_agent = None
        account.get_primary_credential.return_value = None

        source = Mock()
        source.id = 2
        source.account = account

        iptv_instance = Mock()
        iptv_instance.get_xmltv.return_value = b"<xml>test</xml>"
        mock_iptv_service.return_value = iptv_instance

        mock_sync_epg.return_value = {"channels_added": 10, "channels_updated": 2}

        success, message, stats = EpgSyncService.sync_provider_source(source)

        assert success is True
        mock_iptv_service.assert_called_once_with("http://example.com", "account_user", "account_pass", "okhttp/3.14.9")

    @patch("services.epg_sync_service.IPTVService")
    def test_sync_provider_source_exception(self, mock_iptv_service):
        """Sync provider handles exceptions"""
        account = Mock()
        account.server = "http://example.com"
        account.username = "user"
        account.password = "pass"
        account.user_agent = None
        account.get_primary_credential.return_value = None

        source = Mock()
        source.id = 3
        source.account = account

        mock_iptv_service.side_effect = Exception("Network error")

        success, message, stats = EpgSyncService.sync_provider_source(source)

        assert success is False
        assert "Network error" in message
        assert stats == {}


class TestSyncXmltvUrlSource:
    """Test sync_xmltv_url_source method"""

    def test_sync_xmltv_url_no_url(self):
        """Sync fails if no URL configured"""
        source = Mock()
        source.url = None

        success, message, stats = EpgSyncService.sync_xmltv_url_source(source)

        assert success is False
        assert "no url" in message.lower()


class TestSyncSchedulesDirectSource:
    """Test sync_schedules_direct_source method"""

    def test_sync_sd_source_no_credentials(self):
        """Sync fails if no SD credentials"""
        source = Mock()
        source.sd_username = None
        source.sd_password = "pass"

        success, message, stats = EpgSyncService.sync_schedules_direct_source(source)

        assert success is False
        assert "credentials" in message.lower()

    def test_sync_sd_source_no_lineup(self):
        """Sync fails if no lineup selected"""
        source = Mock()
        source.sd_username = "user"
        source.sd_password = "pass"
        source.sd_lineup = None

        success, message, stats = EpgSyncService.sync_schedules_direct_source(source)

        assert success is False
        assert "lineup" in message.lower()

    @patch("services.epg_sync_service.SchedulesDirectClient")
    def test_sync_sd_source_sd_error(self, mock_sd_client_class):
        """Handle Schedules Direct errors"""
        from services.schedules_direct import SchedulesDirectError

        source = Mock()
        source.id = 1
        source.sd_username = "user"
        source.sd_password = "pass"
        source.sd_lineup = "USA-12345"

        mock_client = Mock()
        mock_sd_client_class.return_value = mock_client
        mock_client.authenticate.side_effect = SchedulesDirectError("Auth failed", code=4001)

        success, message, stats = EpgSyncService.sync_schedules_direct_source(source)

        assert success is False
        assert "error" in message.lower()

    @patch("services.epg_sync_service.SchedulesDirectClient")
    def test_sync_sd_source_exception(self, mock_sd_client_class):
        """Handle general exceptions"""
        source = Mock()
        source.id = 1
        source.sd_username = "user"
        source.sd_password = "pass"
        source.sd_lineup = "USA-12345"

        mock_client = Mock()
        mock_sd_client_class.return_value = mock_client
        mock_client.authenticate.side_effect = Exception("Unexpected error")

        success, message, stats = EpgSyncService.sync_schedules_direct_source(source)

        assert success is False
        assert "Unexpected error" in message


class TestSyncXmltvGrabberSource:
    """Test sync_xmltv_grabber_source method"""

    def test_sync_grabber_no_grabber_configured(self):
        """Sync fails if no grabber configured"""
        source = Mock()
        source.xmltv_grabber = None

        success, message, stats = EpgSyncService.sync_xmltv_grabber_source(source)

        assert success is False
        assert "no xmltv grabber" in message.lower()

    @patch("services.epg_sync_service.XmltvGrabberService.run_grabber")
    @patch("services.epg_sync_service.sync_epg_source")
    @patch("services.epg_sync_service.save_to_cache")
    def test_sync_grabber_success(self, mock_cache, mock_sync, mock_run_grabber):
        """Successfully sync XMLTV grabber"""
        source = Mock()
        source.id = 1
        source.xmltv_grabber = "tv_grab_na"
        source.xmltv_config_name = "myconfig"
        source.xmltv_days = 14
        source.xmltv_offset = 2
        source.xmltv_extra_args = None

        mock_run_grabber.return_value = (True, b"<xml>grabber</xml>", None)
        mock_sync.return_value = {"channels_added": 8, "channels_updated": 4}

        success, message, stats = EpgSyncService.sync_xmltv_grabber_source(source)

        assert success is True
        assert "12" in message  # channels_synced
        mock_run_grabber.assert_called_once_with(
            grabber_name="tv_grab_na",
            config_name="myconfig",
            days=14,
            offset=2,
            extra_args=None,
        )

    @patch("services.epg_sync_service.XmltvGrabberService.run_grabber")
    def test_sync_grabber_failure(self, mock_run_grabber):
        """Handle grabber execution failure"""
        source = Mock()
        source.xmltv_grabber = "tv_grab_na"
        source.xmltv_config_name = "myconfig"
        source.xmltv_days = 7
        source.xmltv_offset = 0
        source.xmltv_extra_args = None

        mock_run_grabber.return_value = (False, None, "Grabber not found")

        success, message, stats = EpgSyncService.sync_xmltv_grabber_source(source)

        assert success is False
        assert "grabber failed" in message.lower()

    @patch("services.epg_sync_service.XmltvGrabberService.run_grabber")
    @patch("services.epg_sync_service.sync_epg_source")
    @patch("services.epg_sync_service.save_to_cache")
    def test_sync_grabber_with_extra_args(self, mock_cache, mock_sync, mock_run_grabber):
        """Sync grabber with extra arguments"""
        source = Mock()
        source.id = 2
        source.xmltv_grabber = "tv_grab_custom"
        source.xmltv_config_name = "config"
        source.xmltv_days = 10
        source.xmltv_offset = 1
        source.xmltv_extra_args = '{"key": "value"}'

        mock_run_grabber.return_value = (True, b"<xml></xml>", None)
        mock_sync.return_value = {"channels_added": 5, "channels_updated": 0}

        success, message, stats = EpgSyncService.sync_xmltv_grabber_source(source)

        assert success is True
        args, kwargs = mock_run_grabber.call_args
        assert kwargs["extra_args"] == {"key": "value"}


class TestSyncPpvEventsSource:
    """Test sync_ppv_events_source method"""

    # Note: PPVEpgService is imported inside the function, so full integration
    # testing is done through route tests. This tests the dispatcher only.


class TestUpdateSourceSyncStatus:
    """Test update_source_sync_status method"""

    @patch("services.epg_sync_service.db.session.commit")
    def test_update_sync_status_success(self, mock_commit):
        """Update sync status for successful sync"""
        source = Mock()
        stats = {"channels_added": 10, "channels_updated": 5}

        EpgSyncService.update_source_sync_status(source, True, "Sync complete", stats)

        assert source.last_sync_status == "success"
        assert source.last_sync_message == "Sync complete"
        assert source.channel_count == 15
        mock_commit.assert_called_once()

    @patch("services.epg_sync_service.db.session.commit")
    def test_update_sync_status_failure(self, mock_commit):
        """Update sync status for failed sync"""
        source = Mock()
        stats = {}

        EpgSyncService.update_source_sync_status(source, False, "Sync failed", stats)

        assert source.last_sync_status == "error"
        assert source.last_sync_message == "Sync failed"
        mock_commit.assert_called_once()

    @patch("services.epg_sync_service.db.session.commit")
    def test_update_sync_status_sets_timestamp(self, mock_commit):
        """Update sync status sets last_sync timestamp"""
        source = Mock()
        before = datetime.now(timezone.utc).replace(tzinfo=None)

        EpgSyncService.update_source_sync_status(source, True, "OK", {})

        after = datetime.now(timezone.utc).replace(tzinfo=None)
        assert before <= source.last_sync <= after

    @patch("services.epg_sync_service.db.session.commit")
    def test_update_sync_status_with_empty_stats(self, mock_commit):
        """Update sync status with empty stats"""
        source = Mock()
        source.id = 1

        EpgSyncService.update_source_sync_status(source, True, "Processed", {})

        assert source.last_sync_status == "success"
        # If stats is empty, channel_count should not be updated
        mock_commit.assert_called_once()
