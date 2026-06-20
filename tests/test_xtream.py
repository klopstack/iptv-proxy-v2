"""
Tests for Xtream Codes API emulation routes (routes/xtream.py)

Covers:
- Authentication mechanisms
- Player API endpoints (user info, categories, streams)
- Direct stream URL handling
- Credential CRUD operations
- Channel filtering and collapsing
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from models import (
    Account,
    Category,
    Channel,
    ChannelTag,
    Event,
    EventChannelLink,
    FccFacility,
    PlaylistConfig,
    Tag,
    XtreamCredential,
    db,
)
from services.category_tag_service import XTREAM_LOCAL_CHANNELS_PARENT_ID

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def test_channels(app, test_account, test_category):
    """Create test channels"""
    with app.app_context():
        channels = []
        for i in range(3):
            channel = Channel(
                account_id=test_account,
                stream_id=str(1000 + i),
                name=f"Channel {i + 1}",
                cleaned_name=f"Channel {i + 1}",
                category_id=test_category,
                stream_icon=f"http://example.com/icon{i + 1}.png",
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            channels.append(channel)
        db.session.commit()
        # Get IDs before yielding
        for channel in channels:
            db.session.refresh(channel)
        yield channels


@pytest.fixture
def xtream_credential(app, test_account):
    """Create an Xtream credential linked to account"""
    with app.app_context():
        cred = XtreamCredential(
            username="xtream_user",
            password="xtream_pass",
            account_id=test_account,
            enabled=True,
            use_filters=False,
            collapse_duplicates=False,
        )
        db.session.add(cred)
        db.session.commit()
        db.session.refresh(cred)
        yield cred


@pytest.fixture
def playlist_config(app, test_account):
    """Create a playlist config"""
    with app.app_context():
        config = PlaylistConfig(
            name="Test Playlist",
            include_accounts=json.dumps([test_account]),
            exclude_accounts=json.dumps([]),
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([]),
            tag_match_mode="any",
            enabled=True,
        )
        db.session.add(config)
        db.session.commit()
        db.session.refresh(config)
        yield config


@pytest.fixture
def xtream_credential_playlist(app, playlist_config):
    """Create an Xtream credential linked to playlist config"""
    with app.app_context():
        cred = XtreamCredential(
            username="playlist_user",
            password="playlist_pass",
            playlist_config_id=playlist_config.id,
            enabled=True,
            use_filters=False,
            collapse_duplicates=False,
        )
        db.session.add(cred)
        db.session.commit()
        db.session.refresh(cred)
        yield cred


# ============================================================================
# Authentication Tests
# ============================================================================


class TestXtreamAuthentication:
    """Test Xtream authentication"""

    def test_authenticate_valid_account_credentials(self, app, client, xtream_credential, test_channels):
        """Test authentication with valid account credentials"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "xtream_user", "password": "xtream_pass"},
            )
            assert response.status_code == 200
            data = response.json
            assert data["user_info"]["auth"] == 1
            assert data["user_info"]["username"] == "xtream_user"

    def test_authenticate_invalid_credentials(self, app, client):
        """Test authentication with invalid credentials"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "invalid", "password": "invalid"},
            )
            assert response.status_code == 401
            assert response.json["user_info"]["auth"] == 0

    def test_authenticate_missing_credentials(self, app, client):
        """Test authentication with missing credentials"""
        with app.app_context():
            response = client.get("/player_api.php")
            assert response.status_code == 401

    def test_authenticate_disabled_credential(self, app, client, xtream_credential):
        """Test authentication with disabled credential"""
        with app.app_context():
            # Fetch and update within same session
            cred = db.session.get(XtreamCredential, xtream_credential.id)
            cred.enabled = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={"username": "xtream_user", "password": "xtream_pass"},
        )
        assert response.status_code == 401

    def test_authenticate_disabled_account(self, app, client, xtream_credential, test_account):
        """Test authentication with disabled account"""
        with app.app_context():
            # Fetch and update within same session
            acc = db.session.get(Account, test_account)
            acc.enabled = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={"username": "xtream_user", "password": "xtream_pass"},
        )
        assert response.status_code == 401

    def test_authenticate_playlist_config(self, app, client, xtream_credential_playlist, test_channels):
        """Test authentication with playlist config credential"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "playlist_user", "password": "playlist_pass"},
            )
            assert response.status_code == 200
            data = response.json
            assert data["user_info"]["auth"] == 1

    def test_authenticate_disabled_playlist_config(self, app, client, xtream_credential_playlist, playlist_config):
        """Test authentication with disabled playlist config"""
        with app.app_context():
            # Fetch and update within same session
            config = db.session.get(PlaylistConfig, playlist_config.id)
            config.enabled = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={"username": "playlist_user", "password": "playlist_pass"},
        )
        assert response.status_code == 401


# ============================================================================
# Player API Tests
# ============================================================================


class TestXtreamPlayerAPI:
    """Test Xtream player API endpoints"""

    def test_get_user_info(self, app, client, xtream_credential):
        """Test get_user_info endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={"username": "xtream_user", "password": "xtream_pass"},
            )
            assert response.status_code == 200
            data = response.json
            assert "user_info" in data
            assert "server_info" in data
            assert data["user_info"]["username"] == "xtream_user"
            assert data["user_info"]["auth"] == 1

    def test_get_account_info_action(self, app, client, xtream_credential):
        """Some clients use action=get_account_info instead of omitting action."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_account_info",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert "user_info" in data
            assert "server_info" in data
            assert data["user_info"]["username"] == "xtream_user"
            assert data["user_info"]["auth"] == 1

    def test_get_live_categories(self, app, client, xtream_credential, test_channels):
        """Test get_live_categories endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_categories",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["category_name"] == "Test Category"

    def test_get_live_streams(self, app, client, xtream_credential, test_channels):
        """Test get_live_streams endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_streams",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 3
            assert data[0]["name"] == "Channel 1"
            assert data[0]["stream_type"] == "live"

    def test_get_live_categories_fcc_city_without_dma(
        self, app, client, xtream_credential, test_channels, test_account
    ):
        """FCC-matched channels without a DMA nest under Local Channels by city name."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.category_tag_grouping = json.dumps(
                {"enabled": True, "prefixes": ["DMA:"], "display": "strip_prefix_title"}
            )
            facility = FccFacility(
                facility_id=88001,
                callsign="KAKM",
                community_city="JUNEAU",
                community_state="AK",
                nielsen_dma=None,
            )
            db.session.add(facility)
            db.session.flush()
            ch = db.session.get(Channel, test_channels[0].id)
            ch.fcc_facility_id = facility.id
            network_tag = Tag(name="NETWORK:AK")
            db.session.add(network_tag)
            db.session.flush()
            db.session.add(
                ChannelTag(
                    account_id=test_account,
                    stream_id=ch.stream_id,
                    tag_id=network_tag.id,
                    source=ChannelTag.SOURCE_ENRICHMENT,
                )
            )
            db.session.commit()

            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_categories",
                },
            )
            assert response.status_code == 200
            data = response.json
            juneau = next(item for item in data if item["category_name"] == "Juneau")
            assert juneau["parent_id"] == int(XTREAM_LOCAL_CHANNELS_PARENT_ID)

            streams_response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_streams",
                    "category_id": juneau["category_id"],
                },
            )
            assert len(streams_response.json) == 1
            assert streams_response.json[0]["stream_id"] == int(test_channels[0].stream_id)

    def test_get_live_categories_dma_tag_grouping(self, app, client, xtream_credential, test_channels, test_account):
        """Tag-based DMA grouping emits virtual Xtream categories."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.category_tag_grouping = json.dumps(
                {"enabled": True, "prefixes": ["DMA:"], "display": "strip_prefix_title"}
            )
            dma_tag = Tag(name="DMA:CHICAGO")
            db.session.add(dma_tag)
            db.session.flush()
            db.session.add(
                ChannelTag(
                    account_id=test_account,
                    stream_id=test_channels[0].stream_id,
                    tag_id=dma_tag.id,
                )
            )
            db.session.commit()

            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_categories",
                },
            )
            assert response.status_code == 200
            data = response.json
            names = {item["category_name"] for item in data}
            assert "Chicago" in names
            assert "Local Channels" in names
            assert "Test Category" in names

            parent = next(item for item in data if item["category_name"] == "Local Channels")
            assert parent["parent_id"] == 0

            tag_cat = next(item for item in data if item["category_name"] == "Chicago")
            assert tag_cat["parent_id"] == int(parent["category_id"])
            streams_response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_streams",
                    "category_id": tag_cat["category_id"],
                },
            )
            streams = streams_response.json
            assert len(streams) == 1
            assert streams[0]["category_id"] == tag_cat["category_id"]

    def test_get_live_streams_by_category(self, app, client, xtream_credential, test_channels, test_category):
        """Test get_live_streams filtered by category"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_live_streams",
                    "category_id": str(test_category),
                },
            )
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 3

    def test_get_live_categories_groups_ppv_into_live_and_replay(self, app, client, xtream_credential, test_account):
        """Grouped PPV mode hides PPV categories and exposes Live/Replay virtual categories."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"

            sports = Category(account_id=test_account, category_id="sports", category_name="Sports")
            ppv = Category(account_id=test_account, category_id="ppv", category_name="PPV Events")
            db.session.add_all([sports, ppv])
            db.session.flush()

            sports_channel = Channel(
                account_id=test_account,
                stream_id="1100",
                name="Sports Channel",
                cleaned_name="Sports Channel",
                category_id=sports.id,
                is_active=True,
                is_visible=True,
            )
            live_channel = Channel(
                account_id=test_account,
                stream_id="1101",
                name="Live Event",
                cleaned_name="Live Event",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            replay_channel = Channel(
                account_id=test_account,
                stream_id="1102",
                name="Replay Event",
                cleaned_name="Replay Event",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            hidden_future_channel = Channel(
                account_id=test_account,
                stream_id="1103",
                name="Future Event",
                cleaned_name="Future Event",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add_all([sports_channel, live_channel, replay_channel, hidden_future_channel])
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            events = [
                Event(
                    external_id="live-event",
                    scheduled_at=now + timedelta(hours=3),
                    home_team_id="home-live",
                    home_team_name="Home Live",
                    away_team_id="away-live",
                    away_team_name="Away Live",
                    status=Event.STATUS_SCHEDULED,
                ),
                Event(
                    external_id="replay-event",
                    scheduled_at=now - timedelta(hours=2),
                    home_team_id="home-replay",
                    home_team_name="Home Replay",
                    away_team_id="away-replay",
                    away_team_name="Away Replay",
                    status=Event.STATUS_FINISHED,
                ),
                Event(
                    external_id="future-event",
                    scheduled_at=now + timedelta(hours=30),
                    home_team_id="home-future",
                    home_team_name="Home Future",
                    away_team_id="away-future",
                    away_team_name="Away Future",
                    status=Event.STATUS_SCHEDULED,
                ),
            ]
            db.session.add_all(events)
            db.session.flush()
            db.session.add_all(
                [
                    EventChannelLink(event_id=events[0].id, channel_id=live_channel.id),
                    EventChannelLink(event_id=events[1].id, channel_id=replay_channel.id),
                    EventChannelLink(event_id=events[2].id, channel_id=hidden_future_channel.id),
                ]
            )
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_categories",
            },
        )
        assert response.status_code == 200
        data = response.json
        category_names = {item["category_name"] for item in data}
        assert category_names == {"Sports", "PPV Events", "PPV - Live", "PPV - Replay"}

        parent = next(item for item in data if item["category_name"] == "PPV Events")
        assert parent["category_id"] == "-1"
        assert parent["parent_id"] == 0

        live_cat = next(item for item in data if item["category_name"] == "PPV - Live")
        replay_cat = next(item for item in data if item["category_name"] == "PPV - Replay")
        assert live_cat["parent_id"] == int(parent["category_id"])
        assert replay_cat["parent_id"] == int(parent["category_id"])

    def test_get_live_streams_by_grouped_ppv_category(self, app, client, xtream_credential, test_account):
        """Grouped PPV virtual categories return correctly sorted streams."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"

            ppv = Category(account_id=test_account, category_id="ppv", category_name="PPV Events")
            db.session.add(ppv)
            db.session.flush()

            live_soon = Channel(
                account_id=test_account,
                stream_id="1201",
                name="Soon",
                cleaned_name="Soon",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            live_later = Channel(
                account_id=test_account,
                stream_id="1202",
                name="Later",
                cleaned_name="Later",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            replay_recent = Channel(
                account_id=test_account,
                stream_id="1203",
                name="Replay Recent",
                cleaned_name="Replay Recent",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            replay_old = Channel(
                account_id=test_account,
                stream_id="1204",
                name="Replay Old",
                cleaned_name="Replay Old",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add_all([live_soon, live_later, replay_recent, replay_old])
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            events = [
                Event(
                    external_id="soon-event",
                    scheduled_at=now + timedelta(hours=1),
                    home_team_id="a1",
                    home_team_name="A1",
                    away_team_id="b1",
                    away_team_name="B1",
                    status=Event.STATUS_SCHEDULED,
                ),
                Event(
                    external_id="later-event",
                    scheduled_at=now + timedelta(hours=6),
                    home_team_id="a2",
                    home_team_name="A2",
                    away_team_id="b2",
                    away_team_name="B2",
                    status=Event.STATUS_SCHEDULED,
                ),
                Event(
                    external_id="recent-replay",
                    scheduled_at=now - timedelta(hours=1),
                    home_team_id="a3",
                    home_team_name="A3",
                    away_team_id="b3",
                    away_team_name="B3",
                    status=Event.STATUS_FINISHED,
                ),
                Event(
                    external_id="old-replay",
                    scheduled_at=now - timedelta(hours=5),
                    home_team_id="a4",
                    home_team_name="A4",
                    away_team_id="b4",
                    away_team_name="B4",
                    status=Event.STATUS_FINISHED,
                ),
            ]
            db.session.add_all(events)
            db.session.flush()
            db.session.add_all(
                [
                    EventChannelLink(event_id=events[0].id, channel_id=live_soon.id),
                    EventChannelLink(event_id=events[1].id, channel_id=live_later.id),
                    EventChannelLink(event_id=events[2].id, channel_id=replay_recent.id),
                    EventChannelLink(event_id=events[3].id, channel_id=replay_old.id),
                ]
            )
            db.session.commit()

        live_response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
                "category_id": "-10",
            },
        )
        assert live_response.status_code == 200
        assert [item["stream_id"] for item in live_response.json] == [1201, 1202]
        assert all(item["category_id"] == "-10" for item in live_response.json)

        replay_response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
                "category_id": "-11",
            },
        )
        assert replay_response.status_code == 200
        assert [item["stream_id"] for item in replay_response.json] == [1203, 1204]
        assert all(item["category_id"] == "-11" for item in replay_response.json)

    def test_get_live_streams_unfiltered_preserves_ppv_live_order(self, app, client, xtream_credential, test_account):
        """Unfiltered get_live_streams keeps PPV Live in soonest-first order for client-side filtering."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"

            ppv = Category(account_id=test_account, category_id="ppv", category_name="PPV Events")
            regular = Category(account_id=test_account, category_id="sports", category_name="Sports")
            db.session.add_all([ppv, regular])
            db.session.flush()

            regular_channel = Channel(
                account_id=test_account,
                stream_id="1100",
                name="Regular Sports",
                cleaned_name="Regular Sports",
                category_id=regular.id,
                is_active=True,
                is_visible=True,
                is_ppv=False,
            )
            live_soon = Channel(
                account_id=test_account,
                stream_id="1201",
                name="Z PPV Soon",
                cleaned_name="Z PPV Soon",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            live_later = Channel(
                account_id=test_account,
                stream_id="1202",
                name="A PPV Later",
                cleaned_name="A PPV Later",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add_all([regular_channel, live_later, live_soon])
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            events = [
                Event(
                    external_id="soon-event",
                    scheduled_at=now + timedelta(hours=1),
                    home_team_id="a1",
                    home_team_name="A1",
                    away_team_id="b1",
                    away_team_name="B1",
                    status=Event.STATUS_SCHEDULED,
                ),
                Event(
                    external_id="later-event",
                    scheduled_at=now + timedelta(hours=6),
                    home_team_id="a2",
                    home_team_name="A2",
                    away_team_id="b2",
                    away_team_name="B2",
                    status=Event.STATUS_SCHEDULED,
                ),
            ]
            db.session.add_all(events)
            db.session.flush()
            db.session.add_all(
                [
                    EventChannelLink(event_id=events[0].id, channel_id=live_soon.id),
                    EventChannelLink(event_id=events[1].id, channel_id=live_later.id),
                ]
            )
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
            },
        )
        assert response.status_code == 200
        live_streams = [item for item in response.json if item["category_id"] == "-10"]
        assert [item["stream_id"] for item in live_streams] == [1201, 1202]

    def test_get_live_categories_includes_historical_bucket(self, app, client, xtream_credential, test_account):
        """Grouped PPV mode exposes PPV - Historical virtual category for old events."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"

            ppv = Category(account_id=test_account, category_id="ppv-hist", category_name="PPV Events")
            db.session.add(ppv)
            db.session.flush()

            historical_channel = Channel(
                account_id=test_account,
                stream_id="1301",
                name="Old Archive",
                cleaned_name="Old Archive",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add(historical_channel)
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            historical_event = Event(
                external_id="xtream-historical",
                scheduled_at=now - timedelta(days=30),
                home_team_id="h",
                home_team_name="Home",
                away_team_id="a",
                away_team_name="Away",
                status=Event.STATUS_FINISHED,
            )
            db.session.add(historical_event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=historical_event.id, channel_id=historical_channel.id))
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_categories",
            },
        )
        assert response.status_code == 200
        data = response.json
        category_names = {item["category_name"] for item in data}
        assert category_names == {"PPV Events", "PPV - Historical"}

        parent = next(item for item in data if item["category_name"] == "PPV Events")
        assert parent["parent_id"] == 0
        historical_cat = next(item for item in data if item["category_name"] == "PPV - Historical")
        assert historical_cat["parent_id"] == int(parent["category_id"])

        streams_response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
                "category_id": "-12",
            },
        )
        assert streams_response.status_code == 200
        assert len(streams_response.json) == 1
        assert streams_response.json[0]["category_id"] == "-12"

    def test_get_live_streams_by_unmatched_live_category(self, app, client, xtream_credential, test_account):
        """Grouped PPV mode exposes no_match channels in PPV - Unmatched Live (-13)."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"

            ppv = Category(account_id=test_account, category_id="ppv-unmatched", category_name="PPV Events")
            db.session.add(ppv)
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start_str = (now + timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S")
            unmatched_channel = Channel(
                account_id=test_account,
                stream_id="1501",
                name=f"DAZN 01 | Arsenal vs Brighton ({start_str})",
                cleaned_name=f"DAZN 01 | Arsenal vs Brighton ({start_str})",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
                ppv_enrichment_status="no_match",
            )
            db.session.add(unmatched_channel)
            db.session.commit()

        categories_response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_categories",
            },
        )
        assert categories_response.status_code == 200
        category_names = {item["category_name"] for item in categories_response.json}
        assert "PPV - Unmatched Live" in category_names

        unmatched_cat = next(
            item for item in categories_response.json if item["category_name"] == "PPV - Unmatched Live"
        )
        assert unmatched_cat["category_id"] == "-13"

        streams_response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
                "category_id": "-13",
            },
        )
        assert streams_response.status_code == 200
        assert len(streams_response.json) == 1
        assert streams_response.json[0]["category_id"] == "-13"
        assert streams_response.json[0]["stream_id"] == 1501

    def test_get_live_streams_by_ppv_events_parent_in_grouped_mode(self, app, client, xtream_credential, test_account):
        """Grouped PPV mode: category_id=-1 returns union of all grouped buckets."""
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"

            ppv = Category(account_id=test_account, category_id="ppv", category_name="PPV Events")
            db.session.add(ppv)
            db.session.flush()

            live_channel = Channel(
                account_id=test_account,
                stream_id="1401",
                name="Live",
                cleaned_name="Live",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            replay_channel = Channel(
                account_id=test_account,
                stream_id="1402",
                name="Replay",
                cleaned_name="Replay",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add_all([live_channel, replay_channel])
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            events = [
                Event(
                    external_id="parent-live",
                    scheduled_at=now + timedelta(hours=2),
                    home_team_id="h1",
                    home_team_name="H1",
                    away_team_id="a1",
                    away_team_name="A1",
                    status=Event.STATUS_SCHEDULED,
                ),
                Event(
                    external_id="parent-replay",
                    scheduled_at=now - timedelta(hours=2),
                    home_team_id="h2",
                    home_team_name="H2",
                    away_team_id="a2",
                    away_team_name="A2",
                    status=Event.STATUS_FINISHED,
                ),
            ]
            db.session.add_all(events)
            db.session.flush()
            db.session.add_all(
                [
                    EventChannelLink(event_id=events[0].id, channel_id=live_channel.id),
                    EventChannelLink(event_id=events[1].id, channel_id=replay_channel.id),
                ]
            )
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
                "category_id": "-1",
            },
        )
        assert response.status_code == 200
        stream_ids = {item["stream_id"] for item in response.json}
        assert stream_ids == {1401, 1402}
        category_ids = {item["category_id"] for item in response.json}
        assert category_ids == {"-10", "-11"}

    def test_historical_toggle_hides_xtream_category(self, app, client, xtream_credential, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.ppv_visibility = "group_live_replay"
            account.ppv_show_historical = False

            ppv = Category(account_id=test_account, category_id="ppv-hide", category_name="PPV Events")
            db.session.add(ppv)
            db.session.flush()

            historical_channel = Channel(
                account_id=test_account,
                stream_id="1302",
                name="Hidden Archive",
                cleaned_name="Hidden Archive",
                category_id=ppv.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add(historical_channel)
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            historical_event = Event(
                external_id="xtream-hidden-historical",
                scheduled_at=now - timedelta(days=30),
                home_team_id="h2",
                home_team_name="Home 2",
                away_team_id="a2",
                away_team_name="Away 2",
                status=Event.STATUS_FINISHED,
            )
            db.session.add(historical_event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=historical_event.id, channel_id=historical_channel.id))
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_categories",
            },
        )
        category_names = {item["category_name"] for item in response.json}
        assert "PPV - Historical" not in category_names

    def test_get_vod_categories(self, app, client, xtream_credential):
        """VOD passthrough disabled by default; return empty list for client compatibility."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_vod_categories",
                },
            )
            assert response.status_code == 200
            assert response.json == []

    def test_get_vod_categories_passthrough(self, app, client, xtream_credential, test_account, monkeypatch):
        """When vod_passthrough is enabled, return upstream categories unchanged."""
        with app.app_context():
            cred = db.session.get(XtreamCredential, xtream_credential.id)
            cred.vod_passthrough = True
            db.session.commit()

            monkeypatch.setattr(
                "routes.xtream.fetch_vod_categories",
                lambda account: [{"category_id": "10", "category_name": "Action Movies"}],
            )

            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_vod_categories",
                },
            )
            assert response.status_code == 200
            assert response.json == [{"category_id": "10", "category_name": "Action Movies"}]

    def test_get_vod_streams(self, app, client, xtream_credential):
        """VOD passthrough disabled by default; return empty list for client compatibility."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_vod_streams",
                },
            )
            assert response.status_code == 200
            assert response.json == []

    def test_get_vod_streams_passthrough(self, app, client, xtream_credential, monkeypatch):
        """When vod_passthrough is enabled, return upstream movie titles unchanged."""
        with app.app_context():
            cred = db.session.get(XtreamCredential, xtream_credential.id)
            cred.vod_passthrough = True
            db.session.commit()

            upstream_streams = [
                {"stream_id": 201, "name": "US| Die Hard (1988)", "category_id": "10"},
            ]

            def fake_fetch(account, *, category_id=None):
                assert category_id == "10"
                return upstream_streams

            monkeypatch.setattr("routes.xtream.fetch_vod_streams", fake_fetch)
            monkeypatch.setattr(
                "routes.xtream.rewrite_vod_stream_icons",
                lambda streams, proxy_base: streams,
            )

            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_vod_streams",
                    "category_id": "10",
                },
            )
            assert response.status_code == 200
            assert response.json[0]["name"] == "US| Die Hard (1988)"

    def test_get_series_categories(self, app, client, xtream_credential):
        """Series is not supported; return empty list for client compatibility."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_series_categories",
                },
            )
            assert response.status_code == 200
            assert response.json == []

    def test_get_series(self, app, client, xtream_credential):
        """Series is not supported; return empty list for client compatibility."""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_series",
                },
            )
            assert response.status_code == 200
            assert response.json == []

    def test_unknown_action(self, app, client, xtream_credential):
        """Test unknown action"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "unknown_action",
                },
            )
            assert response.status_code == 400
            assert "error" in response.json

    def test_get_short_epg(self, app, client, xtream_credential):
        """Test get_short_epg endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_short_epg",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert "epg_listings" in data

    def test_get_simple_data_table(self, app, client, xtream_credential, test_channels):
        """Test get_simple_data_table endpoint"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_simple_data_table",
                    "stream_id": "1000",
                },
            )
            assert response.status_code == 200
            data = response.json
            assert data["stream_id"] == 1000
            assert data["name"] == "Channel 1"

    def test_get_simple_data_table_missing_stream(self, app, client, xtream_credential):
        """Test get_simple_data_table with missing stream_id"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_simple_data_table",
                },
            )
            assert response.status_code == 400
            assert "error" in response.json

    def test_get_simple_data_table_not_found(self, app, client, xtream_credential):
        """Test get_simple_data_table with non-existent stream"""
        with app.app_context():
            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "xtream_user",
                    "password": "xtream_pass",
                    "action": "get_simple_data_table",
                    "stream_id": "99999",
                },
            )
            assert response.status_code == 404


# ============================================================================
# Stream URL Tests
# ============================================================================


class TestXtreamStreamURLs:
    """Test Xtream stream URLs"""

    def test_live_stream_valid(self, app, client, xtream_credential, test_channels):
        """Test valid live stream URL - stream_id type conversion"""
        with app.app_context():
            # Stream ID in URL is parsed as integer (1000) but must be compared
            # to string stream IDs in database ("1000"). The route should handle conversion.
            response = client.get("/live/xtream_user/xtream_pass/1000.ts")
            # Should redirect to internal stream proxy when found
            assert response.status_code == 302

    def test_live_stream_uses_fast_path_not_full_channel_list(self, app, client, xtream_credential, test_channels):
        """Tune-in should verify one stream without loading the full channel list."""
        with app.app_context():
            with patch("routes.xtream.get_channels_for_credential") as mock_all_channels:
                response = client.get("/live/xtream_user/xtream_pass/1000.ts")

            assert response.status_code == 302
            mock_all_channels.assert_not_called()

    def test_live_stream_type_mismatch_fix(self, app, client, xtream_credential, test_channels):
        """Test that stream_id integer from route matches string in database"""
        with app.app_context():
            # Create a channel with specific stream_id
            channel = db.session.query(Channel).filter_by(stream_id="1000").first()
            assert channel is not None, "Test channel with stream_id='1000' should exist"
            assert isinstance(channel.stream_id, str), "Channel stream_id should be stored as string"

            # Request using integer in URL
            response = client.get("/live/xtream_user/xtream_pass/1000.ts")
            assert response.status_code == 302, "Integer stream_id from URL should match string in database"

            # Verify the redirect location contains the correct stream_id
            location = response.headers.get("Location")
            assert location is not None
            assert "1000" in location

    def test_live_stream_invalid_credentials(self, app, client):
        """Test live stream with invalid credentials"""
        with app.app_context():
            response = client.get("/live/invalid/invalid/1000.ts")
            assert response.status_code == 401

    def test_live_stream_not_found(self, app, client, xtream_credential):
        """Test live stream with non-existent stream ID"""
        with app.app_context():
            response = client.get("/live/xtream_user/xtream_pass/99999.ts")
            assert response.status_code == 404

    def test_live_stream_without_extension(self, app, client, xtream_credential, test_channels):
        """Test live stream URL without extension"""
        with app.app_context():
            response = client.get("/live/xtream_user/xtream_pass/1000")
            # Should redirect same as with extension
            assert response.status_code == 302

    def test_movie_stream(self, app, client, xtream_credential):
        """Movie stream URL returns 404 when VOD passthrough is disabled."""
        with app.app_context():
            response = client.get("/movie/xtream_user/xtream_pass/1000.mp4")
            assert response.status_code == 404
            assert "VOD not available" in response.json["error"]

    def test_movie_stream_passthrough(self, app, client, xtream_credential, test_account):
        """Movie stream URL redirects to internal VOD proxy when passthrough is enabled."""
        with app.app_context():
            cred = db.session.get(XtreamCredential, xtream_credential.id)
            cred.vod_passthrough = True
            db.session.commit()

            response = client.get("/movie/xtream_user/xtream_pass/1000.mp4")
            assert response.status_code == 302
            assert f"/stream/{test_account}/vod/1000.mp4?xc={xtream_credential.id}" in response.location

    def test_series_stream(self, app, client, xtream_credential):
        """Test series stream URL (not implemented)"""
        with app.app_context():
            response = client.get("/series/xtream_user/xtream_pass/1000.mp4")
            assert response.status_code == 404
            assert "Series not available" in response.json["error"]

    def test_xmltv_epg_account(self, app, client, xtream_credential, test_account):
        """Test XMLTV EPG endpoint with account"""
        with app.app_context():
            response = client.get("/xmltv.php", query_string={"username": "xtream_user", "password": "xtream_pass"})
            assert response.status_code == 302
            assert f"/epg/{test_account}.xml" in response.location

    def test_xmltv_epg_playlist_config(self, app, client, xtream_credential_playlist, playlist_config):
        """Test XMLTV EPG endpoint with playlist config"""
        with app.app_context():
            response = client.get("/xmltv.php", query_string={"username": "playlist_user", "password": "playlist_pass"})
            assert response.status_code == 302
            assert f"/epg/config/{playlist_config.slug}.xml" in response.location

    def test_xmltv_epg_invalid_credentials(self, app, client):
        """Test XMLTV EPG with invalid credentials"""
        with app.app_context():
            response = client.get("/xmltv.php", query_string={"username": "invalid", "password": "invalid"})
            assert response.status_code == 401


# ============================================================================
# Credential Management Tests
# ============================================================================


class TestXtreamCredentialManagement:
    """Test Xtream credential CRUD operations"""

    def test_list_credentials(self, app, client, xtream_credential):
        """Test listing credentials"""
        with app.app_context():
            response = client.get("/api/xtream-credentials")
            assert response.status_code == 200
            data = response.json
            assert isinstance(data, list)
            assert len(data) == 1
            assert data[0]["username"] == "xtream_user"
            assert data[0]["created_at"].endswith("Z")

    def test_create_credential_account(self, app, client, test_account):
        """Test creating credential for account"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={
                    "username": "new_user",
                    "password": "new_pass",
                    "account_id": test_account,
                    "use_filters": True,
                    "collapse_duplicates": False,
                },
            )
            assert response.status_code == 201
            data = response.json
            assert data["username"] == "new_user"
            assert data["account_id"] == test_account

    def test_create_credential_playlist_config(self, app, client, playlist_config):
        """Test creating credential for playlist config"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={
                    "username": "config_user",
                    "password": "config_pass",
                    "playlist_config_id": playlist_config.id,
                },
            )
            assert response.status_code == 201
            data = response.json
            assert data["playlist_config_id"] == playlist_config.id

    def test_create_credential_missing_username(self, app, client, test_account):
        """Test creating credential without username"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={"password": "pass", "account_id": test_account},
            )
            assert response.status_code == 400

    def test_create_credential_missing_target(self, app, client):
        """Test creating credential without account or playlist config"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={"username": "user", "password": "pass"},
            )
            assert response.status_code == 400

    def test_create_credential_duplicate_username(self, app, client, xtream_credential, test_account):
        """Test creating credential with duplicate username"""
        with app.app_context():
            response = client.post(
                "/api/xtream-credentials",
                json={
                    "username": "xtream_user",
                    "password": "different_pass",
                    "account_id": test_account,
                },
            )
            assert response.status_code == 409

    def test_update_credential(self, app, client, xtream_credential):
        """Test updating credential"""
        with app.app_context():
            response = client.put(
                f"/api/xtream-credentials/{xtream_credential.id}",
                json={"password": "new_password", "use_filters": True},
            )
            assert response.status_code == 200
            data = response.json
            assert data["username"] == "xtream_user"

            # Verify update
            updated = db.session.get(XtreamCredential, xtream_credential.id)
            assert updated.password == "new_password"
            assert updated.use_filters is True

    def test_update_credential_not_found(self, app, client):
        """Test updating non-existent credential"""
        with app.app_context():
            response = client.put("/api/xtream-credentials/99999", json={"password": "new_pass"})
            assert response.status_code == 404

    def test_delete_credential(self, app, client, xtream_credential):
        """Test deleting credential"""
        with app.app_context():
            response = client.delete(f"/api/xtream-credentials/{xtream_credential.id}")
            assert response.status_code == 204

            # Verify deletion
            deleted = db.session.get(XtreamCredential, xtream_credential.id)
            assert deleted is None

    def test_delete_credential_not_found(self, app, client):
        """Test deleting non-existent credential"""
        with app.app_context():
            response = client.delete("/api/xtream-credentials/99999")
            assert response.status_code == 404


# ============================================================================
# Channel Filtering Tests
# ============================================================================


class TestXtreamChannelFiltering:
    """Test channel filtering functionality"""

    def test_channels_with_filters_enabled(self, app, client, test_account, test_channels):
        """Test that filters are applied when enabled"""
        with app.app_context():
            # Create credential with filters enabled
            cred = XtreamCredential(
                username="filter_user",
                password="filter_pass",
                account_id=test_account,
                enabled=True,
                use_filters=True,
            )
            db.session.add(cred)
            db.session.commit()

            with patch("services.filter_service.FilterService.apply_filters_to_channels") as mock_filter:
                mock_filter.return_value = test_channels[:2]  # Return only 2 channels

                response = client.get(
                    "/player_api.php",
                    query_string={
                        "username": "filter_user",
                        "password": "filter_pass",
                        "action": "get_live_streams",
                    },
                )
                assert response.status_code == 200
                data = response.json
                assert len(data) == 2
                mock_filter.assert_called_once()

    def test_channels_inactive_excluded(self, app, client, xtream_credential, test_channels):
        """Test that inactive channels are excluded"""
        with app.app_context():
            # Mark one channel as inactive and commit
            channel = Channel.query.filter_by(stream_id="1000").first()
            channel.is_active = False
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "xtream_user",
                "password": "xtream_pass",
                "action": "get_live_streams",
            },
        )
        assert response.status_code == 200
        data = response.json
        # Check that the inactive channel is not in the results
        stream_ids = [s["stream_id"] for s in data]
        assert 1000 not in stream_ids
        assert len(data) == 2  # Only 2 active channels

    def test_playlist_config_with_tag_filters(self, app, client, test_account, test_channels, playlist_config):
        """Test playlist config with tag filtering"""
        with app.app_context():
            # Create tags
            tag = Tag(name="HD")
            db.session.add(tag)
            db.session.flush()

            # Link tag to first channel
            channel_tag = ChannelTag(account_id=test_account, stream_id=test_channels[0].stream_id, tag_id=tag.id)
            db.session.add(channel_tag)
            db.session.commit()

            # Re-fetch playlist config from database to ensure it's attached to this session
            config = db.session.get(PlaylistConfig, playlist_config.id)
            # Update playlist config to include only HD tag
            config.include_tags = json.dumps([tag.id])
            db.session.commit()

            # Create credential for playlist config
            cred = XtreamCredential(
                username="tag_user",
                password="tag_pass",
                playlist_config_id=playlist_config.id,
                enabled=True,
            )
            db.session.add(cred)
            db.session.commit()

            response = client.get(
                "/player_api.php",
                query_string={
                    "username": "tag_user",
                    "password": "tag_pass",
                    "action": "get_live_streams",
                },
            )
            assert response.status_code == 200
            data = response.json
            # Should only include channel with HD tag
            assert len(data) == 1
            assert data[0]["stream_id"] == 1000

    def test_collapse_duplicates(self, app, client, test_account, test_category):
        """Test duplicate channel collapsing"""
        with app.app_context():
            # Create duplicate channels with different names but same base name
            for i, quality in enumerate(["SD", "HD", "4K"]):
                channel = Channel(
                    account_id=test_account,
                    stream_id=f"{2000 + i}",
                    name=f"Test Channel {quality}",
                    cleaned_name="Test Channel",
                    category_id=test_category,
                    is_active=True,
                    is_visible=True,
                )
                db.session.add(channel)
            db.session.commit()

            # Create credential with collapse enabled
            cred = XtreamCredential(
                username="collapse_user",
                password="collapse_pass",
                account_id=test_account,
                enabled=True,
                collapse_duplicates=True,
            )
            db.session.add(cred)
            db.session.commit()

        with patch("services.quality_service.QualityService.collapse_duplicates") as mock_collapse:
            # Mock returns only one channel (highest quality)
            with app.app_context():
                ch = Channel.query.filter_by(stream_id="2002").first()
                mock_collapse.return_value = [
                    {
                        "channel": ch,
                        "stream_id": "2002",
                        "cleaned_name": "Test Channel",
                        "tags": ["4K"],
                    }
                ]

                response = client.get(
                    "/player_api.php",
                    query_string={
                        "username": "collapse_user",
                        "password": "collapse_pass",
                        "action": "get_live_streams",
                    },
                )
                assert response.status_code == 200
                # Should have called collapse
                assert mock_collapse.called


# ============================================================================
# Helper Function Tests
# ============================================================================


class TestXtreamHelpers:
    """Test helper functions"""

    def test_get_proxy_base_url_default(self, app, client):
        """Test getting proxy base URL without custom hostname"""
        with app.app_context():
            from services.url_service import get_proxy_base_url

            with client:
                client.get("/")  # Establish request context
                base_url = get_proxy_base_url()
                assert base_url.startswith("http://")

    def test_get_proxy_base_url_custom(self, app, client):
        """Test getting proxy base URL with custom hostname"""
        with app.app_context():
            from models import Settings
            from services.url_service import get_proxy_base_url

            # Set custom proxy hostname
            Settings.set("proxy_hostname", "proxy.example.com")
            db.session.commit()

            with client:
                client.get("/")  # Establish request context
                base_url = get_proxy_base_url()
                assert base_url == "https://proxy.example.com"
