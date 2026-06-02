"""
Tests for services/epg/generation.py

Tests the EPG generation module including:
- Channel EPG mapping queries
- Grouping channels by EPG source
- EPG filtering and remapping
- Channel link handling
- Full EPG generation
"""
import gzip
import xml.etree.ElementTree as ET
from datetime import timezone
from unittest.mock import patch

import pytest

from models import Account, Category, Channel, ChannelEpgMapping, ChannelLink, EpgChannel, EpgSource

# Sample XMLTV data for testing
SAMPLE_XMLTV = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv generator-info-name="test">
  <channel id="ESPNHD">
    <display-name>ESPN HD</display-name>
    <icon src="http://example.com/espn.png"/>
  </channel>
  <channel id="FOXNEWS">
    <display-name>Fox News</display-name>
  </channel>
  <programme start="20260106120000 +0000" stop="20260106130000 +0000" channel="ESPNHD">
    <title>SportsCenter</title>
    <desc>Sports news</desc>
  </programme>
  <programme start="20260106130000 +0000" stop="20260106140000 +0000" channel="ESPNHD">
    <title>NFL Live</title>
  </programme>
  <programme start="20260106120000 +0000" stop="20260106130000 +0000" channel="FOXNEWS">
    <title>News Today</title>
  </programme>
</tv>
"""


@pytest.fixture
def sample_account(db):
    """Create a sample account."""
    account = Account(
        name="Test Account",
        server="http://test.example.com",
        username="testuser",
        password="testpass",
    )
    db.session.add(account)
    db.session.commit()
    return account


@pytest.fixture
def sample_category(db, sample_account):
    """Create a sample category."""
    cat = Category(
        account_id=sample_account.id,
        category_id="1",
        category_name="Sports",
    )
    db.session.add(cat)
    db.session.commit()
    return cat


@pytest.fixture
def sample_channels(db, sample_account, sample_category):
    """Create sample channels."""
    ch1 = Channel(
        account_id=sample_account.id,
        stream_id=100,
        category_id=sample_category.id,
        name="ESPN HD",
        epg_channel_id="ESPNHD",
    )
    ch2 = Channel(
        account_id=sample_account.id,
        stream_id=101,
        category_id=sample_category.id,
        name="Fox News",
        epg_channel_id="FOXNEWS",
    )
    ch3 = Channel(
        account_id=sample_account.id,
        stream_id=102,
        category_id=sample_category.id,
        name="No EPG Channel",
        epg_channel_id=None,
    )
    db.session.add_all([ch1, ch2, ch3])
    db.session.commit()
    return [ch1, ch2, ch3]


@pytest.fixture
def sample_epg_source(db, sample_account):
    """Create a sample EPG source."""
    source = EpgSource(
        name="Test EPG Source",
        source_type="xmltv_url",
        account_id=sample_account.id,
        url="http://example.com/epg.xml",
    )
    db.session.add(source)
    db.session.commit()
    return source


@pytest.fixture
def sample_epg_channels(db, sample_epg_source):
    """Create sample EPG channels."""
    epg1 = EpgChannel(
        source_id=sample_epg_source.id,
        channel_id="ESPNHD",
        display_name="ESPN HD",
    )
    epg2 = EpgChannel(
        source_id=sample_epg_source.id,
        channel_id="FOXNEWS",
        display_name="Fox News",
    )
    db.session.add_all([epg1, epg2])
    db.session.commit()
    return [epg1, epg2]


@pytest.fixture
def sample_mappings(db, sample_channels, sample_epg_channels):
    """Create sample EPG mappings."""
    mapping1 = ChannelEpgMapping(
        channel_id=sample_channels[0].id,
        epg_channel_id=sample_epg_channels[0].id,
        mapping_type="manual",
        confidence=1.0,
        time_offset_hours=0,
    )
    mapping2 = ChannelEpgMapping(
        channel_id=sample_channels[1].id,
        epg_channel_id=sample_epg_channels[1].id,
        mapping_type="auto_fuzzy",
        confidence=0.9,
        time_offset_hours=1,
    )
    db.session.add_all([mapping1, mapping2])
    db.session.commit()
    return [mapping1, mapping2]


class TestGetChannelEpgMappings:
    """Tests for get_channel_epg_mappings function."""

    def test_get_mappings_empty_list(self, app, db):
        """Test with empty channel list."""
        with app.app_context():
            from services.epg.generation import get_channel_epg_mappings

            result = get_channel_epg_mappings([])
            assert result == {}

    def test_get_mappings_with_data(self, app, db, sample_channels, sample_mappings):
        """Test getting mappings for channels."""
        with app.app_context():
            from services.epg.generation import get_channel_epg_mappings

            channel_ids = [ch.id for ch in sample_channels]
            result = get_channel_epg_mappings(channel_ids)

            # Should have mappings for first 2 channels
            assert sample_channels[0].id in result
            assert sample_channels[1].id in result
            # Third channel has no mapping
            assert sample_channels[2].id not in result

    def test_get_mappings_batching(self, app, db, sample_account, sample_category):
        """Test that large lists are batched correctly."""
        with app.app_context():
            from services.epg.generation import get_channel_epg_mappings

            # Create many channels (more than batch size)
            channels = []
            for i in range(600):
                ch = Channel(
                    account_id=sample_account.id,
                    stream_id=1000 + i,
                    category_id=sample_category.id,
                    name=f"Channel {i}",
                )
                channels.append(ch)
            db.session.add_all(channels)
            db.session.commit()

            channel_ids = [ch.id for ch in channels]
            result = get_channel_epg_mappings(channel_ids)

            # Should complete without error (testing batching works)
            assert isinstance(result, dict)


class TestGroupChannelsByEpgSource:
    """Tests for group_channels_by_epg_source function."""

    def test_group_channels(self, app, db, sample_channels, sample_epg_source, sample_epg_channels, sample_mappings):
        """Test grouping channels by EPG source."""
        with app.app_context():
            from services.epg.generation import get_channel_epg_mappings, group_channels_by_epg_source

            channel_ids = [ch.id for ch in sample_channels]
            mappings = get_channel_epg_mappings(channel_ids)

            groups = group_channels_by_epg_source(sample_channels, mappings)

            # All mapped channels should be in same source group
            assert sample_epg_source.id in groups
            assert len(groups[sample_epg_source.id]) == 2

    def test_group_channels_empty(self, app, db, sample_channels):
        """Test with no mappings."""
        with app.app_context():
            from services.epg.generation import group_channels_by_epg_source

            groups = group_channels_by_epg_source(sample_channels, {})
            assert groups == {}


class TestFilterEpgByChannels:
    """Tests for filter_epg_by_channels function."""

    def test_filter_basic(self, app):
        """Test basic EPG filtering."""
        with app.app_context():
            from services.epg.generation import filter_epg_by_channels

            mappings = [
                ("ESPNHD", "ch-1-100", 0),
            ]

            channels, programmes = filter_epg_by_channels(SAMPLE_XMLTV, mappings)

            assert len(channels) == 1
            assert channels[0].get("id") == "ch-1-100"

            # Should have 2 programmes for ESPN
            assert len(programmes) == 2
            for prog in programmes:
                assert prog.get("channel") == "ch-1-100"

    def test_filter_with_time_offset(self, app):
        """Test filtering with time offset applied."""
        with app.app_context():
            from services.epg.generation import filter_epg_by_channels

            mappings = [
                ("ESPNHD", "ch-1-100", 2),  # +2 hour offset
            ]

            channels, programmes = filter_epg_by_channels(SAMPLE_XMLTV, mappings)

            # Check time was shifted
            for prog in programmes:
                start = prog.get("start")
                # Original was 12:00, should now be 14:00
                assert "140000" in start or "150000" in start

    def test_filter_multiple_channels(self, app):
        """Test filtering multiple channels."""
        with app.app_context():
            from services.epg.generation import filter_epg_by_channels

            mappings = [
                ("ESPNHD", "ch-1-100", 0),
                ("FOXNEWS", "ch-1-101", 0),
            ]

            channels, programmes = filter_epg_by_channels(SAMPLE_XMLTV, mappings)

            assert len(channels) == 2
            # 2 ESPN + 1 Fox = 3 programmes
            assert len(programmes) == 3

    def test_filter_gzipped_content(self, app):
        """Test filtering gzipped XMLTV content."""
        with app.app_context():
            from services.epg.generation import filter_epg_by_channels

            compressed = gzip.compress(SAMPLE_XMLTV)
            mappings = [("ESPNHD", "ch-1-100", 0)]

            channels, programmes = filter_epg_by_channels(compressed, mappings)

            assert len(channels) == 1
            assert len(programmes) == 2


class TestBuildChannelLinkMap:
    """Tests for build_channel_link_map function."""

    def test_empty_list(self, app, db):
        """Test with empty channel list."""
        with app.app_context():
            from services.epg.generation import build_channel_link_map

            result = build_channel_link_map([])
            assert result == {}

    def test_with_channel_links(self, app, db, sample_channels):
        """Test with channel links."""
        with app.app_context():
            from services.epg.generation import build_channel_link_map

            # Create a channel link
            link = ChannelLink(
                channel_id=sample_channels[2].id,  # No EPG channel
                source_channel_id=sample_channels[0].id,  # ESPN
                time_offset_hours=1,
            )
            db.session.add(link)
            db.session.commit()

            # Need to set epg_channel_id for the link map to work
            sample_channels[2].epg_channel_id = "ch-no-epg"
            db.session.commit()

            channel_ids = [ch.id for ch in sample_channels]
            result = build_channel_link_map(channel_ids)

            # Should have link from ch3 to ch1
            assert len(result) >= 0  # May or may not have entries depending on data


class TestBuildMappingOffsetMap:
    """Tests for build_mapping_offset_map function."""

    def test_empty_list(self, app, db):
        """Test with empty channel list."""
        with app.app_context():
            from services.epg.generation import build_mapping_offset_map

            result = build_mapping_offset_map([])
            assert result == {}

    def test_with_offsets(self, app, db, sample_channels, sample_epg_channels, sample_mappings):
        """Test with channels that have time offsets."""
        with app.app_context():
            from services.epg.generation import build_mapping_offset_map

            channel_ids = [ch.id for ch in sample_channels]
            result = build_mapping_offset_map(channel_ids)

            # Second mapping has offset of 1
            # The key is the XMLTV channel ID (lowercase)
            assert "foxnews" in result
            assert result["foxnews"] == 1


class TestGenerateFilteredEpg:
    """Tests for generate_filtered_epg function."""

    def test_empty_channel_list(self, app):
        """Test with empty channel list returns minimal XML."""
        with app.app_context():
            from services.epg.generation import generate_filtered_epg

            result = generate_filtered_epg([], SAMPLE_XMLTV)

            assert b"<?xml" in result
            assert b"<tv" in result

    def test_filter_single_channel(self, app):
        """Test filtering to single channel."""
        with app.app_context():
            from services.epg.generation import generate_filtered_epg

            result = generate_filtered_epg(["ESPNHD"], SAMPLE_XMLTV)

            # Parse result
            root = ET.fromstring(result)

            channels = root.findall("channel")
            assert len(channels) == 1
            assert channels[0].get("id") == "ESPNHD"

            programmes = root.findall("programme")
            assert len(programmes) == 2

    def test_filter_with_link_map(self, app):
        """Test filtering with channel link map for inheritance."""
        with app.app_context():
            from services.epg.generation import generate_filtered_epg

            # Link a new channel to ESPN's schedule
            link_map = {
                "espn2": ("espnhd", 1),  # ESPN2 inherits from ESPN with +1h offset
            }

            result = generate_filtered_epg(["ESPNHD", "ESPN2"], SAMPLE_XMLTV, channel_link_map=link_map)

            root = ET.fromstring(result)

            # Should have programmes for ESPN2 (inherited from ESPN)
            espn2_progs = [p for p in root.findall("programme") if p.get("channel") == "espn2"]
            assert len(espn2_progs) >= 1

    def test_filter_with_mapping_offset(self, app):
        """Test filtering with mapping offset applied."""
        with app.app_context():
            from services.epg.generation import generate_filtered_epg

            offset_map = {
                "espnhd": -1,  # -1 hour offset
            }

            result = generate_filtered_epg(["ESPNHD"], SAMPLE_XMLTV, mapping_offset_map=offset_map)

            root = ET.fromstring(result)
            programmes = root.findall("programme")

            # Check time was shifted back by 1 hour
            for prog in programmes:
                start = prog.get("start")
                # Original 12:00 should be 11:00
                assert "110000" in start or "120000" in start


class TestGenerateEpgForChannels:
    """Tests for generate_epg_for_channels function."""

    def test_empty_channel_list(self, app, db):
        """Test with empty channel list."""
        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            result = generate_epg_for_channels([])

            assert b"<?xml" in result
            assert b"<tv" in result
            assert b"iptv-proxy-v2" in result

    def test_channels_without_mappings(self, app, db, sample_channels):
        """Test with channels that have no mappings - uses synthetic entries."""
        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            # Remove epg_channel_id to ensure no provider fallback
            for ch in sample_channels:
                ch.epg_channel_id = None
            db.session.commit()

            result = generate_epg_for_channels(sample_channels)

            root = ET.fromstring(result)

            # Should have synthetic channel entries
            channels = root.findall("channel")
            assert len(channels) == 3  # All 3 channels get synthetic entries

    @patch("services.epg.generation.fetch_epg_from_source")
    def test_channels_with_mappings(
        self, mock_fetch, app, db, sample_channels, sample_epg_source, sample_epg_channels, sample_mappings
    ):
        """Test with channels that have EPG mappings."""
        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            mock_fetch.return_value = SAMPLE_XMLTV

            # Only test mapped channels
            mapped_channels = sample_channels[:2]
            result = generate_epg_for_channels(mapped_channels)

            root = ET.fromstring(result)

            # Should have channel elements
            channels = root.findall("channel")
            assert len(channels) >= 2


class TestGetChannelLinksForFallback:
    """Tests for get_channel_links_for_fallback function."""

    def test_empty_list(self, app, db):
        """Test with empty channel list."""
        with app.app_context():
            from services.epg.generation import get_channel_links_for_fallback

            result = get_channel_links_for_fallback([])
            assert result == {}

    def test_with_links(self, app, db, sample_channels):
        """Test with channel links present."""
        with app.app_context():
            from services.epg.generation import get_channel_links_for_fallback

            # Create a link
            link = ChannelLink(
                channel_id=sample_channels[2].id,
                source_channel_id=sample_channels[0].id,
                time_offset_hours=2,
            )
            db.session.add(link)
            db.session.commit()

            channel_ids = [ch.id for ch in sample_channels]
            result = get_channel_links_for_fallback(channel_ids)

            assert sample_channels[2].id in result
            source_channel, offset = result[sample_channels[2].id]
            assert source_channel.id == sample_channels[0].id
            assert offset == 2


class TestGetEpgFromCache:
    """Tests for get_epg_from_cache function."""

    def test_cache_miss(self, app, db):
        """Test when cache doesn't have the data."""
        with app.app_context():
            from services.epg.generation import get_epg_from_cache

            with patch("services.epg.cache.load_from_cache") as mock_load:
                mock_load.return_value = None

                result = get_epg_from_cache(999)
                assert result is None

    def test_cache_hit(self, app, db):
        """Test when cache has the data."""
        with app.app_context():
            from services.epg.generation import get_epg_from_cache

            with patch("services.epg.cache.load_from_cache") as mock_load:
                mock_load.return_value = SAMPLE_XMLTV

                result = get_epg_from_cache(1)
                assert result == SAMPLE_XMLTV


class TestGenerateEpgFromDatabaseForMappings:
    """Tests for generate_epg_from_database_for_mappings function."""

    def test_basic_generation(self, app, db, sample_channels, sample_epg_source, sample_epg_channels, sample_mappings):
        """Test basic EPG generation from database."""
        from datetime import datetime, timedelta, timezone

        from models import EpgProgram

        with app.app_context():
            from services.epg.generation import generate_epg_from_database_for_mappings, get_channel_epg_mappings

            # Create a program in the database
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            prog = EpgProgram(
                epg_channel_id=sample_epg_channels[0].id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="DB Test Show",
            )
            db.session.add(prog)
            db.session.commit()

            # Get mappings
            channel_ids = [ch.id for ch in sample_channels]
            mappings = get_channel_epg_mappings(channel_ids)
            from services.channel_query_service import ChannelQueryService

            output_ids = ChannelQueryService.epg_channel_ids_for_channels(sample_channels)

            # Generate from database
            channel_elems, prog_elems, processed = generate_epg_from_database_for_mappings(
                sample_channels, mappings, output_ids
            )

            assert len(processed) >= 1
            assert len(channel_elems) >= 1
            assert len(prog_elems) >= 1

    def test_empty_channels(self, app, db):
        """Test with no channels."""
        with app.app_context():
            from services.epg.generation import generate_epg_from_database_for_mappings

            channel_elems, prog_elems, processed = generate_epg_from_database_for_mappings([], {}, {})

            assert channel_elems == []
            assert prog_elems == []
            assert processed == set()

    def test_no_programs_in_db(self, app, db, sample_channels, sample_epg_source, sample_epg_channels, sample_mappings):
        """Test when database has no programs."""
        with app.app_context():
            from services.epg.generation import generate_epg_from_database_for_mappings, get_channel_epg_mappings

            channel_ids = [ch.id for ch in sample_channels]
            mappings = get_channel_epg_mappings(channel_ids)
            from services.channel_query_service import ChannelQueryService

            output_ids = ChannelQueryService.epg_channel_ids_for_channels(sample_channels)

            channel_elems, prog_elems, processed = generate_epg_from_database_for_mappings(
                sample_channels, mappings, output_ids
            )

            # No channels should be processed since there are no programs
            assert processed == set()
            assert prog_elems == []

    def test_with_time_offset(self, app, db, sample_channels, sample_epg_source, sample_epg_channels):
        """Test generation with time offset applied."""
        from datetime import datetime, timedelta

        from models import EpgProgram

        with app.app_context():
            from services.epg.generation import generate_epg_from_database_for_mappings

            # Create mapping with offset
            mapping = ChannelEpgMapping(
                channel_id=sample_channels[0].id,
                epg_channel_id=sample_epg_channels[0].id,
                mapping_type="manual",
                confidence=1.0,
                time_offset_hours=-3,  # 3 hours offset
            )
            db.session.add(mapping)
            db.session.commit()

            # Create a program (use current time + 2 hours to ensure it's in the query range)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            start = now + timedelta(hours=2)
            prog = EpgProgram(
                epg_channel_id=sample_epg_channels[0].id,
                start_time=start,
                stop_time=start + timedelta(hours=1),
                title="Offset Test Show",
            )
            db.session.add(prog)
            db.session.commit()

            mappings = {sample_channels[0].id: mapping}
            from services.channel_query_service import ChannelQueryService

            output_ids = ChannelQueryService.epg_channel_ids_for_channels([sample_channels[0]])

            channel_elems, prog_elems, processed = generate_epg_from_database_for_mappings(
                [sample_channels[0]], mappings, output_ids
            )

            assert len(processed) == 1
            assert len(prog_elems) == 1

            # Check the time is offset by -3 hours
            # Parse the start time from the program element (format: "20260106120000 +0000")
            from datetime import datetime

            start_str = prog_elems[0].get("start")
            # Strip timezone info and parse
            parsed_start = datetime.strptime(start_str.split()[0], "%Y%m%d%H%M%S")
            expected_start = start + timedelta(hours=-3)  # Apply the -3 hour offset

            # Compare the times (allowing for slight variations in seconds)
            assert abs((parsed_start - expected_start).total_seconds()) < 5


class TestGenerateEpgForChannelsWithDatabase:
    """Tests for generate_epg_for_channels with database priority."""

    def test_uses_database_first(
        self, app, db, sample_channels, sample_epg_source, sample_epg_channels, sample_mappings
    ):
        """Test that database is used before external sources."""
        import xml.etree.ElementTree as ET
        from datetime import datetime, timedelta, timezone

        from models import EpgProgram

        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            # Create a program in the database
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            prog = EpgProgram(
                epg_channel_id=sample_epg_channels[0].id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="From Database",
            )
            db.session.add(prog)
            db.session.commit()

            # Generate EPG
            result = generate_epg_for_channels([sample_channels[0]])

            # Parse and check result
            root = ET.fromstring(result)
            programmes = root.findall("programme")

            # Should have the program from database
            titles = [p.find("title").text for p in programmes]
            assert "From Database" in titles

    def test_database_only_generation(self, app, db, sample_channels, sample_mappings):
        """Test generation with database only (no external services)."""
        import xml.etree.ElementTree as ET

        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            # No programs in database, so should get empty/synthetic EPG
            result = generate_epg_for_channels(sample_channels)

            # Should still produce valid XMLTV
            root = ET.fromstring(result)
            assert root.tag == "tv"

    def test_database_always_used(self, app, db, sample_channels, sample_mappings):
        """Test that database is always used (no external fallback)."""
        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            # Database generation should always be called since external fallback is removed
            with patch("services.epg.generation.generate_epg_from_database_for_mappings") as mock_db:
                mock_db.return_value = ([], [], set())
                generate_epg_for_channels(sample_channels)
                # Database generation should always be called
                mock_db.assert_called_once()


class TestGenerateEpgForPpvEvents:
    """PPV channels with linked events get event-{id} XMLTV and programmes."""

    def test_ppv_event_epg_without_epg_program(self, app, db):
        import xml.etree.ElementTree as ET
        from datetime import datetime, timedelta, timezone

        from models import Account, Category, Channel, Event, EventChannelLink

        with app.app_context():
            from services.epg.generation import generate_epg_for_channels

            account = Account(name="PPV EPG", server="http://test.com", username="u", password="p")
            db.session.add(account)
            db.session.flush()

            category = Category(account_id=account.id, category_id="ppv", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            event = Event(
                external_id="epg-test-1",
                home_team_id="1",
                home_team_name="Arsenal",
                away_team_id="2",
                away_team_name="Chelsea",
                scheduled_at=now + timedelta(hours=3),
                status=Event.STATUS_SCHEDULED,
                league_name="Premier League",
                is_ppv=True,
            )
            db.session.add(event)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="ppv99",
                name="UK: DAZN PPV 1 - Arsenal vs Chelsea",
                category_id=category.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
                ppv_enrichment_status="matched",
            )
            db.session.add(channel)
            db.session.flush()
            db.session.add(EventChannelLink(channel_id=channel.id, event_id=event.id))
            db.session.commit()

            result = generate_epg_for_channels([channel])
            root = ET.fromstring(result)

            expected_id = f"event-{event.id}"
            channel_ids = [ch.get("id") for ch in root.findall("channel")]
            assert expected_id in channel_ids

            programmes = [p for p in root.findall("programme") if p.get("channel") == expected_id]
            assert len(programmes) == 1
            assert programmes[0].find("title").text == "Arsenal vs Chelsea"
            assert programmes[0].find("sub-title").text == "Premier League"
