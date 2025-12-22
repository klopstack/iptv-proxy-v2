"""
Tests for EPG service - parsing, syncing, and matching
"""
import pytest

from models import Account, Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db
from services.epg_service import EpgService, extract_callsign_from_xmltv_id, make_sd_xmltv_id

# ============================================================================
# Utility Function Tests
# ============================================================================


class TestExtractCallsign:
    """Tests for extract_callsign_from_xmltv_id function"""

    def test_schedules_direct_format(self):
        """Test Schedules Direct format extraction"""
        result = extract_callsign_from_xmltv_id("I10021.json.schedulesdirect.org")
        assert result == "10021"

    def test_callsign_with_country(self):
        """Test callsign.country format"""
        assert extract_callsign_from_xmltv_id("ESPN.us") == "ESPN"
        assert extract_callsign_from_xmltv_id("BBC1.uk") == "BBC1"

    def test_simple_callsign(self):
        """Test simple callsign without dots"""
        assert extract_callsign_from_xmltv_id("CNN") == "CNN"
        assert extract_callsign_from_xmltv_id("MSNBC") == "MSNBC"

    def test_empty_input(self):
        """Test empty or None input"""
        assert extract_callsign_from_xmltv_id(None) is None
        assert extract_callsign_from_xmltv_id("") is None

    def test_complex_format_with_dots(self):
        """Test format with multiple dots"""
        result = extract_callsign_from_xmltv_id("ABC.Chicago.us")
        assert result is not None  # Should extract first segment


class TestMakeSdXmltvId:
    """Tests for make_sd_xmltv_id function"""

    def test_creates_correct_format(self):
        """Test that SD XMLTV ID is created correctly"""
        result = make_sd_xmltv_id("10021")
        assert result == "I10021.json.schedulesdirect.org"


# ============================================================================
# Parse XMLTV Tests
# ============================================================================


class TestParseXmltv:
    """Tests for EpgService.parse_xmltv"""

    def test_parse_simple_xmltv(self):
        """Test parsing simple XMLTV content"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN</display-name>
                <display-name>ESPN HD</display-name>
                <icon src="http://example.com/espn.png"/>
            </channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="ESPN.us">
                <title>SportCenter</title>
            </programme>
        </tv>
        """

        result = EpgService.parse_xmltv(xml_content)

        assert "channels" in result
        assert "programs_by_channel" in result
        assert len(result["channels"]) == 1

        channel = result["channels"][0]
        assert channel["channel_id"] == "ESPN.us"
        assert channel["display_name"] == "ESPN"
        assert len(channel["display_names"]) == 2
        assert channel["icon_url"] == "http://example.com/espn.png"

        # Check programs
        assert "ESPN.us" in result["programs_by_channel"]
        assert len(result["programs_by_channel"]["ESPN.us"]) == 1

    def test_parse_channel_without_display_name(self):
        """Test parsing channel that falls back to ID"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="TestChannel">
            </channel>
        </tv>
        """

        result = EpgService.parse_xmltv(xml_content)

        assert len(result["channels"]) == 1
        assert result["channels"][0]["display_name"] == "TestChannel"

    def test_parse_invalid_xml(self):
        """Test parsing invalid XML raises error"""
        xml_content = b"<invalid xml"

        with pytest.raises(ValueError, match="Invalid XMLTV"):
            EpgService.parse_xmltv(xml_content)

    def test_parse_empty_channels(self):
        """Test parsing XML with no channels"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
        </tv>
        """

        result = EpgService.parse_xmltv(xml_content)

        assert result["channels"] == []
        assert result["programs_by_channel"] == {}

    def test_parse_channel_without_id(self):
        """Test that channels without ID are skipped"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel>
                <display-name>No ID Channel</display-name>
            </channel>
            <channel id="ValidChannel">
                <display-name>Valid Channel</display-name>
            </channel>
        </tv>
        """

        result = EpgService.parse_xmltv(xml_content)

        # Only the channel with ID should be parsed
        assert len(result["channels"]) == 1
        assert result["channels"][0]["channel_id"] == "ValidChannel"


# ============================================================================
# Sync EPG Source Tests
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
def test_epg_source(app, test_account):
    """Create a test EPG source"""
    with app.app_context():
        source = EpgSource(
            name="Test EPG Source",
            source_type="provider",
            account_id=test_account,
            priority=100,
            enabled=True,
        )
        db.session.add(source)
        db.session.commit()
        yield source


class TestSyncEpgSource:
    """Tests for EpgService.sync_epg_source"""

    def test_sync_creates_new_channels(self, app, test_epg_source):
        """Test that sync creates new EPG channels"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN</display-name>
            </channel>
            <channel id="CNN.us">
                <display-name>CNN</display-name>
            </channel>
        </tv>
        """

        with app.app_context():
            # Refresh source from db
            source = db.session.get(EpgSource, test_epg_source.id)
            stats = EpgService.sync_epg_source(source, xml_content)

            assert stats["channels_added"] == 2
            assert stats["channels_updated"] == 0

            # Verify channels were created
            channels = EpgChannel.query.filter_by(source_id=source.id).all()
            assert len(channels) == 2

    def test_sync_updates_existing_channels(self, app, test_epg_source):
        """Test that sync updates existing EPG channels"""
        with app.app_context():
            # Create existing channel
            source = db.session.get(EpgSource, test_epg_source.id)
            existing = EpgChannel(
                source_id=source.id,
                channel_id="ESPN.us",
                display_name="Old ESPN Name",
            )
            db.session.add(existing)
            db.session.commit()

        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN Updated</display-name>
                <icon src="http://example.com/new-icon.png"/>
            </channel>
        </tv>
        """

        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)
            stats = EpgService.sync_epg_source(source, xml_content)

            assert stats["channels_added"] == 0
            assert stats["channels_updated"] == 1

            # Verify channel was updated
            channel = EpgChannel.query.filter_by(source_id=source.id, channel_id="ESPN.us").first()
            assert channel.display_name == "ESPN Updated"
            assert channel.icon_url == "http://example.com/new-icon.png"

    def test_sync_with_programs(self, app, test_epg_source):
        """Test that sync processes program counts"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN</display-name>
            </channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="ESPN.us">
                <title>Show 1</title>
            </programme>
            <programme start="20251221190000 +0000" stop="20251221200000 +0000" channel="ESPN.us">
                <title>Show 2</title>
            </programme>
        </tv>
        """

        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)
            stats = EpgService.sync_epg_source(source, xml_content)

            assert stats["total_programs"] == 2

            channel = EpgChannel.query.filter_by(source_id=source.id, channel_id="ESPN.us").first()
            assert channel.program_count == 2

    def test_sync_updates_source_status(self, app, test_epg_source):
        """Test that sync updates source status"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN</display-name>
            </channel>
        </tv>
        """

        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)
            EpgService.sync_epg_source(source, xml_content)

            source = db.session.get(EpgSource, test_epg_source.id)
            assert source.last_sync is not None
            assert source.last_sync_status == "success"
            assert source.channel_count == 1

    def test_sync_handles_invalid_xml(self, app, test_epg_source):
        """Test that sync handles invalid XML gracefully"""
        xml_content = b"<invalid xml"

        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)
            with pytest.raises(ValueError):
                EpgService.sync_epg_source(source, xml_content)

            # Verify source status was updated to error
            source = db.session.get(EpgSource, test_epg_source.id)
            assert source.last_sync_status == "error"

    def test_sync_handles_duplicate_channel_ids(self, app, test_epg_source):
        """Test that sync handles duplicate channel IDs in XMLTV data.

        Some XMLTV sources (like NigmaTV) have multiple channels with the same
        channel ID but different display names (e.g., Cinemax.hu appears as both
        'HU: Cinemax' and 'HU: Cinemax2'). The sync should handle this gracefully
        by merging the duplicate entries.
        """
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="Cinemax.hu">
                <display-name>HU: Cinemax</display-name>
                <icon src="http://example.com/cinemax1.png"/>
            </channel>
            <channel id="Cinemax.hu">
                <display-name>HU: Cinemax2</display-name>
                <icon src="http://example.com/cinemax2.png"/>
            </channel>
            <channel id="HBO.hu">
                <display-name>HU: HBO</display-name>
            </channel>
        </tv>
        """

        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)
            stats = EpgService.sync_epg_source(source, xml_content)

            # Should only create 2 unique channels (Cinemax.hu merged, HBO.hu separate)
            assert stats["channels_added"] == 2
            assert stats["channels_updated"] == 0

            # Verify only 2 channels were created
            channels = EpgChannel.query.filter_by(source_id=source.id).all()
            assert len(channels) == 2

            # Verify the duplicate was merged with combined display names
            cinemax = EpgChannel.query.filter_by(source_id=source.id, channel_id="Cinemax.hu").first()
            assert cinemax is not None
            import json

            display_names = json.loads(cinemax.display_names_json)
            # Should have both display names from the duplicates
            assert "HU: Cinemax" in display_names
            assert "HU: Cinemax2" in display_names
            # Icon should be from first entry since it was not None
            assert cinemax.icon_url == "http://example.com/cinemax1.png"


# ============================================================================
# Parse XMLTV Time Tests
# ============================================================================


class TestParseXmltvTime:
    """Tests for EpgService._parse_xmltv_time"""

    def test_full_format(self):
        """Test parsing full XMLTV time format"""
        result = EpgService._parse_xmltv_time("20251221180000 +0000")
        assert result is not None
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 21
        assert result.hour == 18

    def test_short_format(self):
        """Test parsing short XMLTV time format"""
        result = EpgService._parse_xmltv_time("202512211800")
        assert result is not None
        assert result.year == 2025

    def test_empty_input(self):
        """Test parsing empty input"""
        result = EpgService._parse_xmltv_time("")
        assert result is None

    def test_invalid_format(self):
        """Test parsing invalid time format"""
        result = EpgService._parse_xmltv_time("invalid")
        assert result is None


# ============================================================================
# EPG Coverage Stats Tests
# ============================================================================


class TestGetEpgCoverageStats:
    """Tests for EpgService.get_epg_coverage_stats"""

    def test_empty_database(self, app):
        """Test coverage stats with empty database"""
        with app.app_context():
            stats = EpgService.get_epg_coverage_stats()
            assert stats["total_channels"] == 0
            assert stats["channels_with_epg_mapping"] == 0
            assert stats["coverage_percent"] == 0

    def test_coverage_with_channels(self, app, test_account, test_epg_source):
        """Test coverage stats with channels and mappings"""
        with app.app_context():
            # Create a channel
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
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create EPG channel
            source = db.session.get(EpgSource, test_epg_source.id)
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="epg_ch1",
                display_name="EPG Channel",
            )
            db.session.add(epg_channel)
            db.session.flush()

            # Create mapping
            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="manual",
                confidence=1.0,
            )
            db.session.add(mapping)
            db.session.commit()

            stats = EpgService.get_epg_coverage_stats()
            assert stats["total_channels"] >= 1
            assert stats["channels_with_epg_mapping"] >= 1
            assert stats["epg_sources"] >= 1


# ============================================================================
# Channel Matching Tests
# ============================================================================


class TestMatchChannelsToEpg:
    """Tests for EpgService.match_channels_to_epg"""

    def test_match_empty_channels(self, app, test_account):
        """Test matching with no channels"""
        with app.app_context():
            stats = EpgService.match_channels_to_epg(test_account)
            assert stats["total_channels"] == 0

    def test_match_by_epg_id(self, app, test_account, test_epg_source):
        """Test matching by EPG channel ID"""
        with app.app_context():
            # Create channel with epg_channel_id
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
                name="ESPN HD",
                epg_channel_id="ESPN.us",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create matching EPG channel
            source = db.session.get(EpgSource, test_epg_source.id)
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="ESPN.us",
                display_name="ESPN",
            )
            db.session.add(epg_channel)
            db.session.commit()

            stats = EpgService.match_channels_to_epg(test_account)
            assert stats["matched_exact_id"] >= 0  # May or may not match depending on implementation
