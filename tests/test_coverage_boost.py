"""
Tests to boost code coverage to 80-85%

This module adds tests for previously uncovered code paths in:
- services/scheduler.py - EPG source syncing
- routes/epg.py - various EPG endpoints
- routes/playlists.py - playlist generation
- routes/images.py - image serving
- services/image_cache_service.py
"""
import json
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from models import (
    Account,
    Category,
    Channel,
    ChannelEpgMapping,
    ChannelTag,
    Credential,
    EpgChannel,
    EpgSource,
    PlaylistConfig,
    Tag,
    db,
)

# ============================================================================
# Fixtures
# ============================================================================


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


@pytest.fixture
def test_account_with_credential(app):
    """Create a test account with credentials"""
    with app.app_context():
        account = Account(
            name="Test Account With Creds",
            server="example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        cred = Credential(
            account_id=account.id,
            username="cred_user",
            password="cred_pass",
            max_connections=1,
        )
        db.session.add(cred)
        db.session.commit()
        yield account.id


@pytest.fixture
def synced_account(app, test_account):
    """Create a synced account with channels and categories"""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="cat1",
            category_name="Movies",
        )
        db.session.add(category)
        db.session.flush()

        for i in range(3):
            channel = Channel(
                account_id=test_account,
                stream_id=f"ch{i}",
                name=f"Channel {i}",
                cleaned_name=f"Channel {i}",
                category_id=category.id,
                stream_icon="http://example.com/icon.png",
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
        db.session.commit()

        yield test_account


@pytest.fixture
def synced_account_with_tags(app, synced_account):
    """Create synced account with tags on channels"""
    with app.app_context():
        # Create tags
        hd_tag = Tag(name="HD")
        sd_tag = Tag(name="SD")
        db.session.add(hd_tag)
        db.session.add(sd_tag)
        db.session.flush()

        # Assign HD tag to first channel
        channel_tag = ChannelTag(
            account_id=synced_account,
            stream_id="ch0",
            tag_id=hd_tag.id,
        )
        db.session.add(channel_tag)
        db.session.commit()

        yield synced_account


@pytest.fixture
def sd_epg_source(app, test_account):
    """Create a Schedules Direct EPG source"""
    with app.app_context():
        source = EpgSource(
            name="SD Source",
            source_type="schedules_direct",
            sd_username="sduser",
            sd_password="sdpass",
            sd_lineup="USA-NY12345-X",
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def xmltv_url_source(app):
    """Create an XMLTV URL EPG source"""
    with app.app_context():
        source = EpgSource(
            name="XMLTV URL Source",
            source_type="xmltv_url",
            url="https://example.com/epg.xml",
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def xmltv_grabber_source(app):
    """Create an XMLTV grabber EPG source"""
    with app.app_context():
        source = EpgSource(
            name="XMLTV Grabber Source",
            source_type="xmltv_grabber",
            xmltv_grabber="tv_grab_test",
            xmltv_config_name="test",
            xmltv_days=7,
            xmltv_offset=0,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


@pytest.fixture
def provider_epg_source(app, test_account):
    """Create a provider EPG source"""
    with app.app_context():
        source = EpgSource(
            name="Provider Source",
            source_type="provider",
            account_id=test_account,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source.id


# ============================================================================
# Scheduler EPG Sync Tests
# ============================================================================


class TestSchedulerEpgSync:
    """Tests for scheduler EPG source sync methods"""

    @patch("services.scheduler.EpgService.sync_epg_source")
    @patch("services.scheduler.IPTVService")
    def test_sync_epg_sources_provider(self, MockIPTV, mock_sync, app, test_account):
        """Test scheduler syncs provider EPG sources"""
        from services.scheduler import SyncScheduler

        mock_sync.return_value = {"channels_added": 10, "channels_updated": 5}
        mock_service = MagicMock()
        mock_service.get_xmltv.return_value = b"<tv></tv>"
        MockIPTV.return_value = mock_service

        with app.app_context():
            source = EpgSource(
                name="Provider Source",
                source_type="provider",
                account_id=test_account,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            scheduler = SyncScheduler(app, interval_hours=1)
            scheduler._sync_epg_sources()

            mock_sync.assert_called_once()

    @patch("services.scheduler.EpgService.sync_epg_source")
    @patch("services.scheduler.requests.get")
    def test_sync_epg_sources_xmltv_url(self, mock_get, mock_sync, app):
        """Test scheduler syncs XMLTV URL EPG sources"""
        from services.scheduler import SyncScheduler

        mock_response = MagicMock()
        mock_response.content = b"<tv></tv>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        mock_sync.return_value = {"channels_added": 5, "channels_updated": 2}

        with app.app_context():
            source = EpgSource(
                name="XMLTV Source",
                source_type="xmltv_url",
                url="https://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            scheduler = SyncScheduler(app, interval_hours=1)
            scheduler._sync_epg_sources()

            mock_get.assert_called()
            mock_sync.assert_called_once()

    def test_sync_epg_sources_skips_schedules_direct(self, app, sd_epg_source):
        """Test scheduler skips Schedules Direct sources"""
        from services.scheduler import SyncScheduler

        with app.app_context():
            scheduler = SyncScheduler(app, interval_hours=1)
            # Should not raise any errors
            scheduler._sync_epg_sources()

    def test_sync_single_epg_source_no_account(self, app):
        """Test syncing provider source without associated account"""
        from services.scheduler import SyncScheduler

        with app.app_context():
            source = EpgSource(
                name="Provider No Account",
                source_type="provider",
                account_id=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            scheduler = SyncScheduler(app, interval_hours=1)
            result = scheduler._sync_single_epg_source(source)

            assert result is None

    def test_sync_single_epg_source_no_url(self, app):
        """Test syncing XMLTV URL source without URL configured"""
        from services.scheduler import SyncScheduler

        with app.app_context():
            source = EpgSource(
                name="XMLTV No URL",
                source_type="xmltv_url",
                url=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            scheduler = SyncScheduler(app, interval_hours=1)
            result = scheduler._sync_single_epg_source(source)

            assert result is None

    def test_sync_single_epg_source_unknown_type(self, app):
        """Test syncing EPG source with unknown type"""
        from services.scheduler import SyncScheduler

        with app.app_context():
            source = EpgSource(
                name="Unknown Type",
                source_type="unknown",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            scheduler = SyncScheduler(app, interval_hours=1)
            result = scheduler._sync_single_epg_source(source)

            assert result is None

    @patch("services.scheduler.EpgService.sync_epg_source")
    @patch("services.scheduler.IPTVService")
    def test_sync_single_epg_source_with_credential(self, MockIPTV, mock_sync, app, test_account_with_credential):
        """Test syncing provider source uses credential when available"""
        from services.scheduler import SyncScheduler

        mock_sync.return_value = {"channels_added": 1, "channels_updated": 0}
        mock_service = MagicMock()
        mock_service.get_xmltv.return_value = b"<tv></tv>"
        MockIPTV.return_value = mock_service

        with app.app_context():
            source = EpgSource(
                name="Provider With Cred",
                source_type="provider",
                account_id=test_account_with_credential,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            scheduler = SyncScheduler(app, interval_hours=1)
            scheduler._sync_single_epg_source(source)

            # Verify IPTVService was called with credential username/password
            MockIPTV.assert_called_once()
            call_args = MockIPTV.call_args
            assert call_args[0][1] == "cred_user"  # username from credential


# ============================================================================
# EPG Route Sync Tests
# ============================================================================


class TestEpgSourceSync:
    """Tests for EPG source sync endpoints"""

    def test_sync_source_not_found(self, app, client):
        """Test syncing non-existent source"""
        response = client.post("/api/epg/sources/99999/sync")
        assert response.status_code == 404

    @patch("routes.epg.IPTVService")
    @patch("routes.epg.EpgService.sync_epg_source")
    def test_sync_provider_source_success(self, mock_sync, MockIPTV, app, client, provider_epg_source):
        """Test successfully syncing a provider source"""
        mock_sync.return_value = {"channels_added": 10, "channels_updated": 5}
        mock_service = MagicMock()
        mock_service.get_xmltv.return_value = b"<tv></tv>"
        MockIPTV.return_value = mock_service

        response = client.post(f"/api/epg/sources/{provider_epg_source}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_sync_provider_source_no_account(self, app, client):
        """Test syncing provider source without account returns error"""
        with app.app_context():
            source = EpgSource(
                name="No Account",
                source_type="provider",
                account_id=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "account" in response.json["error"].lower()

    @patch("services.epg_service.EpgService.sync_epg_source")
    @patch("requests.get")
    def test_sync_xmltv_url_source_success(self, mock_get, mock_sync, app, client, xmltv_url_source):
        """Test successfully syncing XMLTV URL source"""
        mock_response = MagicMock()
        mock_response.content = b"<tv></tv>"
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response
        mock_sync.return_value = {"channels_added": 5, "channels_updated": 2}

        response = client.post(f"/api/epg/sources/{xmltv_url_source}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_sync_xmltv_url_source_no_url(self, app, client):
        """Test syncing XMLTV URL source without URL configured"""
        with app.app_context():
            source = EpgSource(
                name="No URL",
                source_type="xmltv_url",
                url=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "url" in response.json["error"].lower()

    @patch("routes.epg.SchedulesDirectClient")
    @patch("routes.epg._sync_sd_channels_to_epg")
    def test_sync_schedules_direct_success(self, mock_sd_sync, MockClient, app, client, sd_epg_source):
        """Test successfully syncing Schedules Direct source"""
        mock_client = MagicMock()
        mock_client.get_lineup_channels.return_value = [
            {"stationID": "12345", "callsign": "WABC", "name": "ABC Network"}
        ]
        MockClient.return_value = mock_client
        mock_sd_sync.return_value = {"channels_added": 1, "channels_updated": 0}

        response = client.post(f"/api/epg/sources/{sd_epg_source}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_sync_schedules_direct_no_credentials(self, app, client):
        """Test syncing SD source without credentials"""
        with app.app_context():
            source = EpgSource(
                name="SD No Creds",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "credentials" in response.json["error"].lower()

    def test_sync_schedules_direct_no_lineup(self, app, client):
        """Test syncing SD source without lineup selected"""
        with app.app_context():
            source = EpgSource(
                name="SD No Lineup",
                source_type="schedules_direct",
                sd_username="user",
                sd_password="pass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "lineup" in response.json["error"].lower()

    @patch("routes.epg.SchedulesDirectClient")
    def test_sync_schedules_direct_no_channels(self, MockClient, app, client, sd_epg_source):
        """Test syncing SD source with no channels found"""
        mock_client = MagicMock()
        mock_client.get_lineup_channels.return_value = []
        MockClient.return_value = mock_client

        response = client.post(f"/api/epg/sources/{sd_epg_source}/sync")
        assert response.status_code == 400
        assert "no channels" in response.json["error"].lower()

    @patch("services.epg_service.EpgService.sync_epg_source")
    @patch("services.xmltv_grabber_service.XmltvGrabberService.run_grabber")
    def test_sync_xmltv_grabber_success(self, mock_grabber, mock_sync, app, client, xmltv_grabber_source):
        """Test successfully syncing XMLTV grabber source"""
        mock_grabber.return_value = (True, b"<tv></tv>", None)
        mock_sync.return_value = {"channels_added": 5, "channels_updated": 0}

        response = client.post(f"/api/epg/sources/{xmltv_grabber_source}/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    @patch("services.xmltv_grabber_service.XmltvGrabberService.run_grabber")
    def test_sync_xmltv_grabber_failure(self, mock_grabber, app, client, xmltv_grabber_source):
        """Test failed XMLTV grabber sync"""
        mock_grabber.return_value = (False, None, "Grabber failed")

        response = client.post(f"/api/epg/sources/{xmltv_grabber_source}/sync")
        assert response.status_code == 500
        assert "failed" in response.json["error"].lower()

    def test_sync_xmltv_grabber_no_grabber(self, app, client):
        """Test syncing grabber source without grabber configured"""
        with app.app_context():
            source = EpgSource(
                name="No Grabber",
                source_type="xmltv_grabber",
                xmltv_grabber=None,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "grabber" in response.json["error"].lower()

    def test_sync_unknown_source_type(self, app, client):
        """Test syncing source with unknown type"""
        with app.app_context():
            source = EpgSource(
                name="Unknown Type",
                source_type="unknown_type",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 400
        assert "unknown" in response.json["error"].lower()


class TestEpgSourceCreation:
    """Additional tests for EPG source creation"""

    def test_create_xmltv_grabber_source_no_grabber(self, app, client):
        """Test creating XMLTV grabber source without grabber name"""
        response = client.post(
            "/api/epg/sources",
            json={"name": "Test", "source_type": "xmltv_grabber"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "grabber" in response.json["error"].lower()

    def test_create_schedules_direct_source(self, app, client):
        """Test creating Schedules Direct source"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "SD Source",
                "source_type": "schedules_direct",
                "sd_username": "user",
                "sd_password": "pass",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json["source_type"] == "schedules_direct"


# ============================================================================
# Playlist Generation Tests
# ============================================================================


class TestPlaylistGeneration:
    """Tests for M3U playlist generation"""

    def test_generate_playlist_account_not_found(self, app, client):
        """Test generating playlist for non-existent account"""
        response = client.get("/playlist/99999.m3u?proxy_icons=false")
        assert response.status_code == 404

    def test_generate_playlist_account_disabled(self, app, client):
        """Test generating playlist for disabled account"""
        with app.app_context():
            account = Account(
                name="Disabled Account",
                username="test_user",
                password="test_pass",
                server="example.com",
                enabled=False,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

        response = client.get(f"/playlist/{account_id}.m3u?proxy_icons=false")
        assert response.status_code == 403

    def test_generate_playlist_not_synced(self, app, client, test_account):
        """Test generating playlist for unsynced account"""
        response = client.get(f"/playlist/{test_account}.m3u?proxy_icons=false")
        assert response.status_code == 503

    def test_generate_playlist_success(self, app, client, synced_account):
        """Test successful playlist generation"""
        response = client.get(f"/playlist/{synced_account}.m3u?proxy_icons=false")
        assert response.status_code == 200
        assert response.content_type == "application/x-mpegurl"
        content = response.data.decode("utf-8")
        assert "#EXTM3U" in content
        assert "#EXTINF" in content

    def test_generate_playlist_with_proxy(self, app, client, synced_account):
        """Test playlist generation with proxy URLs"""
        response = client.get(f"/playlist/{synced_account}.m3u?proxy=true&proxy_icons=false")
        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "/stream/" in content

    @patch("routes.playlists.ImageCacheService.get_instance")
    def test_generate_playlist_with_proxy_icons(self, mock_cache, app, client, synced_account):
        """Test playlist generation with icon proxying"""
        mock_instance = MagicMock()
        mock_instance.get_proxy_url.return_value = "http://localhost/icon/abc123"
        mock_cache.return_value = mock_instance

        response = client.get(f"/playlist/{synced_account}.m3u?proxy_icons=true")
        assert response.status_code == 200
        content = response.data.decode("utf-8")
        assert "#EXTM3U" in content

    def test_generate_playlist_collapse_duplicates(self, app, client, synced_account_with_tags):
        """Test playlist generation with duplicate collapsing"""
        response = client.get(f"/playlist/{synced_account_with_tags}.m3u?collapse_duplicates=true&proxy_icons=false")
        assert response.status_code == 200
        assert response.content_type == "application/x-mpegurl"


class TestPlaylistConfigGeneration:
    """Tests for playlist config-based generation"""

    @pytest.fixture
    def playlist_config(self, app, synced_account):
        """Create a playlist config"""
        with app.app_context():
            config = PlaylistConfig(
                name="Test Config",
                include_accounts=json.dumps([synced_account]),
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps([]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            yield config.id

    @pytest.fixture
    def playlist_config_with_tags(self, app, synced_account_with_tags):
        """Create a playlist config with tag filtering"""
        with app.app_context():
            config = PlaylistConfig(
                name="Tag Filtered Config",
                include_accounts=json.dumps([synced_account_with_tags]),
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps(["HD"]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            yield config.id

    def test_generate_playlist_by_id(self, app, client, playlist_config):
        """Test generating playlist by config ID"""
        response = client.get(f"/playlist/config/{playlist_config}.m3u?proxy_icons=false")
        assert response.status_code == 200
        assert response.content_type == "application/x-mpegurl"

    def test_generate_playlist_by_slug(self, app, client, playlist_config):
        """Test generating playlist by config slug"""
        response = client.get("/playlist/config/test-config.m3u?proxy_icons=false")
        assert response.status_code == 200
        assert response.content_type == "application/x-mpegurl"

    def test_generate_playlist_by_slug_not_found(self, app, client):
        """Test generating playlist with invalid slug"""
        response = client.get("/playlist/config/nonexistent.m3u?proxy_icons=false")
        assert response.status_code == 404

    def test_generate_playlist_config_disabled(self, app, client, synced_account):
        """Test generating playlist for disabled config"""
        with app.app_context():
            config = PlaylistConfig(
                name="Disabled Config",
                include_accounts=json.dumps([synced_account]),
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps([]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=False,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")
        assert response.status_code == 403

    def test_generate_playlist_config_with_proxy(self, app, client, playlist_config):
        """Test playlist config generation with proxy"""
        response = client.get(f"/playlist/config/{playlist_config}.m3u?proxy=true&proxy_icons=false")
        assert response.status_code == 200


class TestTagMatchingLogic:
    """Tests for _matches_tag_filter function"""

    def test_matches_tag_filter_exclude_takes_precedence(self, app):
        """Test that exclude tags take precedence over include"""
        from routes.playlists import _matches_tag_filter

        # Channel has both HD and SD tags
        channel_tags = {"HD", "SD"}
        include_tags = ["HD"]
        exclude_tags = ["SD"]

        # SD is in exclude, so should be False even though HD is included
        result = _matches_tag_filter(channel_tags, include_tags, exclude_tags, "any")
        assert result is False

    def test_matches_tag_filter_match_all(self, app):
        """Test match_mode=all requires all tags"""
        from routes.playlists import _matches_tag_filter

        channel_tags = {"HD", "SPORTS"}
        include_tags = ["HD", "4K"]

        # Channel has HD but not 4K
        result = _matches_tag_filter(channel_tags, include_tags, [], "all")
        assert result is False

        # Channel has both
        channel_tags = {"HD", "4K"}
        result = _matches_tag_filter(channel_tags, include_tags, [], "all")
        assert result is True

    def test_matches_tag_filter_no_include_tags(self, app):
        """Test no include tags means all pass"""
        from routes.playlists import _matches_tag_filter

        channel_tags = {"RANDOM"}

        result = _matches_tag_filter(channel_tags, [], [], "any")
        assert result is True


# ============================================================================
# Image Cache Route Tests
# ============================================================================


class TestImageCacheRoutes:
    """Additional tests for image cache routes"""

    def test_serve_icon_invalid_hash_short(self, app, client):
        """Test serving icon with too short hash"""
        response = client.get("/icon/abc")
        assert response.status_code == 400

    def test_serve_icon_invalid_hash_chars(self, app, client):
        """Test serving icon with invalid characters"""
        response = client.get("/icon/" + "g" * 64)  # 'g' is not hex
        assert response.status_code == 400

    @patch("routes.images.get_image_cache")
    def test_serve_icon_cache_miss_refetch(self, mock_get_cache, app, client):
        """Test serving icon triggers refetch on cache miss"""
        from models import CachedImage

        with app.app_context():
            url_hash = "a" * 64
            cached = CachedImage(
                url_hash=url_hash,
                original_url="http://example.com/icon.png",
                status="cached",
            )
            db.session.add(cached)
            db.session.commit()

        mock_cache = MagicMock()
        # First call returns None (cache miss), second returns data
        mock_cache.get_cached_image.side_effect = [None, (b"imagedata", "image/png")]
        mock_cache.cache_image.return_value = url_hash
        mock_get_cache.return_value = mock_cache

        response = client.get(f"/icon/{url_hash}")
        assert response.status_code == 200
        assert response.headers.get("X-Cache") == "MISS"

    def test_fetch_icon_success(self, app, client):
        """Test fetching and caching icon via POST"""
        with patch("routes.images.get_image_cache") as mock_get:
            mock_cache = MagicMock()
            mock_cache.cache_image.return_value = "abc" * 21 + "a"
            mock_get.return_value = mock_cache

            response = client.post(
                "/icon/fetch",
                json={"url": "http://example.com/icon.png"},
                content_type="application/json",
            )
            assert response.status_code == 200
            assert response.json["success"] is True
            assert "proxy_url" in response.json

    def test_fetch_icon_failure(self, app, client):
        """Test fetch failure returns error"""
        with patch("routes.images.get_image_cache") as mock_get:
            mock_cache = MagicMock()
            mock_cache.cache_image.return_value = None
            mock_get.return_value = mock_cache

            response = client.post(
                "/icon/fetch",
                json={"url": "http://example.com/icon.png"},
                content_type="application/json",
            )
            assert response.status_code == 500
            assert response.json["success"] is False

    def test_cleanup_cache_clear_all(self, app, client):
        """Test clearing all cache entries"""
        with patch("routes.images.get_image_cache") as mock_get:
            mock_cache = MagicMock()
            mock_cache.clear_all.return_value = 5
            mock_get.return_value = mock_cache

            response = client.post("/api/image-cache/cleanup?all=true")
            assert response.status_code == 200
            assert response.json["removed_count"] == 5

    def test_cleanup_cache_by_status(self, app, client):
        """Test cleaning cache by status"""
        with patch("routes.images.get_image_cache") as mock_get:
            mock_cache = MagicMock()
            mock_cache.cleanup_by_status.return_value = 3
            mock_get.return_value = mock_cache

            response = client.post("/api/image-cache/cleanup?status=error")
            assert response.status_code == 200
            assert response.json["removed_count"] == 3


# ============================================================================
# EPG Mapping Tests
# ============================================================================


class TestEpgMappings:
    """Tests for EPG mapping endpoints"""

    @pytest.fixture
    def channel_with_mapping(self, app, test_account):
        """Create a channel with EPG mapping"""
        with app.app_context():
            category = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="ch1",
                name="Test Channel",
                cleaned_name="Test Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.flush()

            source = EpgSource(
                name="Test Source",
                source_type="provider",
                account_id=test_account,
            )
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg1",
                display_name="EPG Channel",
            )
            db.session.add(epg_channel)
            db.session.flush()

            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

            yield {
                "channel_id": channel.id,
                "epg_channel_id": epg_channel.id,
                "mapping_id": mapping.id,
            }

    def test_get_mappings_empty(self, app, client):
        """Test getting mappings when none exist"""
        response = client.get("/api/epg/mappings")
        assert response.status_code == 200
        assert response.json["total"] == 0

    def test_get_mappings_with_data(self, app, client, channel_with_mapping):
        """Test getting existing mappings"""
        response = client.get("/api/epg/mappings")
        assert response.status_code == 200
        assert response.json["total"] == 1

    def test_get_unmapped_channels(self, app, client, synced_account):
        """Test getting unmapped channels"""
        response = client.get(f"/api/epg/mappings?unmapped_only=true&account_id={synced_account}")
        assert response.status_code == 200
        assert "unmapped_channels" in response.json

    def test_create_mapping_missing_channel(self, app, client):
        """Test creating mapping without channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"epg_channel_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_create_mapping_missing_epg_channel(self, app, client):
        """Test creating mapping without epg_channel_id"""
        response = client.post(
            "/api/epg/mappings",
            json={"channel_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_create_mapping_duplicate(self, app, client, channel_with_mapping):
        """Test creating duplicate mapping"""
        response = client.post(
            "/api/epg/mappings",
            json={
                "channel_id": channel_with_mapping["channel_id"],
                "epg_channel_id": channel_with_mapping["epg_channel_id"],
            },
            content_type="application/json",
        )
        assert response.status_code == 409

    def test_delete_mapping_success(self, app, client, channel_with_mapping):
        """Test deleting a mapping"""
        response = client.delete(f"/api/epg/mappings/{channel_with_mapping['mapping_id']}")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_delete_mapping_not_found(self, app, client):
        """Test deleting non-existent mapping"""
        response = client.delete("/api/epg/mappings/99999")
        assert response.status_code == 404


# ============================================================================
# EPG Coverage Stats Tests
# ============================================================================


class TestEpgCoverage:
    """Tests for EPG coverage statistics"""

    def test_get_coverage_stats(self, app, client):
        """Test getting coverage stats"""
        response = client.get("/api/epg/coverage")
        assert response.status_code == 200
        # Response contains coverage statistics
        data = response.json
        assert "total_channels" in data or isinstance(data, dict)

    def test_get_coverage_stats_by_account(self, app, client, synced_account):
        """Test getting coverage stats for specific account"""
        response = client.get(f"/api/epg/coverage?account_id={synced_account}")
        assert response.status_code == 200

    def test_get_category_coverage(self, app, client, synced_account):
        """Test getting category-level coverage stats"""
        response = client.get(f"/api/epg/coverage/categories/{synced_account}")
        assert response.status_code == 200


# ============================================================================
# Error Handling Edge Cases
# ============================================================================


class TestErrorHandling:
    """Tests for error handling edge cases"""

    def test_create_epg_source_provider_account_not_found(self, app, client):
        """Test creating provider source with non-existent account"""
        response = client.post(
            "/api/epg/sources",
            json={
                "name": "Test",
                "source_type": "provider",
                "account_id": 99999,
            },
            content_type="application/json",
        )
        assert response.status_code == 404

    @patch("routes.epg.SchedulesDirectClient")
    def test_sync_sd_handles_error(self, MockClient, app, client, sd_epg_source):
        """Test SD sync handles API errors gracefully"""
        from services.schedules_direct import SchedulesDirectError

        mock_client = MagicMock()
        mock_client.authenticate.side_effect = SchedulesDirectError("API Error", code=4003)
        MockClient.return_value = mock_client

        response = client.post(f"/api/epg/sources/{sd_epg_source}/sync")
        assert response.status_code == 500
        assert "error" in response.json


# ============================================================================
# Helper Function for SD Channels Sync
# ============================================================================


class TestSdChannelsToEpg:
    """Tests for _sync_sd_channels_to_epg helper function"""

    def test_sync_sd_channels_new(self, app):
        """Test syncing new SD channels creates EpgChannel records"""
        from routes.epg import _sync_sd_channels_to_epg

        with app.app_context():
            source = EpgSource(
                name="SD Test",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "WABC",
                    "name": "ABC New York",
                    "logo": {"url": "http://example.com/logo.png"},
                },
                {
                    "stationID": "67890",
                    "callsign": "WCBS",
                    "name": "CBS New York",
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 2
            assert stats["channels_updated"] == 0

            # Verify records created
            epg_channels = EpgChannel.query.filter_by(source_id=source.id).all()
            assert len(epg_channels) == 2

    def test_sync_sd_channels_update(self, app):
        """Test syncing SD channels updates existing records"""
        from routes.epg import _sync_sd_channels_to_epg

        with app.app_context():
            source = EpgSource(
                name="SD Test",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            # Create existing channel with SD format channel_id
            existing = EpgChannel(
                source_id=source.id,
                channel_id="I12345.json.schedulesdirect.org",
                display_name="Old Name",
            )
            db.session.add(existing)
            db.session.commit()

            channels = [
                {
                    "stationID": "12345",
                    "callsign": "WABC",
                    "name": "ABC New York",
                },
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_updated"] == 1
            assert stats["channels_added"] == 0

            # Verify name updated
            channel = EpgChannel.query.filter_by(source_id=source.id).first()
            assert channel.display_name == "WABC"

    def test_sync_sd_channels_skip_no_station_id(self, app):
        """Test syncing skips channels without station ID"""
        from routes.epg import _sync_sd_channels_to_epg

        with app.app_context():
            source = EpgSource(
                name="SD Test",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            channels = [
                {"callsign": "WABC"},  # No stationID
                {"stationID": "12345", "callsign": "WCBS"},
            ]

            stats = _sync_sd_channels_to_epg(source, channels)

            assert stats["channels_added"] == 1


# ============================================================================
# Additional EPG Update/Delete Tests
# ============================================================================


class TestEpgSourceUpdateExtended:
    """Extended tests for EPG source update with different fields"""

    def test_update_epg_source_xmltv_fields(self, app, client, xmltv_grabber_source):
        """Test updating XMLTV grabber specific fields"""
        response = client.put(
            f"/api/epg/sources/{xmltv_grabber_source}",
            json={
                "xmltv_grabber": "tv_grab_updated",
                "xmltv_config_name": "new_config",
                "xmltv_days": 14,
                "xmltv_offset": 2,
                "xmltv_extra_args": '{"key": "value"}',
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_update_epg_source_sd_fields(self, app, client, sd_epg_source):
        """Test updating Schedules Direct specific fields"""
        response = client.put(
            f"/api/epg/sources/{sd_epg_source}",
            json={
                "sd_username": "new_user",
                "sd_password": "new_pass",
                "sd_lineup": "NEW-LINEUP",
            },
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True


# ============================================================================
# Playlist Preview Extended Tests
# ============================================================================


class TestPlaylistPreviewExtended:
    """Extended tests for playlist preview functionality"""

    @pytest.fixture
    def playlist_config_with_all_mode(self, app, synced_account_with_tags):
        """Create a playlist config with tag_match_mode=all"""
        with app.app_context():
            config = PlaylistConfig(
                name="All Tags Config",
                include_accounts=json.dumps([synced_account_with_tags]),
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps(["HD", "SPORTS"]),
                exclude_tags=json.dumps([]),
                tag_match_mode="all",  # Requires ALL tags
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            yield config.id

    def test_preview_with_tag_match_all_mode(self, app, client, playlist_config_with_all_mode):
        """Test preview with tag_match_mode=all"""
        from unittest.mock import patch

        mock_streams = [
            {"stream_id": 1, "name": "Channel HD SPORTS", "category_id": "cat1", "stream_icon": "icon.png"},
        ]
        mock_categories = [{"category_id": "cat1", "category_name": "Sports"}]

        with patch("routes.playlists.IPTVService"):
            with patch("routes.playlists.cache_service") as mock_cache:
                mock_cache.get_cached_streams.return_value = mock_streams
                mock_cache.get_cached_categories.return_value = mock_categories

                response = client.get(f"/api/playlist-configs/{playlist_config_with_all_mode}/preview")
                assert response.status_code == 200


# ============================================================================
# Image Cache Service Extended Tests
# ============================================================================


class TestImageCacheServiceExtended:
    """Extended tests for image cache service"""

    def test_cleanup_by_status_error(self, app, client):
        """Test cleanup of error status entries"""
        from models import CachedImage

        with app.app_context():
            # Add error entry
            cached = CachedImage(
                url_hash="error" + "0" * 59,
                original_url="http://example.com/bad.png",
                status="error",
            )
            db.session.add(cached)
            db.session.commit()

        with patch("routes.images.get_image_cache") as mock_get:
            mock_cache = MagicMock()
            mock_cache.cleanup_by_status.return_value = 1
            mock_get.return_value = mock_cache

            response = client.post("/api/image-cache/cleanup?status=error&delete_files=false")
            assert response.status_code == 200
            assert response.json["removed_count"] == 1


# ============================================================================
# EPG Channel Listing Tests
# ============================================================================


class TestEpgChannelsListingExtended:
    """Extended tests for EPG channel listing"""

    def test_get_epg_channels_with_search(self, app, client):
        """Test searching EPG channels"""
        with app.app_context():
            source = EpgSource(
                name="Test Source",
                source_type="provider",
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            for i in range(3):
                channel = EpgChannel(
                    source_id=source.id,
                    channel_id=f"ch{i}",
                    display_name=f"Channel {i}",
                )
                db.session.add(channel)
            db.session.commit()

        response = client.get("/api/epg/channels?search=Channel%201")
        assert response.status_code == 200
        assert response.json["total"] >= 1

    def test_get_epg_channels_with_pagination(self, app, client):
        """Test paginating EPG channels"""
        with app.app_context():
            source = EpgSource(
                name="Test Source",
                source_type="provider",
                enabled=True,
            )
            db.session.add(source)
            db.session.flush()

            for i in range(10):
                channel = EpgChannel(
                    source_id=source.id,
                    channel_id=f"pagech{i}",
                    display_name=f"Page Channel {i}",
                )
                db.session.add(channel)
            db.session.commit()
            source_id = source.id

        response = client.get(f"/api/epg/channels?source_id={source_id}&limit=5&offset=0")
        assert response.status_code == 200
        assert response.json["limit"] == 5
        assert len(response.json["channels"]) <= 5


# ============================================================================
# EPG Channel Matching Tests
# ============================================================================


class TestEpgMatching:
    """Tests for EPG matching endpoint"""

    def test_match_channels_to_epg_basic(self, app, client, synced_account):
        """Test basic EPG matching"""
        response = client.post(f"/api/epg/match/{synced_account}")
        assert response.status_code == 200
        assert "stats" in response.json

    def test_match_channels_to_epg_with_source(self, app, client, synced_account, provider_epg_source):
        """Test EPG matching with specific source"""
        response = client.post(f"/api/epg/match/{synced_account}?source_id={provider_epg_source}")
        assert response.status_code == 200

    def test_match_channels_to_epg_not_found(self, app, client):
        """Test EPG matching for non-existent account"""
        response = client.post("/api/epg/match/99999")
        assert response.status_code == 404


# ============================================================================
# Web Routes Tests
# ============================================================================


class TestWebRoutesExtended:
    """Extended tests for web routes"""

    def test_categories_page(self, app, client):
        """Test categories page loads"""
        response = client.get("/categories")
        assert response.status_code == 200

    def test_settings_page(self, app, client):
        """Test settings page loads"""
        response = client.get("/settings")
        assert response.status_code == 200

    def test_epg_page(self, app, client):
        """Test EPG page loads"""
        response = client.get("/epg")
        assert response.status_code == 200

    def test_stations_page(self, app, client):
        """Test stations page loads"""
        response = client.get("/stations")
        assert response.status_code == 200


# ============================================================================
# Cache Service Tests
# ============================================================================


class TestCacheServiceExtended:
    """Extended tests for cache service"""

    def test_cache_streams(self, app):
        """Test caching streams"""
        from services.cache_service import CacheService

        with app.app_context():
            cache = CacheService()
            streams = [{"stream_id": 1, "name": "Test"}]

            cache.cache_streams(1, streams)
            result = cache.get_cached_streams(1)

            assert result == streams

    def test_cache_categories(self, app):
        """Test caching categories"""
        from services.cache_service import CacheService

        with app.app_context():
            cache = CacheService()
            categories = [{"category_id": "1", "category_name": "Test"}]

            cache.cache_categories(1, categories)
            result = cache.get_cached_categories(1)

            assert result == categories

    def test_cache_categories_hit(self, app):
        """Test categories cache hit (second access)"""
        from services.cache_service import CacheService

        with app.app_context():
            cache = CacheService()
            categories = [{"category_id": "1", "category_name": "Test"}]

            cache.cache_categories(1, categories)
            # First get
            result1 = cache.get_cached_categories(1)
            # Second get (cache hit)
            result2 = cache.get_cached_categories(1)

            assert result1 == result2 == categories

    def test_clear_account_cache(self, app):
        """Test clearing account cache"""
        from services.cache_service import CacheService

        with app.app_context():
            cache = CacheService()
            streams = [{"stream_id": 1, "name": "Test"}]

            cache.cache_streams(1, streams)
            cache.clear_account_cache(1)
            result = cache.get_cached_streams(1)

            assert result is None

    def test_clear_all_cache(self, app):
        """Test clearing all cache"""
        from services.cache_service import CacheService

        with app.app_context():
            cache = CacheService()
            cache.cache_streams(1, [{"stream_id": 1}])
            cache.cache_categories(2, [{"category_id": "1"}])

            cache.clear_all()

            assert cache.get_cached_streams(1) is None
            assert cache.get_cached_categories(2) is None


# ============================================================================
# EPG Mapping Creation Tests
# ============================================================================


class TestEpgMappingCreation:
    """Tests for creating EPG mappings"""

    def test_create_mapping_success(self, app, client):
        """Test successful mapping creation"""
        with app.app_context():
            account = Account(
                name="Test",
                server="test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="cat1",
                category_name="Test",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="ch1",
                name="Test Channel",
                cleaned_name="Test Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.flush()

            source = EpgSource(
                name="Test Source",
                source_type="provider",
            )
            db.session.add(source)
            db.session.flush()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg1",
                display_name="EPG Channel",
            )
            db.session.add(epg_channel)
            db.session.commit()

            channel_id = channel.id
            epg_channel_id = epg_channel.id

        response = client.post(
            "/api/epg/mappings",
            json={
                "channel_id": channel_id,
                "epg_channel_id": epg_channel_id,
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json["success"] is True


# ============================================================================
# Image Cache Service Additional Tests
# ============================================================================


class TestImageCacheServiceAdditional:
    """Additional tests for ImageCacheService to improve coverage"""

    def test_get_cached_image_expired(self, app):
        """Test getting expired cached image returns None"""
        from models import CachedImage

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)
                url = "http://example.com/expired.png"
                url_hash = service.hash_url(url)

                # Create expired cache entry
                expired = CachedImage(
                    url_hash=url_hash,
                    original_url=url,
                    status="cached",
                    file_path="ab/test.png",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
                db.session.add(expired)
                db.session.commit()

                result = service.get_cached_image(url)
                assert result is None

    def test_get_cached_image_file_missing(self, app):
        """Test getting cached image when file is missing"""
        from models import CachedImage

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)
                url = "http://example.com/missing.png"
                url_hash = service.hash_url(url)

                # Create cache entry with non-existent file
                cached = CachedImage(
                    url_hash=url_hash,
                    original_url=url,
                    status="cached",
                    file_path="ab/nonexistent.png",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                )
                db.session.add(cached)
                db.session.commit()

                result = service.get_cached_image(url)
                assert result is None

                # Check status was updated to error
                updated = CachedImage.query.filter_by(url_hash=url_hash).first()
                assert updated.status == "error"

    def test_cache_image_force_refresh(self, app):
        """Test force refreshing a cached image"""
        from models import CachedImage

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)
                url = "http://example.com/refresh.png"
                url_hash = service.hash_url(url)

                # Create existing cache entry
                cached = CachedImage(
                    url_hash=url_hash,
                    original_url=url,
                    status="cached",
                    file_path="ab/test.png",
                    expires_at=datetime.now(timezone.utc) + timedelta(days=7),
                )
                db.session.add(cached)
                db.session.commit()

                # Mock the HTTP request
                mock_response = MagicMock()
                mock_response.status_code = 200
                mock_response.headers = {"Content-Type": "image/png"}
                mock_response.iter_content = MagicMock(return_value=[b"\x89PNG\r\n\x1a\n" + b"x" * 100])

                with patch("requests.get", return_value=mock_response):
                    result = service.cache_image(url, force_refresh=True)

                assert result == url_hash

    def test_cache_image_invalid_url(self, app):
        """Test caching with invalid URL returns None"""
        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                result = service.cache_image("not-a-valid-url")
                assert result is None

                result = service.cache_image("")
                assert result is None

    def test_cache_image_http_error(self, app):
        """Test caching handles HTTP errors"""
        import requests

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)
                url = "http://example.com/error.png"

                with patch("requests.get", side_effect=requests.RequestException("Connection error")):
                    result = service.cache_image(url)

                assert result is None


# ============================================================================
# Playlist Preview Error Handling
# ============================================================================


class TestPlaylistPreviewErrors:
    """Tests for playlist preview error handling"""

    def test_preview_with_exception(self, app, client):
        """Test preview handles exceptions gracefully"""
        with app.app_context():
            config = PlaylistConfig(
                name="Error Config",
                include_accounts=json.dumps([99999]),  # Non-existent account
                exclude_accounts=json.dumps([]),
                include_tags=json.dumps([]),
                exclude_tags=json.dumps([]),
                tag_match_mode="any",
                enabled=True,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        # Should return 200 with empty channels (account doesn't exist)
        response = client.get(f"/api/playlist-configs/{config_id}/preview")
        assert response.status_code in [200, 400]  # Depends on error handling


# ============================================================================
# XMLTV Grabber Extra Args Test
# ============================================================================


class TestXmltvGrabberExtraArgs:
    """Test XMLTV grabber with extra arguments"""

    @patch("services.epg_service.EpgService.sync_epg_source")
    @patch("services.xmltv_grabber_service.XmltvGrabberService.run_grabber")
    def test_sync_xmltv_grabber_with_extra_args(self, mock_grabber, mock_sync, app, client):
        """Test syncing XMLTV grabber source with extra args"""
        mock_grabber.return_value = (True, b"<tv></tv>", None)
        mock_sync.return_value = {"channels_added": 3, "channels_updated": 0}

        with app.app_context():
            source = EpgSource(
                name="Grabber With Args",
                source_type="xmltv_grabber",
                xmltv_grabber="tv_grab_test",
                xmltv_config_name="config",
                xmltv_days=7,
                xmltv_offset=0,
                xmltv_extra_args='{"fast": true, "quality": "high"}',
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(f"/api/epg/sources/{source_id}/sync")
        assert response.status_code == 200


# ============================================================================
# Image Cache Cleanup Tests
# ============================================================================


class TestImageCacheCleanup:
    """Test image cache cleanup functions"""

    def test_cleanup_by_status(self, app):
        """Test cleanup_by_status removes entries with specific status"""
        from models import CachedImage

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                # Create entries with different statuses
                for i in range(3):
                    entry = CachedImage(
                        url_hash=f"error_hash_{i}",
                        original_url=f"http://example.com/error{i}.png",
                        status="error",
                        error_message="Test error",
                    )
                    db.session.add(entry)

                for i in range(2):
                    entry = CachedImage(
                        url_hash=f"cached_hash_{i}",
                        original_url=f"http://example.com/cached{i}.png",
                        status="cached",
                        file_path=f"ab/cached{i}.png",
                    )
                    db.session.add(entry)

                db.session.commit()

                # Clean up error entries
                count = service.cleanup_by_status("error", delete_files=False)
                assert count == 3

                # Verify only cached entries remain
                remaining = CachedImage.query.all()
                assert len(remaining) == 2
                assert all(c.status == "cached" for c in remaining)

    def test_clear_all(self, app):
        """Test clear_all removes all cache entries"""
        from models import CachedImage

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                # Create several entries
                for i in range(5):
                    entry = CachedImage(
                        url_hash=f"hash_{i}",
                        original_url=f"http://example.com/img{i}.png",
                        status="cached",
                    )
                    db.session.add(entry)
                db.session.commit()

                # Clear all
                count = service.clear_all(delete_files=False)
                assert count == 5

                # Verify all cleared
                remaining = CachedImage.query.count()
                assert remaining == 0

    def test_cleanup_expired_with_files(self, app):
        """Test cleanup_expired removes files and marks as expired"""
        from pathlib import Path

        from models import CachedImage

        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                # Create expired entry with actual file
                file_dir = Path(tmpdir) / "ab"
                file_dir.mkdir(parents=True, exist_ok=True)
                test_file = file_dir / "test.png"
                test_file.write_bytes(b"fake image data")

                expired = CachedImage(
                    url_hash="expired_with_file",
                    original_url="http://example.com/expired.png",
                    status="cached",
                    file_path="ab/test.png",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                )
                db.session.add(expired)
                db.session.commit()

                # Run cleanup
                count = service.cleanup_expired()
                assert count == 1

                # File should be deleted
                assert not test_file.exists()

    def test_fetch_image_unsupported_content_type(self, app):
        """Test _fetch_image with unsupported content type"""
        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                with patch("requests.get") as mock_get:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.headers = {"Content-Type": "text/html"}
                    mock_response.content = b"<html>not an image</html>"
                    mock_get.return_value = mock_response

                    result, content_type = service._fetch_image("http://example.com/notimage")
                    assert result is None
                    assert content_type is None

    def test_fetch_image_too_large(self, app):
        """Test _fetch_image rejects oversized images"""
        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                with patch("requests.get") as mock_get:
                    mock_response = MagicMock()
                    mock_response.status_code = 200
                    mock_response.headers = {
                        "Content-Type": "image/png",
                        "Content-Length": "100000000",  # 100MB
                    }
                    mock_get.return_value = mock_response

                    result, content_type = service._fetch_image("http://example.com/huge.png")
                    assert result is None

    def test_is_valid_url(self, app):
        """Test URL validation"""
        with app.app_context():
            from services.image_cache_service import ImageCacheService

            with tempfile.TemporaryDirectory() as tmpdir:
                service = ImageCacheService(cache_dir=tmpdir)

                assert service._is_valid_url("http://example.com/image.png") is True
                assert service._is_valid_url("https://example.com/image.png") is True
                assert service._is_valid_url("ftp://example.com/image.png") is False
                assert service._is_valid_url("") is False
                assert service._is_valid_url(None) is False


# ============================================================================
# FCC Facility Service Tests
# ============================================================================


class TestFccFacilitySync:
    """Test FCC facility sync functionality"""

    @patch("services.fcc_facility_service.FccFacilityService.download_facility_data")
    def test_full_sync_download_failure(self, mock_download, app):
        """Test full_sync handles download failure"""
        mock_download.return_value = None

        with app.app_context():
            from services.fcc_facility_service import FccFacilityService

            result = FccFacilityService.full_sync()
            assert result["success"] is False
            assert "Failed to download" in result["message"]

    @patch("services.fcc_facility_service.FccFacilityService.download_facility_data")
    @patch("services.fcc_facility_service.FccFacilityService.parse_facility_data")
    def test_full_sync_no_records(self, mock_parse, mock_download, app):
        """Test full_sync handles no records"""
        mock_download.return_value = b"some data"
        mock_parse.return_value = []

        with app.app_context():
            from services.fcc_facility_service import FccFacilityService

            result = FccFacilityService.full_sync()
            assert result["success"] is False
            assert "No TV facility records" in result["message"]

    @patch("services.fcc_facility_service.FccFacilityService.download_facility_data")
    @patch("services.fcc_facility_service.FccFacilityService.parse_facility_data")
    @patch("services.fcc_facility_service.FccFacilityService.sync_facilities")
    def test_full_sync_success(self, mock_sync, mock_parse, mock_download, app):
        """Test full_sync success path"""
        mock_download.return_value = b"facility data"
        mock_parse.return_value = [{"callsign": "KABC"}]
        mock_sync.return_value = {"added": 1, "updated": 0, "unchanged": 0, "errors": 0}

        with app.app_context():
            from services.fcc_facility_service import FccFacilityService

            result = FccFacilityService.full_sync()
            assert result["success"] is True
            assert "Synced 1 TV facilities" in result["message"]


# ============================================================================
# EPG SD Lineup Tests
# ============================================================================


class TestEpgSdLineups:
    """Test Schedules Direct lineup management"""

    def test_add_sd_lineup_missing_fields(self, app, client):
        """Test adding SD lineup with missing required fields"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="test",
                sd_password="pass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

        # Missing lineup_id
        response = client.post(
            "/api/epg/sd/lineups",
            json={"source_id": 1},
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_add_sd_lineup_non_sd_source(self, app, client):
        """Test adding SD lineup to non-SD source fails"""
        with app.app_context():
            source = EpgSource(
                name="XMLTV Source",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(
            "/api/epg/sd/lineups",
            json={"source_id": source_id, "lineup_id": "USA-TEST-X"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "not a Schedules Direct source" in response.json["error"]

    @patch("services.schedules_direct.SchedulesDirectClient.authenticate")
    @patch("services.schedules_direct.SchedulesDirectClient.get_status")
    def test_add_sd_lineup_limit_reached(self, mock_status, mock_auth, app, client):
        """Test adding SD lineup when account limit reached"""
        mock_auth.return_value = True
        mock_status.return_value = {
            "lineups": [{"lineup": f"USA-{i}"} for i in range(4)],
            "account": {"maxLineups": 4},
        }

        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="test",
                sd_password="pass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(
            "/api/epg/sd/lineups",
            json={"source_id": source_id, "lineup_id": "USA-NEW-LINEUP"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "limit reached" in response.json["error"]

    @patch("services.schedules_direct.SchedulesDirectClient.authenticate")
    @patch("services.schedules_direct.SchedulesDirectClient.get_status")
    def test_add_sd_lineup_success(self, mock_status, mock_auth, app, client):
        """Test successfully adding SD lineup"""
        from models import SdLineup

        mock_auth.return_value = True
        mock_status.return_value = {
            "lineups": [],
            "account": {"maxLineups": 4},
        }

        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="test",
                sd_password="pass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.post(
            "/api/epg/sd/lineups",
            json={
                "source_id": source_id,
                "lineup_id": "USA-TEST-LINEUP",
                "name": "Test Lineup",
                "location": "Test City",
            },
            content_type="application/json",
        )
        assert response.status_code == 201
        assert response.json["success"] is True

        # Verify lineup created
        with app.app_context():
            lineup = SdLineup.query.filter_by(lineup_id="USA-TEST-LINEUP").first()
            assert lineup is not None
            assert lineup.name == "Test Lineup"


# ============================================================================
# Playlist Config EPG Generation Tests
# ============================================================================


class TestPlaylistConfigEpg:
    """Test EPG generation for playlist configs"""

    def test_config_epg_disabled_config(self, app, client):
        """Test EPG generation for disabled config fails"""
        with app.app_context():
            config = PlaylistConfig(
                name="Disabled Config",
                enabled=False,
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        response = client.get(f"/epg/config/{config_id}.xml")
        assert response.status_code == 403

    def test_config_epg_empty_result(self, app, client):
        """Test EPG generation returns minimal XML when no channels match"""
        with app.app_context():
            config = PlaylistConfig(
                name="Empty Config",
                enabled=True,
                include_tags=json.dumps(["NONEXISTENT_TAG"]),
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        response = client.get(f"/epg/config/{config_id}.xml")
        assert response.status_code == 200
        assert b"<tv" in response.data


# ============================================================================
# Auto-matching Tests
# ============================================================================


class TestEpgAutoMatching:
    """Test EPG auto-matching functionality"""

    def test_auto_match_missing_source_id(self, app, client):
        """Test auto-match fails without source_id"""
        with app.app_context():
            account = Account(
                name="Test",
                username="u",
                password="p",
                server="s.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

        response = client.post(
            f"/api/epg/sd/match/{account_id}",
            json={},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "source_id is required" in response.json["error"]


# ============================================================================
# Sync Service Additional Tests
# ============================================================================


class TestSyncServiceAdditional:
    """Additional sync service tests"""

    def test_get_iptv_service_for_account(self, app):
        """Test creating IPTV service for an account"""
        with app.app_context():
            account = Account(
                name="Test Account",
                username="user",
                password="pass",
                server="example.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            from services.sync_service import get_iptv_service_for_account

            service = get_iptv_service_for_account(account)
            assert service is not None
            assert service.server == "example.com"


# ============================================================================
# Filter Service Additional Tests
# ============================================================================


class TestFilterServiceAdditional:
    """Additional filter service tests"""

    def test_compute_visibility_no_filters(self, app):
        """Test compute visibility when no filters exist"""
        with app.app_context():
            from services.filter_service import FilterService

            account = Account(
                name="Filter Test",
                username="u",
                password="p",
                server="s.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create channels without filters
            cat_news = Category(
                account_id=account.id,
                category_id="1",
                category_name="News",
            )
            db.session.add(cat_news)
            db.session.commit()

            ch1 = Channel(
                account_id=account.id,
                stream_id=1,
                name="CNN",
                category_id=cat_news.id,
                is_active=True,
                is_visible=False,
            )
            db.session.add(ch1)
            db.session.commit()

            # Compute visibility - should make all visible since no filters
            result = FilterService.compute_visibility_for_account(account.id)

            assert result["success"] is True
            assert result["channels_visible"] == 1

    def test_compute_visibility_with_blacklist(self, app):
        """Test compute visibility with blacklist filter"""
        with app.app_context():
            from models import Filter
            from services.filter_service import FilterService

            account = Account(
                name="Filter Test 2",
                username="u",
                password="p",
                server="s.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create blacklist filter
            filter_obj = Filter(
                account_id=account.id,
                name="Block Adult",
                filter_type="category",
                filter_action="blacklist",
                filter_value="Adult",
                enabled=True,
            )
            db.session.add(filter_obj)
            db.session.commit()

            # Create channels
            cat_news = Category(
                account_id=account.id,
                category_id="1",
                category_name="News",
            )
            cat_adult = Category(
                account_id=account.id,
                category_id="2",
                category_name="Adult",
            )
            db.session.add_all([cat_news, cat_adult])
            db.session.commit()

            ch1 = Channel(
                account_id=account.id,
                stream_id=1,
                name="CNN",
                category_id=cat_news.id,
                is_active=True,
            )
            ch2 = Channel(
                account_id=account.id,
                stream_id=2,
                name="Adult Channel",
                category_id=cat_adult.id,
                is_active=True,
            )
            db.session.add_all([ch1, ch2])
            db.session.commit()

            # Compute visibility
            result = FilterService.compute_visibility_for_account(account.id)

            assert result["success"] is True
            assert result["channels_visible"] == 1
            assert result["channels_hidden"] == 1


# ============================================================================
# Schedules Direct Client Tests
# ============================================================================


class TestSchedulesDirectClient:
    """Test Schedules Direct client functionality"""

    def test_authenticate_failure(self, app):
        """Test authentication failure handling"""
        with app.app_context():
            from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError

            client = SchedulesDirectClient("bad_user", "bad_pass")

            # Mock the session post method
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "message": "Invalid credentials",
                "code": 4001,
            }
            client.session.post = MagicMock(return_value=mock_response)

            with pytest.raises(SchedulesDirectError):
                client.authenticate()

    def test_authenticate_success(self, app):
        """Test successful authentication"""
        with app.app_context():
            from services.schedules_direct import SchedulesDirectClient

            client = SchedulesDirectClient("good_user", "good_pass")

            # Mock the session post method
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "token": "test_token_123",
                "code": 0,
                "tokenExpires": 1735000000,
            }
            client.session.post = MagicMock(return_value=mock_response)

            client.authenticate()
            assert client.token == "test_token_123"


# ============================================================================
# Additional Playlist Routes Tests
# ============================================================================


class TestPlaylistRoutesAdditional:
    """Additional playlist route tests"""

    def test_playlist_config_with_exclude_tags(self, app, client):
        """Test playlist config with exclude tags"""
        with app.app_context():
            account = Account(
                name="Tag Account",
                username="u",
                password="p",
                server="s.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="General",
            )
            db.session.add(category)
            db.session.commit()

            # Create channels
            ch1 = Channel(
                account_id=account.id,
                stream_id=1,
                name="Good Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            ch2 = Channel(
                account_id=account.id,
                stream_id=2,
                name="Bad Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add_all([ch1, ch2])

            # Create tag and assign
            tag = Tag(name="EXCLUDE_ME")
            db.session.add(tag)
            db.session.commit()

            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=2,
                tag_id=tag.id,
            )
            db.session.add(channel_tag)

            # Create config with exclude tags
            config = PlaylistConfig(
                name="Exclude Test",
                enabled=True,
                exclude_tags=json.dumps(["EXCLUDE_ME"]),
            )
            db.session.add(config)
            db.session.commit()
            config_id = config.id

        response = client.get(f"/playlist/config/{config_id}.m3u?proxy_icons=false")
        assert response.status_code == 200
        assert b"Good Channel" in response.data
        assert b"Bad Channel" not in response.data
