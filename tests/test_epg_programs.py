"""
Tests for services/epg/programs.py

Tests the EPG program sync service including:
- XMLTV program parsing
- Program sync to database
- Current/upcoming program queries
- Schedule around time queries
- Cleanup of expired programs
"""
import gzip
from datetime import datetime, timedelta, timezone

import pytest

from models import Account, ChannelEpgMapping, EpgChannel, EpgProgram, EpgSource
from services.epg.programs import (
    _create_program,
    _update_program,
    cleanup_expired_programs,
    get_current_program,
    get_current_programs_batch,
    get_epg_channel_id_map,
    get_matched_epg_channel_ids,
    get_schedule_around_time,
    get_upcoming_programs,
    parse_xmltv_programs_streaming,
    search_programs_by_title,
    sync_programs_for_source,
)

# Sample XMLTV data for testing
SAMPLE_XMLTV = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv generator-info-name="test">
  <channel id="ch1">
    <display-name>Channel 1</display-name>
  </channel>
  <channel id="ch2">
    <display-name>Channel 2</display-name>
  </channel>
  <programme start="20260106120000 +0000" stop="20260106130000 +0000" channel="ch1">
    <title>Test Show 1</title>
    <sub-title>Episode Title</sub-title>
    <desc>Description of show</desc>
    <category>Sports</category>
    <category>Basketball</category>
    <episode-num system="xmltv_ns">1.5.0</episode-num>
    <rating system="VCHIP">
      <value>TV-14</value>
    </rating>
    <icon src="http://example.com/icon.png"/>
    <date>20251225</date>
    <new/>
    <live/>
  </programme>
  <programme start="20260106130000 +0000" stop="20260106140000 +0000" channel="ch1">
    <title>Test Show 2</title>
    <desc>Another show</desc>
    <episode-num system="onscreen">S1 E10</episode-num>
  </programme>
  <programme start="20260106140000 +0000" stop="20260106150000 +0000" channel="ch2">
    <title>Channel 2 Show</title>
    <episode-num system="dd_progid">EP123456</episode-num>
    <premiere/>
  </programme>
  <programme start="20260106100000 +0000" stop="20260106110000 +0000" channel="ch1">
    <title>Earlier Show</title>
  </programme>
</tv>
"""

XMLTV_NO_TITLE = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <programme start="20260106120000 +0000" stop="20260106130000 +0000" channel="ch1">
    <desc>No title program</desc>
  </programme>
</tv>
"""

XMLTV_INVALID_TIME = b"""<?xml version="1.0" encoding="UTF-8"?>
<tv>
  <programme start="invalid" stop="20260106130000 +0000" channel="ch1">
    <title>Invalid Time Show</title>
  </programme>
  <programme stop="20260106130000 +0000" channel="ch1">
    <title>Missing Start</title>
  </programme>
</tv>
"""


@pytest.fixture
def sample_account(db):
    """Create a sample account for testing."""
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
def sample_epg_source(db, sample_account):
    """Create a sample EPG source."""
    source = EpgSource(
        name="Test Source",
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
    ch1 = EpgChannel(
        source_id=sample_epg_source.id,
        channel_id="ch1",
        display_name="Channel 1",
    )
    ch2 = EpgChannel(
        source_id=sample_epg_source.id,
        channel_id="ch2",
        display_name="Channel 2",
    )
    db.session.add_all([ch1, ch2])
    db.session.commit()
    return [ch1, ch2]


class TestParseXmltvProgramsStreaming:
    """Tests for parse_xmltv_programs_streaming function."""

    def test_parse_basic_program(self, app):
        """Test parsing basic XMLTV program elements."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV))

            # Should find 4 programs total
            assert len(programs) == 4

            # Check first program details
            ch_id, prog = next((c, p) for c, p in programs if p.get("title") == "Test Show 1")
            assert ch_id == "ch1"
            assert prog["title"] == "Test Show 1"
            assert prog["sub_title"] == "Episode Title"
            assert prog["description"] == "Description of show"
            assert prog["categories"] == ["Sports", "Basketball"]
            assert prog["season"] == 2  # xmltv_ns is 0-indexed, so 1 + 1 = 2
            assert prog["episode"] == 6  # 5 + 1 = 6
            assert prog["rating"] == "TV-14"
            assert prog["rating_system"] == "VCHIP"
            assert prog["icon_url"] == "http://example.com/icon.png"
            assert prog["is_new"] is True
            assert prog["is_live"] is True

    def test_parse_onscreen_episode_format(self, app):
        """Test parsing onscreen episode format (S1 E10)."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV))

            prog = next(p for _, p in programs if p.get("title") == "Test Show 2")
            assert prog["season"] == 1
            assert prog["episode"] == 10

    def test_parse_dd_progid_format(self, app):
        """Test parsing dd_progid episode format."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV))

            prog = next(p for _, p in programs if p.get("title") == "Channel 2 Show")
            assert prog["episode_id"] == "EP123456"
            assert prog["is_premiere"] is True

    def test_filter_by_channel(self, app):
        """Test filtering programs by channel ID."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV, channel_filter={"ch1"}))

            # Should only have ch1 programs
            assert all(ch == "ch1" for ch, _ in programs)
            assert len(programs) == 3  # 3 programs on ch1

    def test_filter_by_time_start_after(self, app):
        """Test filtering programs starting after a time."""
        with app.app_context():
            cutoff = datetime(2026, 1, 6, 12, 30, tzinfo=timezone.utc).replace(tzinfo=None)
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV, start_after=cutoff))

            # Only programs starting after 12:30 UTC
            for _, prog in programs:
                assert prog["start_time"] >= cutoff

    def test_filter_by_time_end_before(self, app):
        """Test filtering programs starting before a time."""
        with app.app_context():
            cutoff = datetime(2026, 1, 6, 13, 0, tzinfo=timezone.utc).replace(tzinfo=None)
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV, end_before=cutoff))

            # Only programs starting before 13:00 UTC
            for _, prog in programs:
                assert prog["start_time"] < cutoff

    def test_skip_programs_without_title(self, app):
        """Test that programs without title are skipped."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(XMLTV_NO_TITLE))
            assert len(programs) == 0

    def test_skip_programs_with_invalid_times(self, app):
        """Test that programs with invalid times are skipped."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(XMLTV_INVALID_TIME))
            assert len(programs) == 0

    def test_parse_gzipped_content(self, app):
        """Test parsing gzip-compressed XMLTV content."""
        with app.app_context():
            compressed = gzip.compress(SAMPLE_XMLTV)
            programs = list(parse_xmltv_programs_streaming(compressed))
            assert len(programs) == 4

    def test_sport_detection_from_categories(self, app):
        """Test that sports are detected from categories."""
        with app.app_context():
            programs = list(parse_xmltv_programs_streaming(SAMPLE_XMLTV))

            prog = next(p for _, p in programs if p.get("title") == "Test Show 1")
            assert prog.get("sport") is not None


class TestProgramDatabaseOperations:
    """Tests for database operations on programs."""

    def test_create_program(self, app, db, sample_epg_channels):
        """Test creating a program in the database."""
        with app.app_context():
            ch = sample_epg_channels[0]
            data = {
                "start_time": datetime(2026, 1, 6, 12, 0, tzinfo=timezone.utc).replace(tzinfo=None),
                "stop_time": datetime(2026, 1, 6, 13, 0, tzinfo=timezone.utc).replace(tzinfo=None),
                "title": "Test Program",
                "sub_title": "Episode 1",
                "description": "Test description",
                "categories": ["Drama", "Action"],
                "season": 1,
                "episode": 5,
                "rating": "TV-14",
                "is_new": True,
                "is_live": False,
                "is_premiere": False,
            }

            prog = _create_program(ch.id, data)
            db.session.add(prog)
            db.session.commit()

            assert prog.id is not None
            assert prog.title == "Test Program"
            assert prog.sub_title == "Episode 1"
            assert prog.season == 1
            assert prog.episode == 5
            assert prog.is_new is True

    def test_update_program(self, app, db, sample_epg_channels):
        """Test updating an existing program."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create initial program
            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Original Title",
            )
            db.session.add(prog)
            db.session.commit()

            # Update it
            new_data = {
                "start_time": now,
                "stop_time": now + timedelta(hours=2),  # Extended
                "title": "Updated Title",
                "description": "New description",
                "is_live": True,
            }
            _update_program(prog, new_data)
            db.session.commit()

            # Verify updates
            refreshed = db.session.get(EpgProgram, prog.id)
            assert refreshed.title == "Updated Title"
            assert refreshed.description == "New description"
            assert refreshed.is_live is True


class TestGetChannelIdMap:
    """Tests for get_epg_channel_id_map function."""

    def test_get_channel_id_map(self, app, db, sample_epg_source, sample_epg_channels):
        """Test getting mapping from XMLTV ID to database ID."""
        with app.app_context():
            channel_map = get_epg_channel_id_map(sample_epg_source.id)

            assert "ch1" in channel_map
            assert "ch2" in channel_map
            assert channel_map["ch1"] == sample_epg_channels[0].id
            assert channel_map["ch2"] == sample_epg_channels[1].id

    def test_get_channel_id_map_no_channels(self, app, db, sample_epg_source):
        """Test with no channels for source."""
        with app.app_context():
            # Delete existing channels
            EpgChannel.query.filter_by(source_id=sample_epg_source.id).delete()
            db.session.commit()

            channel_map = get_epg_channel_id_map(sample_epg_source.id)
            assert channel_map == {}


class TestGetMatchedEpgChannelIds:
    """Tests for get_matched_epg_channel_ids function."""

    def test_no_matched_channels(self, app, db, sample_epg_source, sample_epg_channels):
        """Test when no channels have mappings."""
        with app.app_context():
            matched = get_matched_epg_channel_ids(sample_epg_source.id)
            assert matched == set()

    def test_with_matched_channels(self, app, db, sample_account, sample_epg_source, sample_epg_channels):
        """Test when some channels have mappings."""
        with app.app_context():
            from models import Category, Channel

            # Create a category and channel
            cat = Category(
                account_id=sample_account.id,
                category_id="1",
                category_name="Test Category",
            )
            db.session.add(cat)
            db.session.commit()

            channel = Channel(
                account_id=sample_account.id,
                stream_id=100,
                category_id=cat.id,
                name="Test Channel",
            )
            db.session.add(channel)
            db.session.commit()

            # Create mapping for ch1
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=sample_epg_channels[0].id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

            matched = get_matched_epg_channel_ids(sample_epg_source.id)
            assert sample_epg_channels[0].id in matched
            assert sample_epg_channels[1].id not in matched


class TestSyncProgramsForSource:
    """Tests for sync_programs_for_source function."""

    def test_sync_programs_basic(self, app, db, sample_epg_source, sample_epg_channels):
        """Test basic program sync."""
        with app.app_context():
            stats = sync_programs_for_source(sample_epg_source, SAMPLE_XMLTV)

            assert stats["channels_processed"] >= 1
            assert stats["programs_added"] >= 1

            # Check programs were created
            programs = EpgProgram.query.all()
            assert len(programs) >= 1

    def test_sync_programs_updates_existing(self, app, db, sample_epg_source, sample_epg_channels):
        """Test that sync updates existing programs."""
        with app.app_context():
            # First sync
            stats1 = sync_programs_for_source(sample_epg_source, SAMPLE_XMLTV)
            added1 = stats1["programs_added"]

            # Second sync - should update, not add
            stats2 = sync_programs_for_source(sample_epg_source, SAMPLE_XMLTV)

            # Updated programs should be same as previously added
            assert stats2["programs_updated"] >= added1 - stats2.get("programs_deleted", 0)


class TestGetCurrentProgram:
    """Tests for get_current_program function."""

    def test_get_current_program_found(self, app, db, sample_epg_channels):
        """Test getting currently airing program."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create a current program
            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(minutes=30),
                stop_time=now + timedelta(minutes=30),
                title="Currently Airing",
            )
            db.session.add(prog)
            db.session.commit()

            current = get_current_program(ch.id)
            assert current is not None
            assert current.title == "Currently Airing"

    def test_get_current_program_not_found(self, app, db, sample_epg_channels):
        """Test when no program is currently airing."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create a past program
            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(hours=2),
                stop_time=now - timedelta(hours=1),
                title="Past Show",
            )
            db.session.add(prog)
            db.session.commit()

            current = get_current_program(ch.id)
            assert current is None


class TestGetCurrentProgramsBatch:
    """Tests for get_current_programs_batch function."""

    def test_batch_empty_list(self, app, db):
        """Test with empty channel list."""
        with app.app_context():
            result = get_current_programs_batch([])
            assert result == {}

    def test_batch_multiple_channels(self, app, db, sample_epg_channels):
        """Test getting current programs for multiple channels."""
        with app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create current programs for both channels
            for i, ch in enumerate(sample_epg_channels):
                prog = EpgProgram(
                    epg_channel_id=ch.id,
                    start_time=now - timedelta(minutes=30),
                    stop_time=now + timedelta(minutes=30),
                    title=f"Current Show {i + 1}",
                )
                db.session.add(prog)
            db.session.commit()

            channel_ids = [ch.id for ch in sample_epg_channels]
            result = get_current_programs_batch(channel_ids)

            assert len(result) == 2
            assert sample_epg_channels[0].id in result
            assert sample_epg_channels[1].id in result


class TestGetUpcomingPrograms:
    """Tests for get_upcoming_programs function."""

    def test_upcoming_programs(self, app, db, sample_epg_channels):
        """Test getting upcoming programs."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create several future programs
            for i in range(5):
                prog = EpgProgram(
                    epg_channel_id=ch.id,
                    start_time=now + timedelta(hours=i + 1),
                    stop_time=now + timedelta(hours=i + 2),
                    title=f"Future Show {i + 1}",
                )
                db.session.add(prog)
            db.session.commit()

            upcoming = get_upcoming_programs(ch.id, hours=24, limit=3)

            assert len(upcoming) == 3
            # Should be ordered by start time
            assert upcoming[0].title == "Future Show 1"
            assert upcoming[1].title == "Future Show 2"


class TestSearchProgramsByTitle:
    """Tests for search_programs_by_title function."""

    def test_search_basic(self, app, db, sample_epg_channels):
        """Test basic title search."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create programs with different titles
            prog1 = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Football Game",
            )
            prog2 = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now + timedelta(hours=1),
                stop_time=now + timedelta(hours=2),
                title="Basketball Match",
            )
            db.session.add_all([prog1, prog2])
            db.session.commit()

            results = search_programs_by_title("Football")

            assert len(results) >= 1
            titles = [r[0].title for r in results]
            assert "Football Game" in titles

    def test_search_current_only(self, app, db, sample_epg_channels):
        """Test search with current_only filter."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create current and future programs
            current_prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(minutes=30),
                stop_time=now + timedelta(minutes=30),
                title="Game Now",
            )
            future_prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now + timedelta(hours=2),
                stop_time=now + timedelta(hours=3),
                title="Game Later",
            )
            db.session.add_all([current_prog, future_prog])
            db.session.commit()

            results = search_programs_by_title("Game", include_current_only=True)

            # Should only find the current program
            titles = [r[0].title for r in results]
            assert "Game Now" in titles
            assert "Game Later" not in titles


class TestGetScheduleAroundTime:
    """Tests for get_schedule_around_time function."""

    def test_schedule_around_current_time(self, app, db, sample_epg_channels):
        """Test getting schedule around current time."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create past, current, and future programs
            past = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(hours=2),
                stop_time=now - timedelta(hours=1),
                title="Past Show",
            )
            current = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(minutes=30),
                stop_time=now + timedelta(minutes=30),
                title="Current Show",
            )
            future = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now + timedelta(hours=1),
                stop_time=now + timedelta(hours=2),
                title="Future Show",
            )
            db.session.add_all([past, current, future])
            db.session.commit()

            result = get_schedule_around_time(ch.id)

            assert result["current_program"] is not None
            assert result["current_program"]["title"] == "Current Show"
            assert len(result["programs_before"]) >= 1
            assert len(result["programs_after"]) >= 1
            assert result["reference_time"].endswith("Z")
            assert result["adjusted_time"].endswith("Z")

    def test_schedule_with_time_offset(self, app, db, sample_epg_channels):
        """Test getting schedule with time offset applied."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create a program 2 hours in the future
            future_prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now + timedelta(hours=1, minutes=30),
                stop_time=now + timedelta(hours=2, minutes=30),
                title="Future Program",
            )
            db.session.add(future_prog)
            db.session.commit()

            # With +2 hour offset, this should be "current"
            result = get_schedule_around_time(ch.id, offset_hours=2)

            assert result["offset_hours"] == 2
            assert result["current_program"] is not None
            assert result["current_program"]["title"] == "Future Program"
            assert result["reference_time"].endswith("Z")
            assert result["adjusted_time"].endswith("Z")


class TestCleanupExpiredPrograms:
    """Tests for cleanup_expired_programs function."""

    def test_cleanup_old_programs(self, app, db, sample_epg_channels):
        """Test that old programs are cleaned up."""
        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create old and recent programs
            old_prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(days=3),
                stop_time=now - timedelta(days=2),
                title="Old Program",
            )
            recent_prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(hours=1),
                stop_time=now + timedelta(hours=1),
                title="Recent Program",
            )
            db.session.add_all([old_prog, recent_prog])
            db.session.commit()

            deleted = cleanup_expired_programs(days_old=1)

            assert deleted >= 1
            # Recent program should still exist
            remaining = EpgProgram.query.filter_by(epg_channel_id=ch.id).all()
            titles = [p.title for p in remaining]
            assert "Recent Program" in titles
            assert "Old Program" not in titles


# =============================================================================
# Tests for Database-Based EPG Generation Functions
# =============================================================================


class TestGetProgramsForChannels:
    """Tests for get_programs_for_channels function."""

    def test_get_programs_basic(self, app, db, sample_epg_channels):
        """Test basic program retrieval for multiple channels."""
        from services.epg.programs import get_programs_for_channels

        with app.app_context():
            ch1, ch2 = sample_epg_channels[0], sample_epg_channels[1]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create programs
            prog1 = EpgProgram(
                epg_channel_id=ch1.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Show on Ch1",
            )
            prog2 = EpgProgram(
                epg_channel_id=ch2.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Show on Ch2",
            )
            db.session.add_all([prog1, prog2])
            db.session.commit()

            result = get_programs_for_channels([ch1.id, ch2.id])

            assert len(result) == 2
            assert ch1.id in result
            assert ch2.id in result
            assert len(result[ch1.id]) == 1
            assert len(result[ch2.id]) == 1
            assert result[ch1.id][0].title == "Show on Ch1"

    def test_get_programs_empty_list(self, app, db):
        """Test with empty channel list."""
        from services.epg.programs import get_programs_for_channels

        with app.app_context():
            result = get_programs_for_channels([])
            assert result == {}

    def test_get_programs_time_range(self, app, db, sample_epg_channels):
        """Test program retrieval with time range filtering."""
        from services.epg.programs import get_programs_for_channels

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create programs at different times
            past = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(hours=5),
                stop_time=now - timedelta(hours=4),
                title="Past Show",
            )
            current = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(minutes=30),
                stop_time=now + timedelta(minutes=30),
                title="Current Show",
            )
            future = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now + timedelta(hours=2),
                stop_time=now + timedelta(hours=3),
                title="Future Show",
            )
            db.session.add_all([past, current, future])
            db.session.commit()

            # Get only current hour
            start = now - timedelta(hours=1)
            end = now + timedelta(hours=1)
            result = get_programs_for_channels([ch.id], start, end)

            assert len(result[ch.id]) == 1
            assert result[ch.id][0].title == "Current Show"


class TestFormatXmltvTime:
    """Tests for format_xmltv_time function."""

    def test_format_basic(self):
        """Test basic time formatting."""
        from services.epg.programs import format_xmltv_time

        dt = datetime(2026, 1, 6, 12, 30, 45)
        result = format_xmltv_time(dt)
        assert result == "20260106123045 +0000"

    def test_format_with_offset(self):
        """Test time formatting with hour offset."""
        from services.epg.programs import format_xmltv_time

        dt = datetime(2026, 1, 6, 12, 0, 0)
        result = format_xmltv_time(dt, offset_hours=3)
        assert result == "20260106150000 +0000"

    def test_format_negative_offset(self):
        """Test time formatting with negative offset."""
        from services.epg.programs import format_xmltv_time

        dt = datetime(2026, 1, 6, 12, 0, 0)
        result = format_xmltv_time(dt, offset_hours=-3)
        assert result == "20260106090000 +0000"


class TestProgramToXmltvElement:
    """Tests for program_to_xmltv_element function."""

    def test_basic_conversion(self, app, db, sample_epg_channels):
        """Test converting a program to XMLTV element."""
        from services.epg.programs import program_to_xmltv_element

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Test Show",
                description="A test description",
            )

            elem = program_to_xmltv_element(prog, "ch-1-100")

            assert elem.tag == "programme"
            assert elem.get("channel") == "ch-1-100"
            assert elem.find("title").text == "Test Show"
            assert elem.find("desc").text == "A test description"

    def test_with_episode_info(self, app, db, sample_epg_channels):
        """Test conversion with season/episode info."""
        from services.epg.programs import program_to_xmltv_element

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Episode Show",
                season=2,
                episode=5,
            )

            elem = program_to_xmltv_element(prog, "ch-1-100")

            # Check XMLTV NS format (0-indexed)
            ep_nums = elem.findall("episode-num")
            assert len(ep_nums) >= 1
            xmltv_ns = [e for e in ep_nums if e.get("system") == "xmltv_ns"]
            assert len(xmltv_ns) == 1
            assert xmltv_ns[0].text == "1.4."  # Season 2-1=1, Episode 5-1=4

            # Check onscreen format
            onscreen = [e for e in ep_nums if e.get("system") == "onscreen"]
            assert len(onscreen) == 1
            assert onscreen[0].text == "S02E05"

    def test_with_time_offset(self, app, db, sample_epg_channels):
        """Test conversion with time offset applied."""
        from services.epg.programs import program_to_xmltv_element

        with app.app_context():
            ch = sample_epg_channels[0]
            start = datetime(2026, 1, 6, 12, 0, 0)
            stop = datetime(2026, 1, 6, 13, 0, 0)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=start,
                stop_time=stop,
                title="Offset Show",
            )

            elem = program_to_xmltv_element(prog, "ch-1-100", time_offset_hours=-3)

            assert elem.get("start") == "20260106090000 +0000"
            assert elem.get("stop") == "20260106100000 +0000"

    def test_with_categories(self, app, db, sample_epg_channels):
        """Test conversion with categories."""
        import json

        from services.epg.programs import program_to_xmltv_element

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Sports Show",
                categories=json.dumps(["Sports", "Basketball"]),
            )

            elem = program_to_xmltv_element(prog, "ch-1-100")

            cats = elem.findall("category")
            assert len(cats) == 2
            cat_texts = [c.text for c in cats]
            assert "Sports" in cat_texts
            assert "Basketball" in cat_texts

    def test_with_flags(self, app, db, sample_epg_channels):
        """Test conversion with flags (new, live, premiere)."""
        from services.epg.programs import program_to_xmltv_element

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Flagged Show",
                is_new=True,
                is_live=True,
                is_premiere=True,
            )

            elem = program_to_xmltv_element(prog, "ch-1-100")

            assert elem.find("new") is not None
            assert elem.find("live") is not None
            assert elem.find("premiere") is not None


class TestGenerateXmltvFromDatabase:
    """Tests for generate_xmltv_from_database function."""

    def test_basic_generation(self, app, db, sample_epg_channels):
        """Test basic XMLTV generation from database."""
        import xml.etree.ElementTree as ET

        from services.epg.programs import generate_xmltv_from_database

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            # Create programs
            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="DB Generated Show",
            )
            db.session.add(prog)
            db.session.commit()

            mappings = [(ch.id, "ch-1-100", 0, ch)]
            result = generate_xmltv_from_database(mappings)

            # Parse result
            root = ET.fromstring(result)
            assert root.tag == "tv"

            channels = root.findall("channel")
            assert len(channels) == 1
            assert channels[0].get("id") == "ch-1-100"

            programmes = root.findall("programme")
            assert len(programmes) == 1
            assert programmes[0].find("title").text == "DB Generated Show"

    def test_empty_mappings(self, app, db):
        """Test generation with empty mappings."""
        from services.epg.programs import generate_xmltv_from_database

        with app.app_context():
            result = generate_xmltv_from_database([])
            assert b"<tv" in result
            assert b"</tv>" in result

    def test_with_time_offset(self, app, db, sample_epg_channels):
        """Test generation with time offset."""
        import xml.etree.ElementTree as ET

        from services.epg.programs import generate_xmltv_from_database

        with app.app_context():
            ch = sample_epg_channels[0]
            start = datetime(2026, 1, 6, 12, 0, 0)
            stop = datetime(2026, 1, 6, 13, 0, 0)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=start,
                stop_time=stop,
                title="Offset Show",
            )
            db.session.add(prog)
            db.session.commit()

            mappings = [(ch.id, "ch-1-100", -3, ch)]
            result = generate_xmltv_from_database(
                mappings,
                start_time=datetime(2026, 1, 6, 0, 0, 0),
                end_time=datetime(2026, 1, 7, 0, 0, 0),
            )

            root = ET.fromstring(result)
            prog_elem = root.find("programme")
            assert prog_elem.get("start") == "20260106090000 +0000"

    def test_multiple_channels(self, app, db, sample_epg_channels):
        """Test generation with multiple channels."""
        import xml.etree.ElementTree as ET

        from services.epg.programs import generate_xmltv_from_database

        with app.app_context():
            ch1, ch2 = sample_epg_channels[0], sample_epg_channels[1]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog1 = EpgProgram(
                epg_channel_id=ch1.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Ch1 Show",
            )
            prog2 = EpgProgram(
                epg_channel_id=ch2.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Ch2 Show",
            )
            db.session.add_all([prog1, prog2])
            db.session.commit()

            mappings = [
                (ch1.id, "ch-1-100", 0, ch1),
                (ch2.id, "ch-1-101", 0, ch2),
            ]
            result = generate_xmltv_from_database(mappings)

            root = ET.fromstring(result)
            channels = root.findall("channel")
            programmes = root.findall("programme")

            assert len(channels) == 2
            assert len(programmes) == 2


class TestHasProgramsInDatabase:
    """Tests for has_programs_in_database function."""

    def test_channel_with_programs(self, app, db, sample_epg_channels):
        """Test channel that has programs."""
        from services.epg.programs import has_programs_in_database

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now,
                stop_time=now + timedelta(hours=1),
                title="Current Show",
            )
            db.session.add(prog)
            db.session.commit()

            assert has_programs_in_database(ch.id) is True

    def test_channel_without_programs(self, app, db, sample_epg_channels):
        """Test channel that has no programs."""
        from services.epg.programs import has_programs_in_database

        with app.app_context():
            ch = sample_epg_channels[0]
            assert has_programs_in_database(ch.id) is False

    def test_channel_with_only_past_programs(self, app, db, sample_epg_channels):
        """Test channel with only expired programs."""
        from services.epg.programs import has_programs_in_database

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now - timedelta(hours=5),
                stop_time=now - timedelta(hours=4),
                title="Past Show",
            )
            db.session.add(prog)
            db.session.commit()

            assert has_programs_in_database(ch.id) is False


class TestGetDatabaseCoverageStats:
    """Tests for get_database_coverage_stats function."""

    def test_coverage_with_programs(self, app, db, sample_epg_source, sample_epg_channels):
        """Test coverage stats when some channels have programs."""
        from services.epg.programs import get_database_coverage_stats

        with app.app_context():
            ch = sample_epg_channels[0]
            now = datetime.now(timezone.utc).replace(tzinfo=None)

            prog = EpgProgram(
                epg_channel_id=ch.id,
                start_time=now + timedelta(hours=1),
                stop_time=now + timedelta(hours=2),
                title="Future Show",
            )
            db.session.add(prog)
            db.session.commit()

            stats = get_database_coverage_stats(sample_epg_source.id)

            assert stats["source_id"] == sample_epg_source.id
            assert stats["total_channels"] >= 1
            assert stats["channels_with_programs"] >= 1
            assert stats["total_programs"] >= 1

    def test_coverage_empty_source(self, app, db, sample_epg_source):
        """Test coverage stats for source with no programs."""
        from services.epg.programs import get_database_coverage_stats

        with app.app_context():
            stats = get_database_coverage_stats(sample_epg_source.id)

            assert stats["channels_with_programs"] == 0
            assert stats["total_programs"] == 0
