"""
Tests for PPV EPG Service

Tests the generation of XMLTV EPG data from Event records
with enriched TheSportsDB data.
"""
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

import pytest

from models import Channel, EpgChannel, EpgSource, Event, EventChannelLink, db
from services.ppv_epg_service import PPVEpgService


@pytest.fixture
def sample_events(app):
    """Create sample events for testing"""
    with app.app_context():
        # Create test account
        from models import Account

        account = Account(name="Test Account", server="http://test.com", username="test", password="test")
        db.session.add(account)
        db.session.flush()

        # Create test category
        from models import Category

        category = Category(account_id=account.id, category_id="ppv", category_name="PPV")
        db.session.add(category)
        db.session.flush()

        # Create events
        now = datetime.now(timezone.utc).replace(tzinfo=None)

        event1 = Event(
            external_id="12345",
            source=Event.SOURCE_THESPORTSDB,
            sport="Soccer",
            league_name="Premier League",
            home_team_id="133604",
            home_team_name="Arsenal",
            away_team_id="133609",
            away_team_name="Chelsea",
            scheduled_at=now + timedelta(hours=2),
            status=Event.STATUS_SCHEDULED,
            venue_name="Emirates Stadium",
            city="London",
            country="England",
            home_team_badge="http://example.com/arsenal.png",
            event_image="http://example.com/match.jpg",
            is_ppv=True,
        )

        event2 = Event(
            external_id="12346",
            source=Event.SOURCE_THESPORTSDB,
            sport="Basketball",
            league_name="NBA",
            home_team_id="133616",
            home_team_name="Lakers",
            away_team_id="133618",
            away_team_name="Warriors",
            scheduled_at=now + timedelta(days=1),
            end_at=now + timedelta(days=1, hours=3),
            status=Event.STATUS_SCHEDULED,
            venue_name="Crypto.com Arena",
            city="Los Angeles",
            country="USA",
            is_ppv=True,
        )

        db.session.add_all([event1, event2])
        db.session.flush()

        # Create channels
        channel1 = Channel(
            account_id=account.id,
            stream_id=1001,
            name="Arsenal vs Chelsea PPV",
            cleaned_name="Arsenal vs Chelsea",
            category_id=category.id,
            is_active=True,
            is_visible=True,
            stream_icon="http://example.com/icon1.png",
        )

        channel2 = Channel(
            account_id=account.id,
            stream_id=1002,
            name="Lakers vs Warriors PPV",
            cleaned_name="Lakers vs Warriors",
            category_id=category.id,
            is_active=True,
            is_visible=True,
        )

        # Inactive channel (should be excluded)
        channel3 = Channel(
            account_id=account.id,
            stream_id=1003,
            name="PPV Placeholder",
            category_id=category.id,
            is_active=False,
            is_visible=False,
        )

        db.session.add_all([channel1, channel2, channel3])
        db.session.flush()

        # Link events to channels
        link1 = EventChannelLink(
            event_id=event1.id,
            channel_id=channel1.id,
            match_confidence=0.95,
            match_method="direct_search",
            feed_type="primary",
        )

        link2 = EventChannelLink(
            event_id=event2.id,
            channel_id=channel2.id,
            match_confidence=1.0,
            match_method="calendar_browse",
            feed_type="hd",
        )

        db.session.add_all([link1, link2])
        db.session.commit()

        return {
            "account": account,
            "events": [event1, event2],
            "channels": [channel1, channel2, channel3],
            "links": [link1, link2],
        }


class TestPPVEpgService:
    """Test PPV EPG Service functionality"""

    def test_generate_ppv_epg_xmltv_basic(self, app, sample_events):
        """Test basic XMLTV generation from PPV events"""
        with app.app_context():
            epg_xml = PPVEpgService.generate_ppv_epg_xmltv()

            # Parse XML
            root = ET.fromstring(epg_xml)

            # Check root element
            assert root.tag == "tv"
            assert root.get("source-info-name") == "IPTV Proxy PPV EPG"
            assert root.get("generator-info-name") == "iptv-proxy-v2/ppv-epg-service"

            # Should have 2 channels (inactive excluded)
            channels = root.findall("channel")
            assert len(channels) == 2

            # Should have 2 programmes
            programmes = root.findall("programme")
            assert len(programmes) == 2

            # Check channel elements
            for channel in channels:
                assert channel.get("id").startswith("ppv-")
                display_names = channel.findall("display-name")
                assert len(display_names) >= 1

    def test_generate_ppv_epg_xmltv_with_account_filter(self, app, sample_events):
        """Test EPG generation filtered to specific account"""
        with app.app_context():
            # Re-query account to avoid DetachedInstanceError
            from models import Account

            account = Account.query.first()

            epg_xml = PPVEpgService.generate_ppv_epg_xmltv(account_id=account.id)
            root = ET.fromstring(epg_xml)

            # Should have channels from this account
            channels = root.findall("channel")
            assert len(channels) == 2

            # All channels should belong to this account
            for channel in channels:
                channel_id = channel.get("id")
                assert f"ppv-{account.id}-" in channel_id
        with app.app_context():
            epg_xml = PPVEpgService.generate_ppv_epg_xmltv()
            root = ET.fromstring(epg_xml)

            programmes = root.findall("programme")
            assert len(programmes) > 0

            for programme in programmes:
                # Check required attributes
                assert programme.get("start") is not None
                assert programme.get("stop") is not None
                assert programme.get("channel") is not None

                # Check time format (YYYYMMDDhhmmss +0000)
                start = programme.get("start")
                assert len(start) == 20
                assert start.endswith(" +0000")

                # Check required elements
                title = programme.find("title")
                assert title is not None
                assert title.text is not None
                assert " vs " in title.text

                desc = programme.find("desc")
                assert desc is not None
                assert desc.text is not None

                category = programme.find("category")
                assert category is not None

    def test_generate_ppv_epg_with_metadata(self, app, sample_events):
        """Test that EPG includes rich metadata from events"""
        with app.app_context():
            epg_xml = PPVEpgService.generate_ppv_epg_xmltv()
            root = ET.fromstring(epg_xml)

            # Find the Arsenal vs Chelsea programme
            arsenal_prog = None
            for prog in root.findall("programme"):
                title = prog.find("title")
                if title.text == "Arsenal vs Chelsea":
                    arsenal_prog = prog
                    break

            assert arsenal_prog is not None

            # Check sub-title (league)
            subtitle = arsenal_prog.find("sub-title")
            assert subtitle is not None
            assert subtitle.text == "Premier League"

            # Check description contains venue info
            desc = arsenal_prog.find("desc")
            assert "Emirates Stadium" in desc.text
            assert "London, England" in desc.text
            assert "Soccer" in desc.text

            # Check category
            category = arsenal_prog.find("category")
            assert category.text == "Soccer"

            # Check episode number (TheSportsDB ID)
            episode = arsenal_prog.find("episode-num")
            assert episode is not None
            assert episode.get("system") == "thesportsdb"
            assert episode.text == "12345"

            # Check date
            date = arsenal_prog.find("date")
            assert date is not None

            # Check star rating (confidence-based)
            rating = arsenal_prog.find("star-rating")
            assert rating is not None
            value = rating.find("value")
            assert "/5" in value.text

            # Check icon (event image)
            icon = arsenal_prog.find("icon")
            assert icon is not None
            assert icon.get("src") == "http://example.com/match.jpg"

            # Check credits (teams)
            credits = arsenal_prog.find("credits")
            assert credits is not None
            actors = credits.findall("actor")
            assert len(actors) == 2
            team_names = [actor.text for actor in actors]
            assert "Arsenal" in team_names
            assert "Chelsea" in team_names

    def test_generate_ppv_epg_event_duration(self, app, sample_events):
        """Test event duration handling"""
        with app.app_context():
            # Generate EPG with custom duration
            epg_xml = PPVEpgService.generate_ppv_epg_xmltv(event_duration_hours=2)
            root = ET.fromstring(epg_xml)

            programmes = root.findall("programme")

            for prog in programmes:
                start_str = prog.get("start")
                stop_str = prog.get("stop")

                # Parse times
                start_dt = datetime.strptime(start_str[:14], "%Y%m%d%H%M%S")
                stop_dt = datetime.strptime(stop_str[:14], "%Y%m%d%H%M%S")

                # Check duration is reasonable (2-4 hours depending on event)
                duration = (stop_dt - start_dt).total_seconds() / 3600
                assert duration >= 2
                assert duration <= 4

    def test_get_ppv_events_for_account(self, app, sample_events):
        """Test getting PPV events for specific account"""
        with app.app_context():
            # Re-query account to avoid DetachedInstanceError
            from models import Account

            account = Account.query.first()

            events = PPVEpgService.get_ppv_events_for_account(account.id)
            # Check event structure
            for event_data in events:
                assert "event_id" in event_data
                assert "sport" in event_data
                assert "home_team" in event_data
                assert "away_team" in event_data
                assert "scheduled_at" in event_data
                assert "channel_id" in event_data
                assert "match_confidence" in event_data

    def test_get_upcoming_ppv_events(self, app, sample_events):
        """Test getting upcoming PPV events"""
        with app.app_context():
            events = PPVEpgService.get_upcoming_ppv_events(days_ahead=7)

            # Should return both events (both scheduled in future)
            assert len(events) == 2

            # Check events are ordered by scheduled time
            assert events[0]["scheduled_at"] <= events[1]["scheduled_at"]

            # Check structure
            for event in events:
                assert "id" in event
                assert "external_id" in event
                assert "home_team" in event
                assert "away_team" in event
                assert "channel_count" in event

    def test_get_event_channels(self, app, sample_events):
        """Test getting channels for specific event"""
        with app.app_context():
            # Re-query event to avoid DetachedInstanceError
            event = Event.query.first()

            channels = PPVEpgService.get_event_channels(event.id)
            channel = channels[0]
            assert "channel_id" in channel
            assert "channel_name" in channel
            assert "match_confidence" in channel
            assert "match_method" in channel
            assert channel["match_method"] == "direct_search"

    def test_create_epg_source_for_ppv_events(self, app):
        """Test creating EPG source for PPV events"""
        with app.app_context():
            source_id = PPVEpgService.create_epg_source_for_ppv_events(name="Test PPV Source")

            # Check source was created
            source = db.session.get(EpgSource, source_id)
            assert source is not None
            assert source.name == "Test PPV Source"
            assert source.source_type == "ppv_events"
            assert source.enabled is True
            assert source.priority == 50

            # Should be idempotent
            source_id2 = PPVEpgService.create_epg_source_for_ppv_events(name="Test PPV Source")
            assert source_id2 == source_id

    def test_sync_ppv_events_to_epg_channels(self, app, sample_events):
        """Test syncing PPV events to EPG channels"""
        with app.app_context():
            # Create EPG source
            source_id = PPVEpgService.create_epg_source_for_ppv_events()

            # Sync events
            created, updated = PPVEpgService.sync_ppv_events_to_epg_channels(source_id)

            # Should create 2 EPG channels (one per event)
            assert created == 2
            assert updated == 0

            # Check EPG channels were created
            epg_channels = EpgChannel.query.filter_by(source_id=source_id).all()
            assert len(epg_channels) == 2

            for epg_ch in epg_channels:
                assert epg_ch.channel_id.startswith("ppv-event-")
                assert epg_ch.display_name is not None
                assert " vs " in epg_ch.display_name
                assert epg_ch.display_names_json is not None

                # Parse display names
                display_names = json.loads(epg_ch.display_names_json)
                assert len(display_names) >= 2

            # Running sync again should update existing
            created2, updated2 = PPVEpgService.sync_ppv_events_to_epg_channels(source_id)
            assert created2 == 0
            assert updated2 == 2

    def test_empty_ppv_events(self, app):
        """Test EPG generation when no PPV events exist"""
        with app.app_context():
            epg_xml = PPVEpgService.generate_ppv_epg_xmltv()

            root = ET.fromstring(epg_xml)

            # Should be valid but empty XML
            assert root.tag == "tv"
            channels = root.findall("channel")
            programmes = root.findall("programme")

            assert len(channels) == 0
            assert len(programmes) == 0

    def test_ppv_epg_channel_icons(self, app, sample_events):
        """Test that channel icons are properly included"""
        with app.app_context():
            epg_xml = PPVEpgService.generate_ppv_epg_xmltv()
            root = ET.fromstring(epg_xml)

            channels = root.findall("channel")

            # At least one channel should have an icon
            icons_found = False
            for channel in channels:
                icon = channel.find("icon")
                if icon is not None:
                    icons_found = True
                    assert icon.get("src") is not None
                    assert icon.get("src").startswith("http")

            assert icons_found

    def test_ppv_epg_status_display(self, app, sample_events):
        """Test that event status is properly displayed in description"""
        with app.app_context():
            # Update one event to be live
            event = Event.query.first()
            event.status = Event.STATUS_LIVE
            db.session.commit()

            epg_xml = PPVEpgService.generate_ppv_epg_xmltv()
            root = ET.fromstring(epg_xml)

            # Find the live event programme
            for prog in root.findall("programme"):
                title = prog.find("title")
                if "Arsenal" in title.text:
                    desc = prog.find("desc")
                    assert "Status: Live Now" in desc.text
                    break


class TestPPVEpgRoutes:
    """Test PPV EPG API routes"""

    def test_get_ppv_epg_xmltv_route(self, app, client, sample_events):
        """Test GET /api/ppv-epg/xmltv"""
        with app.app_context():
            response = client.get("/api/ppv-epg/xmltv")

            assert response.status_code == 200
            assert response.mimetype == "application/xml"

            # Parse XML
            root = ET.fromstring(response.data)
            assert root.tag == "tv"

    def test_get_ppv_epg_xmltv_with_account_filter(self, app, client, sample_events):
        """Test GET /api/ppv-epg/xmltv with account_id filter"""
        with app.app_context():
            # Re-query account to avoid DetachedInstanceError
            from models import Account

            account = Account.query.first()

            response = client.get(f"/api/ppv-epg/xmltv?account_id={account.id}")

            assert response.status_code == 200
            root = ET.fromstring(response.data)
            channels = root.findall("channel")
            assert len(channels) == 2

    def test_get_ppv_events_upcoming(self, app, client, sample_events):
        """Test GET /api/ppv-epg/events?mode=upcoming"""
        with app.app_context():
            response = client.get("/api/ppv-epg/events?mode=upcoming")

            assert response.status_code == 200
            data = response.get_json()

            assert "events" in data
            assert "count" in data
            assert data["count"] == 2

    def test_get_ppv_events_for_account(self, app, client, sample_events):
        """Test GET /api/ppv-epg/events?account_id=X"""
        with app.app_context():
            # Re-query account to avoid DetachedInstanceError
            from models import Account

            account = Account.query.first()

            response = client.get(f"/api/ppv-epg/events?account_id={account.id}")

            assert response.status_code == 200
            data = response.get_json()

            assert data["count"] == 2
            assert all("channel_name" in evt for evt in data["events"])

    def test_get_event_channels_route(self, app, client, sample_events):
        """Test GET /api/ppv-epg/events/<event_id>/channels"""
        with app.app_context():
            # Re-query event to avoid DetachedInstanceError
            event = Event.query.first()

            response = client.get(f"/api/ppv-epg/events/{event.id}/channels")

            assert response.status_code == 200
            data = response.get_json()

            assert data["count"] == 1
            assert data["channels"][0]["match_method"] == "direct_search"

    def test_create_ppv_epg_source_route(self, app, client):
        """Test POST /api/ppv-epg/source"""
        with app.app_context():
            response = client.post("/api/ppv-epg/source", json={"name": "My PPV EPG"})

            assert response.status_code == 200
            data = response.get_json()

            assert "epg_source_id" in data
            assert data["epg_source_id"] > 0

    def test_sync_ppv_events_to_source_route(self, app, client, sample_events):
        """Test POST /api/ppv-epg/source/<source_id>/sync"""
        with app.app_context():
            # Create source first
            source_id = PPVEpgService.create_epg_source_for_ppv_events()

            response = client.post(f"/api/ppv-epg/source/{source_id}/sync")

            assert response.status_code == 200
            data = response.get_json()

            assert data["created"] == 2
            assert data["updated"] == 0
            assert data["total"] == 2

    def test_get_ppv_epg_source_info_route(self, app, client):
        """Test GET /api/ppv-epg/source/<source_id>"""
        with app.app_context():
            source_id = PPVEpgService.create_epg_source_for_ppv_events(name="Test Source")

            response = client.get(f"/api/ppv-epg/source/{source_id}")

            assert response.status_code == 200
            data = response.get_json()

            assert data["id"] == source_id
            assert data["name"] == "Test Source"
            assert data["source_type"] == "ppv_events"

    def test_auto_creation_after_enrichment(self, app):
        """Test that PPV EPG source is auto-created after successful enrichment"""
        with app.app_context():
            from models import Account, Category, Event

            # Create test data
            account = Account(name="Test Account", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.flush()

            category = Category(account_id=account.id, category_id="ppv", category_name="PPV")
            db.session.add(category)
            db.session.flush()

            # Create an event
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            event = Event(
                external_id="auto_test",
                source=Event.SOURCE_THESPORTSDB,
                sport="Soccer",
                league_name="Test League",
                home_team_id="123",
                home_team_name="Team A",
                away_team_id="456",
                away_team_name="Team B",
                scheduled_at=now + timedelta(hours=2),
                status=Event.STATUS_SCHEDULED,
                is_ppv=True,
            )
            db.session.add(event)
            db.session.commit()

            # Verify no PPV EPG source exists initially
            initial_source = EpgSource.query.filter_by(source_type="ppv_events").first()
            assert initial_source is None

            # Test auto-creation by directly calling the service method
            from services.ppv_epg_service import PPVEpgService

            source_id = PPVEpgService.create_epg_source_for_ppv_events()

            # Fetch the created source
            source = db.session.get(EpgSource, source_id)

            # Verify EPG source was created
            assert source is not None
            assert source.source_type == "ppv_events"
            assert source.name == "PPV Events"
            assert source.enabled is True

            # Verify idempotency - calling again should return same source ID
            source_id2 = PPVEpgService.create_epg_source_for_ppv_events()
            assert source_id2 == source_id


def test_ppv_channel_epg_matching(app, sample_events):
    """Test that PPV channels are correctly matched to EPG data"""
    with app.app_context():
        from models import Account, Category, Channel, ChannelEpgMapping, Event, EventChannelLink
        from services.epg_match_rules_service import EpgMatchRulesService
        from services.ppv_epg_service import PPVEpgService

        # Get the event created by fixture
        event = Event.query.first()
        assert event is not None

        # Create a PPV channel
        account = Account.query.first()
        category = Category.query.first()

        channel = Channel(
            account_id=account.id,
            stream_id=9999,
            name="UFC 300 Main Event",
            category_id=category.id,
            stream_type="live",
            stream_icon="http://example.com/icon.png",
            epg_channel_id=None,
            is_ppv=True,
        )
        db.session.add(channel)
        db.session.commit()

        # Link the channel to the event
        link = EventChannelLink(channel_id=channel.id, event_id=event.id, match_method="test", match_confidence=1.0)
        db.session.add(link)
        db.session.commit()

        # Create EPG source and sync events
        source_id = PPVEpgService.create_epg_source_for_ppv_events()
        created, updated = PPVEpgService.sync_ppv_events_to_epg_channels(source_id)
        assert created > 0

        # Verify EPG channel was created with event-based ID
        epg_channel = EpgChannel.query.filter_by(source_id=source_id).first()
        assert epg_channel is not None
        assert epg_channel.channel_id == f"ppv-event-{event.external_id}"

        # Now run the matching
        stats = EpgMatchRulesService.match_ppv_channels_to_epg(source_id)

        # Verify stats
        assert stats["total_channels"] == 1
        assert stats["matched_count"] == 1
        assert stats["unmatched_count"] == 0
        assert stats["skipped_existing_count"] == 0

        # Verify mapping was created
        mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
        assert mapping is not None
        assert mapping.epg_channel_id == epg_channel.id
        assert mapping.mapping_type == "ppv_auto"
        assert mapping.confidence == 1.0

        # Test idempotency - running again should skip the existing mapping
        stats2 = EpgMatchRulesService.match_ppv_channels_to_epg(source_id)
        assert stats2["total_channels"] == 1
        assert stats2["matched_count"] == 0
        assert stats2["skipped_existing_count"] == 1

        # Verify only one mapping exists
        all_mappings = ChannelEpgMapping.query.filter_by(channel_id=channel.id).all()
        assert len(all_mappings) == 1
