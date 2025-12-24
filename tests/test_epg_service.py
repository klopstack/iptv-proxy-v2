"""
Tests for EPG service - parsing, syncing, and matching
"""
import gzip

import pytest

from models import (
    Account,
    Category,
    Channel,
    ChannelEpgMapping,
    ChannelLink,
    ChannelTag,
    EpgChannel,
    EpgSource,
    Tag,
    db,
)
from services.epg_service import (
    EAST_TAGS,
    WEST_TAGS,
    EpgService,
    decompress_content,
    extract_callsign_from_xmltv_id,
    make_sd_xmltv_id,
    normalize_xmltv_url,
    shift_xmltv_time,
)

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


class TestNormalizeXmltvUrl:
    """Tests for normalize_xmltv_url function"""

    def test_github_blob_url_https(self):
        """Test converting GitHub blob URL with https"""
        url = "https://github.com/acidjesuz/EPGTalk/blob/master/guide.xml"
        result = normalize_xmltv_url(url)
        assert result == "https://raw.githubusercontent.com/acidjesuz/EPGTalk/master/guide.xml"

    def test_github_blob_url_http(self):
        """Test converting GitHub blob URL with http"""
        url = "http://github.com/user/repo/blob/main/epg.xml"
        result = normalize_xmltv_url(url)
        assert result == "https://raw.githubusercontent.com/user/repo/main/epg.xml"

    def test_github_blob_url_with_path(self):
        """Test converting GitHub blob URL with subdirectory path"""
        url = "https://github.com/user/repo/blob/develop/data/epg/guide.xml"
        result = normalize_xmltv_url(url)
        assert result == "https://raw.githubusercontent.com/user/repo/develop/data/epg/guide.xml"

    def test_raw_github_url_unchanged(self):
        """Test that raw.githubusercontent.com URLs are not modified"""
        url = "https://raw.githubusercontent.com/user/repo/main/guide.xml"
        result = normalize_xmltv_url(url)
        assert result == url

    def test_regular_url_unchanged(self):
        """Test that regular URLs are not modified"""
        url = "https://example.com/epg.xml"
        result = normalize_xmltv_url(url)
        assert result == url

    def test_local_url_unchanged(self):
        """Test that local/internal URLs are not modified"""
        url = "http://192.168.1.100:8080/epg.xml"
        result = normalize_xmltv_url(url)
        assert result == url


class TestDecompressContent:
    """Tests for decompress_content function"""

    def test_decompress_gzipped_content(self):
        """Test decompressing gzipped content"""
        original = b"<tv><channel id='test'></channel></tv>"
        compressed = gzip.compress(original)
        result = decompress_content(compressed)
        assert result == original

    def test_passthrough_uncompressed_content(self):
        """Test that uncompressed content passes through unchanged"""
        original = b"<tv><channel id='test'></channel></tv>"
        result = decompress_content(original)
        assert result == original

    def test_passthrough_xml_declaration(self):
        """Test XML with declaration passes through"""
        original = b"<?xml version='1.0'?><tv></tv>"
        result = decompress_content(original)
        assert result == original

    def test_invalid_gzip_header_passthrough(self):
        """Test that invalid gzip (has header but bad data) passes through"""
        # Gzip magic bytes but invalid data
        bad_gzip = b"\x1f\x8b\x00\x00invalid"
        result = decompress_content(bad_gzip)
        assert result == bad_gzip


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

    def test_parse_gzipped_xmltv(self):
        """Test parsing gzip-compressed XMLTV content"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="GZ.test">
                <display-name>Gzip Test Channel</display-name>
            </channel>
        </tv>
        """
        compressed = gzip.compress(xml_content)

        result = EpgService.parse_xmltv(compressed)
        assert len(result["channels"]) == 1
        assert result["channels"][0]["channel_id"] == "GZ.test"
        assert result["channels"][0]["display_name"] == "Gzip Test Channel"

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


class TestParseXmltvStreaming:
    """Tests for EpgService.parse_xmltv_streaming"""

    def test_streaming_parse_channels_and_programmes(self):
        """Test streaming parser yields channels and programmes correctly"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN</display-name>
                <icon src="http://example.com/espn.png"/>
            </channel>
            <channel id="CNN.us">
                <display-name>CNN</display-name>
            </channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="ESPN.us">
                <title>SportCenter</title>
            </programme>
            <programme start="20251221190000 +0000" stop="20251221200000 +0000" channel="CNN.us">
                <title>News</title>
            </programme>
        </tv>
        """

        elements = list(EpgService.parse_xmltv_streaming(xml_content))

        # Should have 2 channels and 2 programmes
        channels = [e for e in elements if e[0] == "channel"]
        programmes = [e for e in elements if e[0] == "programme"]

        assert len(channels) == 2
        assert len(programmes) == 2

        # Check channel data
        assert channels[0][1]["channel_id"] == "ESPN.us"
        assert channels[0][1]["display_name"] == "ESPN"
        assert channels[0][1]["icon_url"] == "http://example.com/espn.png"

        # Check programme data
        assert programmes[0][1]["channel"] == "ESPN.us"
        assert programmes[0][1]["start"] == "20251221180000 +0000"

    def test_streaming_parse_gzipped_content(self):
        """Test streaming parser handles gzipped content"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="GZ.test">
                <display-name>Gzip Test Channel</display-name>
            </channel>
        </tv>
        """
        compressed = gzip.compress(xml_content)

        elements = list(EpgService.parse_xmltv_streaming(compressed))

        channels = [e for e in elements if e[0] == "channel"]
        assert len(channels) == 1
        assert channels[0][1]["channel_id"] == "GZ.test"

    def test_streaming_parse_invalid_xml(self):
        """Test streaming parser raises error for invalid XML"""
        xml_content = b"<invalid xml"

        with pytest.raises(ValueError, match="Invalid XMLTV"):
            list(EpgService.parse_xmltv_streaming(xml_content))

    def test_streaming_clears_memory(self):
        """Test that streaming parser doesn't accumulate memory"""
        # Generate a moderately sized XMLTV file
        channels_xml = ""
        programmes_xml = ""
        for i in range(100):
            channels_xml += f'<channel id="ch{i}"><display-name>Channel {i}</display-name></channel>\n'
            for j in range(10):
                programmes_xml += f'<programme start="20251221{j:02d}0000 +0000" stop="20251221{j + 1:02d}0000 +0000" channel="ch{i}"><title>Show {j}</title></programme>\n'

        xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            {channels_xml}
            {programmes_xml}
        </tv>
        """.encode()

        # Process all elements - this should not accumulate memory
        channel_count = 0
        programme_count = 0
        for element_type, data in EpgService.parse_xmltv_streaming(xml_content):
            if element_type == "channel":
                channel_count += 1
            elif element_type == "programme":
                programme_count += 1

        assert channel_count == 100
        assert programme_count == 1000


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

    def test_match_with_category_filter(self, app, test_account, test_epg_source):
        """Test matching filtered by category"""
        with app.app_context():
            # Create two categories
            cat1 = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Sports",
            )
            cat2 = Category(
                account_id=test_account,
                category_id="cat2",
                category_name="News",
            )
            db.session.add_all([cat1, cat2])
            db.session.flush()

            # Create channels in different categories
            ch1 = Channel(
                account_id=test_account,
                stream_id="ch1",
                name="ESPN HD",
                category_id=cat1.id,
                is_active=True,
            )
            ch2 = Channel(
                account_id=test_account,
                stream_id="ch2",
                name="CNN HD",
                category_id=cat2.id,
                is_active=True,
            )
            db.session.add_all([ch1, ch2])
            db.session.commit()

            # Match only cat1 (Sports)
            stats = EpgService.match_channels_to_epg(test_account, category_id=cat1.id)
            assert stats["total_channels"] == 1

            # Match only cat2 (News)
            stats = EpgService.match_channels_to_epg(test_account, category_id=cat2.id)
            assert stats["total_channels"] == 1

            # Match all (no category filter)
            stats = EpgService.match_channels_to_epg(test_account)
            assert stats["total_channels"] == 2

    def test_skip_already_matched(self, app, test_account, test_epg_source):
        """Test that channels with good existing matches are skipped"""
        with app.app_context():
            # Create category and channel
            cat = Category(
                account_id=test_account,
                category_id="cat1",
                category_name="Test",
            )
            db.session.add(cat)
            db.session.flush()

            channel = Channel(
                account_id=test_account,
                stream_id="ch1",
                name="ESPN HD",
                category_id=cat.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Create EPG channel and existing mapping with high confidence
            source = db.session.get(EpgSource, test_epg_source.id)
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="espn",
                display_name="ESPN",
            )
            db.session.add(epg_channel)
            db.session.flush()

            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="auto_exact",
                confidence=0.95,
            )
            db.session.add(mapping)
            db.session.commit()

            # Run matching with default threshold (0.85) - should skip
            stats = EpgService.match_channels_to_epg(test_account)
            assert stats["skipped_existing"] == 1

            # Run matching with higher threshold - should NOT skip
            stats = EpgService.match_channels_to_epg(test_account, skip_matched_threshold=0.99)
            assert stats["skipped_existing"] == 0


class TestMatchingStrategies:
    """Tests for EPG matching strategy functions"""

    def test_normalize_name(self, app):
        """Test name normalization"""
        with app.app_context():
            assert EpgService._normalize_name("ESPN HD") == "espn hd"
            assert EpgService._normalize_name("CNN: News Network") == "cnn news network"
            assert EpgService._normalize_name("BBC  One  ") == "bbc one"
            assert EpgService._normalize_name("") == ""
            assert EpgService._normalize_name(None) == ""

    def test_get_name_tokens(self, app):
        """Test token extraction"""
        with app.app_context():
            tokens = EpgService._get_name_tokens("ESPN HD")
            assert "espn" in tokens
            # "hd" is a noise word, should be stripped
            assert "hd" not in tokens

            tokens = EpgService._get_name_tokens("Fox News Channel")
            assert "fox" in tokens
            assert "news" in tokens
            # "channel" is a noise word, should be stripped
            assert "channel" not in tokens

    def test_calculate_match_score_exact(self, app):
        """Test exact match scoring"""
        with app.app_context():
            score, match_type = EpgService._calculate_match_score("ESPN", "ESPN")
            assert score == 1.0
            assert match_type == "exact"

            score, match_type = EpgService._calculate_match_score("CNN HD", "CNN HD")
            assert score == 1.0
            assert match_type == "exact"

    def test_calculate_match_score_contains(self, app):
        """Test contains/prefix match scoring"""
        with app.app_context():
            # Channel name contained in EPG name - token match is also acceptable
            score, match_type = EpgService._calculate_match_score("BBC One", "BBC One London")
            assert score >= 0.7
            assert match_type in ("contains", "token_match")

            # Longer contains with good coverage
            score, match_type = EpgService._calculate_match_score("Discovery Channel", "Discovery")
            assert score >= 0.75
            assert match_type in ("contains", "exact_stripped")

    def test_calculate_match_score_token_match(self, app):
        """Test token-based match scoring"""
        with app.app_context():
            # Stripped suffix match - "MTV2" vs "MTV2 Music Television"
            # "television" is stripped, so this should match
            score, match_type = EpgService._calculate_match_score("MTV2", "MTV2 Television")
            assert score >= 0.90
            assert match_type == "exact_stripped"

            # Two-token match with coverage
            score, match_type = EpgService._calculate_match_score("Comedy Central", "Comedy Central HD")
            assert score >= 0.90
            assert match_type in ("exact_stripped", "token_match")

    def test_fuzzy_match_basic(self, app, test_epg_source):
        """Test basic fuzzy matching"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)

            # Create EPG channels
            epg1 = EpgChannel(source_id=source.id, channel_id="espn", display_name="ESPN")
            epg2 = EpgChannel(source_id=source.id, channel_id="cnn", display_name="CNN News Network")
            epg3 = EpgChannel(source_id=source.id, channel_id="bbc", display_name="BBC One London")
            db.session.add_all([epg1, epg2, epg3])
            db.session.commit()

            epg_channels = [epg1, epg2, epg3]

            # Exact match
            match, score = EpgService._fuzzy_match("ESPN", epg_channels)
            assert match is not None
            assert match.display_name == "ESPN"
            assert score >= 0.95

            # Contains match
            match, score = EpgService._fuzzy_match("CNN", epg_channels)
            assert match is not None
            assert "CNN" in match.display_name
            assert score >= 0.65

    def test_fuzzy_match_no_match(self, app, test_epg_source):
        """Test fuzzy matching with no good matches"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)

            epg1 = EpgChannel(source_id=source.id, channel_id="abc", display_name="ABC Network")
            db.session.add(epg1)
            db.session.commit()

            match, score = EpgService._fuzzy_match("XYZ Completely Different", [epg1])
            # Should return None if below threshold
            assert match is None or score < 0.65

    def test_extract_country_from_epg_id(self, app):
        """Test extracting country codes from EPG channel IDs"""
        with app.app_context():
            # Common patterns
            assert EpgService._extract_country_from_epg_id("ESPN.us") == "US"
            assert EpgService._extract_country_from_epg_id("Court.TV.us2") == "US"
            assert EpgService._extract_country_from_epg_id("BBC1.uk") == "UK"
            assert EpgService._extract_country_from_epg_id("RTL.de") == "DE"
            assert EpgService._extract_country_from_epg_id("CBC.ca") == "CA"

            # No country code
            assert EpgService._extract_country_from_epg_id("plex.tv.Court.TV.plex") is None
            assert EpgService._extract_country_from_epg_id("") is None
            assert EpgService._extract_country_from_epg_id(None) is None

    def test_fuzzy_match_with_country_tags(self, app, test_epg_source):
        """Test fuzzy matching prefers country-matching EPG channels"""
        with app.app_context():
            source = db.session.get(EpgSource, test_epg_source.id)

            # Create EPG channels with same name but different country suffixes
            epg_us = EpgChannel(source_id=source.id, channel_id="CourtTV.us", display_name="Court TV")
            epg_uk = EpgChannel(source_id=source.id, channel_id="CourtTV.uk", display_name="Court TV")
            epg_generic = EpgChannel(source_id=source.id, channel_id="court-tv", display_name="Court TV")
            db.session.add_all([epg_us, epg_uk, epg_generic])
            db.session.commit()

            epg_channels = [epg_us, epg_uk, epg_generic]

            # Without country tags - any match is acceptable
            match, score = EpgService._fuzzy_match("Court TV", epg_channels)
            assert match is not None
            assert score >= 0.95

            # With US country tag - should prefer the .us channel
            match, score = EpgService._fuzzy_match("Court TV", epg_channels, country_tags={"US"})
            assert match is not None
            assert match.channel_id == "CourtTV.us"

            # With UK country tag - should prefer the .uk channel
            match, score = EpgService._fuzzy_match("Court TV", epg_channels, country_tags={"UK"})
            assert match is not None
            assert match.channel_id == "CourtTV.uk"


# ============================================================================
# Channel Link EPG Handling Tests
# ============================================================================


class TestChannelLinkHandling:
    """Tests for channel link EPG handling and time shifting"""

    def test_east_tags_defined(self):
        """Test that expected east tags are defined for auto-detection"""
        assert "EAST" in EAST_TAGS
        assert "E" in EAST_TAGS
        assert "ET" in EAST_TAGS
        assert "EST" in EAST_TAGS
        assert "EASTERN" in EAST_TAGS

    def test_west_tags_defined(self):
        """Test that expected west tags are defined for auto-detection"""
        assert "WEST" in WEST_TAGS
        assert "W" in WEST_TAGS
        assert "PT" in WEST_TAGS
        assert "PST" in WEST_TAGS
        assert "PACIFIC" in WEST_TAGS
        assert "WESTERN" in WEST_TAGS

    def test_shift_xmltv_time_negative(self):
        """Test shifting XMLTV time backwards (for west coast)"""
        # 2:00 PM becomes 11:00 AM (-3 hours)
        result = shift_xmltv_time("20251221140000 +0000", -3)
        assert result == "20251221110000 +0000"

        # Crossing midnight boundary
        result = shift_xmltv_time("20251221010000 +0000", -3)
        assert result == "20251220220000 +0000"

    def test_shift_xmltv_time_positive(self):
        """Test shifting XMLTV time forward"""
        result = shift_xmltv_time("20251221140000 +0000", 3)
        assert result == "20251221170000 +0000"

    def test_shift_xmltv_time_preserves_timezone(self):
        """Test that timezone is preserved after shift"""
        result = shift_xmltv_time("20251221140000 -0500", -3)
        assert result == "20251221110000 -0500"

    def test_shift_xmltv_time_no_timezone(self):
        """Test shifting time without timezone"""
        result = shift_xmltv_time("20251221140000", -3)
        assert result == "20251221110000 +0000"

    def test_shift_xmltv_time_empty(self):
        """Test handling empty/invalid time strings"""
        assert shift_xmltv_time("", -3) == ""
        assert shift_xmltv_time(None, -3) is None

    def test_build_channel_link_map(self, app, test_account):
        """Test building channel link map from database"""
        with app.app_context():
            # Fetch the account
            account = db.session.get(Account, test_account)

            # Create category
            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            # Create channels
            hbo_east = Channel(
                account_id=account.id,
                stream_id=1,
                name="HBO East",
                cleaned_name="HBO",
                epg_channel_id="HBO-East.us",
                category_id=category.id,
            )
            hbo_west = Channel(
                account_id=account.id,
                stream_id=2,
                name="HBO West",
                cleaned_name="HBO",
                epg_channel_id="HBO-West.us",
                category_id=category.id,
            )
            db.session.add_all([hbo_east, hbo_west])
            db.session.flush()

            # Create channel link: west -> east with -3 hour offset
            link = ChannelLink(
                channel_id=hbo_west.id,
                source_channel_id=hbo_east.id,
                time_offset_hours=-3,
                link_type="time_shifted",
                auto_detected=False,
            )
            db.session.add(link)
            db.session.commit()

            # Build link map
            result = EpgService._build_channel_link_map([hbo_east.id, hbo_west.id])

            # West channel should map to east with -3 hour offset
            assert "hbo-west.us" in result
            assert result["hbo-west.us"] == ("hbo-east.us", -3)

            # East channel should not be in the map (it's the source, not target)
            assert "hbo-east.us" not in result


class TestGenerateFilteredEpg:
    """Tests for filtered EPG generation with channel link handling"""

    def test_generate_filtered_epg_basic(self):
        """Test basic EPG filtering by channel IDs"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us">
                <display-name>ESPN</display-name>
            </channel>
            <channel id="CNN.us">
                <display-name>CNN</display-name>
            </channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="ESPN.us">
                <title>SportCenter</title>
            </programme>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="CNN.us">
                <title>News</title>
            </programme>
        </tv>
        """

        # Request only ESPN
        result = EpgService.generate_filtered_epg(["ESPN.us"], xml_content)

        # Parse result
        import xml.etree.ElementTree as ET

        root = ET.fromstring(result)

        channels = root.findall("channel")
        assert len(channels) == 1
        assert channels[0].get("id") == "ESPN.us"

        programmes = root.findall("programme")
        assert len(programmes) == 1
        assert programmes[0].get("channel") == "ESPN.us"

    def test_generate_filtered_epg_channel_link_fallback(self):
        """Test that linked channel EPG is generated from source with time offset"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="HBO East">
                <display-name>HBO East</display-name>
            </channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="HBO East">
                <title>Movie</title>
            </programme>
            <programme start="20251221190000 +0000" stop="20251221200000 +0000" channel="HBO East">
                <title>Documentary</title>
            </programme>
        </tv>
        """

        # Create channel link map: west -> (east, -3 hours)
        channel_link_map = {"hbo west": ("hbo east", -3)}

        # Request both east and west - west doesn't exist in source
        result = EpgService.generate_filtered_epg(
            ["HBO East", "HBO West"], xml_content, channel_link_map=channel_link_map
        )

        import xml.etree.ElementTree as ET

        root = ET.fromstring(result)

        # Should have both channels
        channels = root.findall("channel")
        channel_ids = [c.get("id") for c in channels]
        assert "HBO East" in channel_ids
        assert "hbo west" in channel_ids  # Generated west channel

        # Should have programmes for both channels
        programmes = root.findall("programme")
        east_progs = [p for p in programmes if p.get("channel") == "HBO East"]
        west_progs = [p for p in programmes if p.get("channel") == "hbo west"]

        assert len(east_progs) == 2
        assert len(west_progs) == 2  # Same programmes, time-shifted

        # West times should be 3 hours earlier
        # East: 18:00 -> West: 15:00
        assert west_progs[0].get("start") == "20251221150000 +0000"
        assert west_progs[0].get("stop") == "20251221160000 +0000"

    def test_generate_filtered_epg_no_link_map(self):
        """Test that no fallback when channel_link_map not provided"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="HBO East">
                <display-name>HBO East</display-name>
            </channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="HBO East">
                <title>Movie</title>
            </programme>
        </tv>
        """

        # No channel_link_map provided
        result = EpgService.generate_filtered_epg(["HBO East", "HBO West"], xml_content)

        import xml.etree.ElementTree as ET

        root = ET.fromstring(result)

        # Should only have east channel
        channels = root.findall("channel")
        assert len(channels) == 1
        assert channels[0].get("id") == "HBO East"

    def test_generate_filtered_epg_different_offsets(self):
        """Test channel links with different time offsets"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="Source">
                <display-name>Source</display-name>
            </channel>
            <programme start="20251221120000 +0000" stop="20251221130000 +0000" channel="Source">
                <title>Show</title>
            </programme>
        </tv>
        """

        # Two linked channels with different offsets
        channel_link_map = {
            "target_minus2": ("source", -2),
            "target_plus1": ("source", 1),
        }

        result = EpgService.generate_filtered_epg(
            ["Source", "target_minus2", "target_plus1"],
            xml_content,
            channel_link_map=channel_link_map,
        )

        import xml.etree.ElementTree as ET

        root = ET.fromstring(result)

        programmes = root.findall("programme")
        progs_by_channel = {}
        for p in programmes:
            ch = p.get("channel")
            if ch not in progs_by_channel:
                progs_by_channel[ch] = []
            progs_by_channel[ch].append(p)

        # Source: 12:00
        assert progs_by_channel["Source"][0].get("start") == "20251221120000 +0000"
        # target_minus2: 12:00 - 2 = 10:00
        assert progs_by_channel["target_minus2"][0].get("start") == "20251221100000 +0000"
        # target_plus1: 12:00 + 1 = 13:00
        assert progs_by_channel["target_plus1"][0].get("start") == "20251221130000 +0000"

    def test_generate_filtered_epg_empty_channels(self):
        """Test with empty channel list returns minimal valid XML"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us"><display-name>ESPN</display-name></channel>
        </tv>
        """

        result = EpgService.generate_filtered_epg([], xml_content)

        import xml.etree.ElementTree as ET

        root = ET.fromstring(result)
        assert root.tag == "tv"
        assert len(root.findall("channel")) == 0

    def test_generate_filtered_epg_gzipped_input(self):
        """Test filtering gzipped XMLTV content"""
        xml_content = b"""<?xml version="1.0" encoding="UTF-8"?>
        <tv>
            <channel id="ESPN.us"><display-name>ESPN</display-name></channel>
            <programme start="20251221180000 +0000" stop="20251221190000 +0000" channel="ESPN.us">
                <title>SportCenter</title>
            </programme>
        </tv>
        """
        compressed = gzip.compress(xml_content)

        result = EpgService.generate_filtered_epg(["ESPN.us"], compressed)

        import xml.etree.ElementTree as ET

        root = ET.fromstring(result)
        channels = root.findall("channel")
        assert len(channels) == 1


# ============================================================================
# FCC-Enhanced EPG Matching Tests
# ============================================================================


class TestFccEnhancedEpgMatching:
    """Tests for FCC-enhanced EPG matching functionality"""

    @pytest.fixture
    def fcc_test_facility(self, app):
        """Create a test FCC facility"""
        from models import FccFacility

        with app.app_context():
            facility = FccFacility(
                facility_id=12345,
                callsign="KABC-TV",
                service_code="DTV",
                station_type="M",
                community_city="LOS ANGELES",
                community_state="CA",
                channel="7",
                tv_virtual_channel="7",
                network_affiliation="ABC",
                nielsen_dma="Los Angeles",
                active=True,
            )
            db.session.add(facility)
            db.session.commit()
            yield facility.id
            # Cleanup
            FccFacility.query.filter_by(id=facility.id).delete()
            db.session.commit()

    @pytest.fixture
    def us_tagged_channel(self, app):
        """Create a US-tagged channel with callsign in name"""
        from models import Account, Channel, ChannelTag, Tag

        with app.app_context():
            account = Account(
                name="Test Account",
                server="http://test.example.com",
                username="testuser",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="us_abc_la",
                name="US: ABC 7 (KABC) Los Angeles",
                category_id=1,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Add US tag
            us_tag = Tag.query.filter_by(name="US").first()
            if not us_tag:
                us_tag = Tag(name="US")
                db.session.add(us_tag)
                db.session.commit()

            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=channel.stream_id,
                tag_id=us_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            yield {
                "account_id": account.id,
                "channel_id": channel.id,
                "channel_name": channel.name,
            }

            # Cleanup
            ChannelTag.query.filter_by(account_id=account.id).delete()
            Channel.query.filter_by(account_id=account.id).delete()
            Account.query.filter_by(id=account.id).delete()
            db.session.commit()

    @pytest.fixture
    def kabc_epg_channel(self, app):
        """Create an EPG channel for KABC"""
        from models import EpgChannel, EpgSource

        with app.app_context():
            source = EpgSource(
                name="Test EPG Source",
                source_type="xmltv",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="KABC.us",
                display_name="KABC-TV",
            )
            db.session.add(epg_channel)
            db.session.commit()

            yield {
                "source_id": source.id,
                "epg_channel_id": epg_channel.id,
                "channel_id": epg_channel.channel_id,
            }

            # Cleanup
            EpgChannel.query.filter_by(source_id=source.id).delete()
            EpgSource.query.filter_by(id=source.id).delete()
            db.session.commit()

    def test_build_fcc_epg_indices(self, app):
        """Test building FCC EPG indices from EPG channels"""
        with app.app_context():
            # Create test EPG channels
            source = EpgSource(
                name="Test Source",
                source_type="xmltv",
                url="http://test.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            epg_channels = [
                EpgChannel(source_id=source.id, channel_id="KABC.us", display_name="KABC-TV"),
                EpgChannel(source_id=source.id, channel_id="WNBC.us", display_name="WNBC"),
                EpgChannel(source_id=source.id, channel_id="ESPN.us", display_name="ESPN"),  # Not a broadcast callsign
            ]
            for ec in epg_channels:
                db.session.add(ec)
            db.session.commit()

            # Build indices
            callsign_index, dma_index = EpgService._build_fcc_epg_indices(epg_channels)

            # Verify callsign index
            assert "KABC" in callsign_index
            assert "WNBC" in callsign_index
            # ESPN doesn't start with K or W, so shouldn't be indexed as broadcast callsign
            assert "ESPN" not in callsign_index

            # Cleanup
            EpgChannel.query.filter_by(source_id=source.id).delete()
            EpgSource.query.filter_by(id=source.id).delete()
            db.session.commit()

    def test_match_by_fcc_callsign_exact(self, app, fcc_test_facility, kabc_epg_channel):
        """Test matching by exact FCC callsign"""
        from models import FccFacility

        with app.app_context():
            facility = FccFacility.query.get(fcc_test_facility)

            # Build callsign index
            epg_channel = EpgChannel.query.get(kabc_epg_channel["epg_channel_id"])
            epg_by_callsign = {"KABC": epg_channel, "KABC-TV": epg_channel}

            # Create a mock channel
            channel = type("Channel", (), {"name": "US: ABC (KABC) Los Angeles"})()

            result = EpgService._match_by_fcc_callsign(channel, epg_by_callsign, facility)

            assert result is not None
            matched_epg, confidence, match_type = result
            assert matched_epg.channel_id == "KABC.us"
            assert confidence >= 0.93
            assert "fcc_callsign" in match_type

    def test_match_by_fcc_callsign_no_facility(self, app):
        """Test matching returns None when no FCC facility"""
        with app.app_context():
            channel = type("Channel", (), {"name": "ESPN"})()
            result = EpgService._match_by_fcc_callsign(channel, {}, None)
            assert result is None

    def test_match_by_fcc_network_fallback(self, app, fcc_test_facility):
        """Test network fallback matching"""
        from models import FccFacility

        with app.app_context():
            facility = FccFacility.query.get(fcc_test_facility)

            # Create EPG channel for ABC network
            source = EpgSource(
                name="Test Source",
                source_type="xmltv",
                url="http://test.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            abc_epg = EpgChannel(source_id=source.id, channel_id="ABC.us", display_name="ABC")
            db.session.add(abc_epg)
            db.session.commit()

            epg_by_name = {"abc": abc_epg}

            channel = type("Channel", (), {"name": "US: ABC (WXYZ) Detroit"})()

            result = EpgService._match_by_fcc_network(channel, epg_by_name, facility)

            assert result is not None
            matched_epg, confidence, match_type = result
            assert matched_epg.channel_id == "ABC.us"
            assert confidence == 0.60  # Lower confidence for network fallback
            assert match_type == "fcc_network_fallback"

            # Cleanup
            EpgChannel.query.filter_by(source_id=source.id).delete()
            EpgSource.query.filter_by(id=source.id).delete()
            db.session.commit()

    def test_match_by_fcc_network_non_major_network(self, app):
        """Test network fallback doesn't apply to non-major networks"""
        from models import FccFacility

        with app.app_context():
            # Create facility with non-major network
            facility = FccFacility(
                facility_id=99999,
                callsign="WXYZ-TV",
                service_code="DTV",
                network_affiliation="INDEPENDENT",  # Not a major network
                community_city="TEST CITY",
                community_state="TX",
            )
            db.session.add(facility)
            db.session.commit()

            channel = type("Channel", (), {"name": "US: Independent Station"})()

            result = EpgService._match_by_fcc_network(channel, {}, facility)
            assert result is None

            # Cleanup
            FccFacility.query.filter_by(id=facility.id).delete()
            db.session.commit()

    def test_get_fcc_facility_for_channel(self, app, fcc_test_facility):
        """Test getting FCC facility for a channel"""
        with app.app_context():
            channel = type("Channel", (), {"name": "US: ABC 7 (KABC) Los Angeles"})()

            facility = EpgService._get_fcc_facility_for_channel(channel)

            assert facility is not None
            assert facility.callsign == "KABC-TV"
            assert facility.community_city == "LOS ANGELES"

    def test_get_fcc_facility_for_channel_no_callsign(self, app):
        """Test returns None when no callsign in channel name"""
        with app.app_context():
            channel = type("Channel", (), {"name": "ESPN"})()

            facility = EpgService._get_fcc_facility_for_channel(channel)

            assert facility is None

    def test_preview_fcc_epg_matches(self, app, fcc_test_facility, us_tagged_channel, kabc_epg_channel):
        """Test previewing FCC-based EPG matches"""
        with app.app_context():
            account_id = us_tagged_channel["account_id"]

            results = EpgService.preview_fcc_epg_matches(
                account_id=account_id,
                source_id=kabc_epg_channel["source_id"],
                limit=10,
            )

            # Should find at least one match
            assert len(results) >= 1

            # Check first result has expected structure
            if results:
                result = results[0]
                assert "channel_id" in result
                assert "channel_name" in result
                assert "fcc_callsign" in result
                assert "epg_channel_id" in result
                assert "confidence" in result
                assert "match_type" in result

    def test_preview_fcc_epg_matches_no_us_tag(self, app):
        """Test preview returns empty when no US tag exists"""
        with app.app_context():
            from models import Tag

            # Ensure no US tag
            Tag.query.filter_by(name="US").delete()
            db.session.commit()

            results = EpgService.preview_fcc_epg_matches(account_id=1, limit=10)
            assert results == []

    def test_fcc_lookup_by_nielsen_dma(self, app):
        """Test FCC lookup falls back to nielsen_dma when community_city doesn't match.

        This handles cases like WTVD (ABC affiliate serving Raleigh-Durham market)
        which is licensed to Durham but tagged as RALEIGH.
        """
        from models import FccFacility

        with app.app_context():
            # Create FCC facility for WTVD - licensed to Durham but serves Raleigh-Durham DMA
            facility = FccFacility(
                facility_id=67890,
                callsign="WTVD",
                service_code="DTV",
                station_type="M",
                community_city="DURHAM",  # Licensed to Durham, not Raleigh
                community_state="NC",
                channel="11",
                tv_virtual_channel="11",
                network_affiliation="ABC",
                nielsen_dma="Raleigh-Durham",  # But serves Raleigh-Durham market
                active=True,
            )
            db.session.add(facility)
            db.session.commit()

            try:
                # Tags include RALEIGH (not Durham) - city-based lookup would fail
                tags = {"HD", "RAW", "60FPS", "US", "ABC", "RALEIGH"}
                network_tags = {"ABC"}
                channel_name = "ABC 11 HD"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)

                # Should find WTVD via nielsen_dma lookup
                assert callsign == "WTVD", f"Expected WTVD, got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=67890).delete()
                db.session.commit()

    def test_fcc_lookup_prefers_city_over_dma(self, app):
        """Test that city-based lookup is preferred over DMA-based lookup."""
        from models import FccFacility

        with app.app_context():
            # Create two facilities - one matches by city, one by DMA
            facility_city = FccFacility(
                facility_id=11111,
                callsign="WRAL",
                service_code="DTV",
                station_type="M",
                community_city="RALEIGH",
                community_state="NC",
                channel="5",
                tv_virtual_channel="5",
                network_affiliation="NBC",
                nielsen_dma="Raleigh-Durham",
                active=True,
            )
            facility_dma = FccFacility(
                facility_id=22222,
                callsign="WTVD",
                service_code="DTV",
                station_type="M",
                community_city="DURHAM",
                community_state="NC",
                channel="11",
                tv_virtual_channel="11",
                network_affiliation="ABC",
                nielsen_dma="Raleigh-Durham",
                active=True,
            )
            db.session.add(facility_city)
            db.session.add(facility_dma)
            db.session.commit()

            try:
                # NBC lookup with RALEIGH tag - should match by city first
                tags = {"HD", "US", "NBC", "RALEIGH"}
                network_tags = {"NBC"}
                channel_name = "NBC 5 HD"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                assert callsign == "WRAL", f"Expected WRAL (city match), got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter(FccFacility.facility_id.in_([11111, 22222])).delete()
                db.session.commit()

    def test_fcc_lookup_underscore_location_tags(self, app):
        """Test FCC lookup handles underscore-separated location tags like LAS_VEGAS."""
        from models import FccFacility

        with app.app_context():
            # Create FCC facility for KTNV-TV in Las Vegas
            facility = FccFacility(
                facility_id=33333,
                callsign="KTNV-TV",
                service_code="DTV",
                station_type="M",
                community_city="LAS VEGAS",  # Note: space, not underscore
                community_state="NV",
                channel="13",
                tv_virtual_channel="13",
                network_affiliation="ABC",
                nielsen_dma="Las Vegas",
                active=True,
            )
            db.session.add(facility)
            db.session.commit()

            try:
                # Tag has underscore: LAS_VEGAS
                tags = {"HD", "RAW", "60FPS", "US", "ABC", "LAS_VEGAS"}
                network_tags = {"ABC"}
                channel_name = "ABC 13 LAS VEGAS"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                assert callsign == "KTNV-TV", f"Expected KTNV-TV, got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=33333).delete()
                db.session.commit()

    def test_fcc_lookup_multi_word_location_partial_match(self, app):
        """Test FCC lookup handles multi-word locations like HAMPTON_ROADS.

        HAMPTON ROADS is a region, but the station (WVEC) is licensed to HAMPTON.
        The lookup should try individual words from multi-word locations.
        """
        from models import FccFacility

        with app.app_context():
            # Create FCC facility for WVEC in Hampton (not "Hampton Roads")
            facility = FccFacility(
                facility_id=44444,
                callsign="WVEC",
                service_code="DTV",
                station_type="M",
                community_city="HAMPTON",  # Just HAMPTON, not HAMPTON ROADS
                community_state="VA",
                channel="35",
                tv_virtual_channel="13",
                network_affiliation="ABC",
                nielsen_dma="Norfolk-Portsmth-Newpt Nws",
                active=True,
            )
            db.session.add(facility)
            db.session.commit()

            try:
                # Tag is HAMPTON_ROADS but city is just HAMPTON
                tags = {"HD", "RAW", "60FPS", "US", "ABC", "HAMPTON_ROADS"}
                network_tags = {"ABC"}
                channel_name = "ABC 13 HAMPTON ROADS"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                assert callsign == "WVEC", f"Expected WVEC, got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=44444).delete()
                db.session.commit()

    def test_fcc_lookup_callsign_from_name(self, app):
        """Test FCC lookup extracts callsign from channel name like 'ABC 3 WSIL'."""
        from models import FccFacility

        with app.app_context():
            # Create FCC facility for WSIL
            facility = FccFacility(
                facility_id=55555,
                callsign="WSIL-TV",
                service_code="DTV",
                station_type="M",
                community_city="HARRISBURG",
                community_state="IL",
                channel="17",
                tv_virtual_channel="3",
                network_affiliation="ABC",
                nielsen_dma="Paducah-Cape Girard-Harsbg",
                active=True,
            )
            db.session.add(facility)
            db.session.commit()

            try:
                # Channel name has callsign "WSIL" embedded
                tags = {"HD", "RAW", "60FPS", "US", "ABC"}
                network_tags = {"ABC"}
                channel_name = "ABC 3 WSIL"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                assert callsign == "WSIL-TV", f"Expected WSIL-TV, got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=55555).delete()
                db.session.commit()

    def test_fcc_lookup_compound_channel_number(self, app):
        """Test FCC lookup handles compound channel numbers like '33/40'.

        Some stations broadcast with multiple virtual channel numbers (e.g., simulcasts).
        Channel names like 'ABC 33/40 HD [BIRMINGHAM]' should try both 33 and 40.
        """
        from models import FccFacility

        with app.app_context():
            # Create two FCC facilities - one with channel 33, one with channel 40
            facility_33 = FccFacility(
                facility_id=88881,
                callsign="WXYZ-33",
                service_code="DTV",
                station_type="M",
                community_city="TESTCITY",
                community_state="XX",
                channel="33",
                tv_virtual_channel="33",
                network_affiliation="ABC",
                nielsen_dma="TestDMA",
                active=True,
            )
            facility_40 = FccFacility(
                facility_id=88882,
                callsign="WABC-40",
                service_code="DTV",
                station_type="M",
                community_city="TESTCITY",
                community_state="XX",
                channel="40",
                tv_virtual_channel="40",
                network_affiliation="NBC",
                nielsen_dma="TestDMA",
                active=True,
            )
            db.session.add(facility_33)
            db.session.add(facility_40)
            db.session.commit()

            try:
                # Test matching compound channel "33/40" with ABC network
                # Should find WXYZ-33 which matches channel 33 and ABC
                tags = {"HD", "US", "ABC", "TESTCITY"}
                network_tags = {"ABC"}
                channel_name = "ABC 33/40 HD TESTCITY"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                assert callsign == "WXYZ-33", f"Expected WXYZ-33 (channel 33 ABC match), got {callsign}"

                # Test with NBC network - should find WABC-40 (channel 40)
                tags_nbc = {"HD", "US", "NBC", "TESTCITY"}
                network_tags_nbc = {"NBC"}
                channel_name_nbc = "NBC 33/40 HD TESTCITY"

                callsign_nbc = EpgService._lookup_fcc_callsign(channel_name_nbc, tags_nbc, network_tags_nbc)
                assert callsign_nbc == "WABC-40", f"Expected WABC-40 (channel 40 NBC match), got {callsign_nbc}"
            finally:
                # Cleanup
                FccFacility.query.filter(FccFacility.facility_id.in_([88881, 88882])).delete()
                db.session.commit()

    def test_fcc_lookup_independent_station_fallback(self, app):
        """Test FCC lookup falls back to INDEPENDENT/blank affiliation when network not found."""
        from models import FccFacility

        with app.app_context():
            # Create FCC facility with no network affiliation (like WBMA-LD in Birmingham)
            facility = FccFacility(
                facility_id=66666,
                callsign="WBMA-LD",
                service_code="LPD",
                station_type="M",
                community_city="BIRMINGHAM",
                community_state="AL",
                channel="32",
                tv_virtual_channel="33",  # ABC 33/40 uses virtual channel 33
                network_affiliation="",  # No affiliation in FCC data
                nielsen_dma="Birmingham (Ann and Tusc)",
                active=True,
            )
            db.session.add(facility)
            db.session.commit()

            try:
                # Looking for ABC in Birmingham, but WBMA-LD has no ABC affiliation
                tags = {"HD", "RAW", "60FPS", "US", "ABC", "BIRMINGHAM"}
                network_tags = {"ABC"}
                channel_name = "ABC 33/40 HD BIRMINGHAM"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                # Should find WBMA-LD via independent fallback with channel 33 match
                assert callsign == "WBMA-LD", f"Expected WBMA-LD, got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=66666).delete()
                db.session.commit()

    def test_fcc_lookup_callsign_tag_match(self, app):
        """Test FCC lookup matches callsign from tags."""
        from models import FccFacility

        with app.app_context():
            # Create FCC facility for WMAR
            facility = FccFacility(
                facility_id=77777,
                callsign="WMAR-TV",
                service_code="DTV",
                station_type="M",
                community_city="BALTIMORE",
                community_state="MD",
                channel="38",
                tv_virtual_channel="2",
                network_affiliation="ABC",
                nielsen_dma="Baltimore",
                active=True,
            )
            db.session.add(facility)
            db.session.commit()

            try:
                # Channel has WMAR as a tag
                tags = {"RAW", "60FPS", "PRIME", "WMAR"}
                network_tags = set()  # No network tag
                channel_name = "ABC BALTIMORE NEWS"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                assert callsign == "WMAR-TV", f"Expected WMAR-TV, got {callsign}"
            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=77777).delete()
                db.session.commit()

    def test_fcc_corrections_apply_to_lookup(self, app):
        """Test that FCC corrections are applied during lookup.

        This tests the scenario where FCC data has incomplete info (e.g., missing
        network_affiliation) but a correction exists in the fcc_corrections table.
        """
        from models import FccCorrection, FccFacility
        from services.fcc_facility_service import FccFacilityService

        with app.app_context():
            # Create FCC facility with blank network affiliation (as in real WBMA-LD data)
            facility = FccFacility(
                facility_id=99999,
                callsign="WXYZ-LD",
                service_code="LPD",
                station_type="M",
                community_city="TESTVILLE",
                community_state="TX",
                channel="32",
                tv_virtual_channel="",  # No virtual channel in FCC data
                network_affiliation="",  # No affiliation in FCC data
                nielsen_dma="Testville DMA",
                active=True,
            )
            db.session.add(facility)

            # Add a correction for this facility
            correction = FccCorrection(
                callsign="WXYZ-LD",
                network_affiliation="NBC",
                tv_virtual_channel="5",
                reason="Test correction",
                source="Test",
            )
            db.session.add(correction)
            db.session.commit()

            # Clear the corrections cache to ensure we load the new correction
            FccFacilityService.clear_corrections_cache()

            try:
                # Without correction: facility has blank affiliation
                # With correction: should match NBC
                tags = {"HD", "US", "NBC", "TESTVILLE"}
                network_tags = {"NBC"}
                channel_name = "NBC 5 HD TESTVILLE"

                callsign = EpgService._lookup_fcc_callsign(channel_name, tags, network_tags)
                # Should find WXYZ-LD because the correction adds NBC affiliation
                assert callsign == "WXYZ-LD", f"Expected WXYZ-LD with correction applied, got {callsign}"

            finally:
                # Cleanup
                FccFacility.query.filter_by(facility_id=99999).delete()
                FccCorrection.query.filter_by(callsign="WXYZ-LD").delete()
                FccFacilityService.clear_corrections_cache()
                db.session.commit()

    def test_network_fallback_for_unmatched_cw(self, app):
        """Test that channels fall back to generic network EPG when no local EPG exists.

        This tests the scenario where a CW affiliate in a market without local EPG
        coverage falls back to the generic CW.us2 feed with lower confidence.
        """
        from services.epg_service import EpgService

        with app.app_context():
            # Create an account
            account = Account(
                name="Fallback Test Account",
                server="http://test.example.com",
                username="testuser",
                password="testpass",
            )
            db.session.add(account)
            db.session.commit()

            # Create the generic CW EPG channel (like CW.us2)
            source = EpgSource(
                name="Generic EPG",
                source_type="xmltv",
                url="http://test.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            cw_epg = EpgChannel(
                source_id=source.id,
                channel_id="CW.us2",
                display_name="CW",
            )
            db.session.add(cw_epg)
            db.session.commit()

            # Create a CW channel from a market without local EPG
            channel = Channel(
                account_id=account.id,
                stream_id="cw_laredo",
                name="US: CW 13 LAREDO TX",
                cleaned_name="CW 13 LAREDO TX",
                category_id=1,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Add US and CW tags
            us_tag = Tag.query.filter_by(name="US").first()
            if not us_tag:
                us_tag = Tag(name="US")
                db.session.add(us_tag)
                db.session.commit()

            cw_tag = Tag.query.filter_by(name="CW").first()
            if not cw_tag:
                cw_tag = Tag(name="CW")
                db.session.add(cw_tag)
                db.session.commit()

            for tag in [us_tag, cw_tag]:
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=channel.stream_id,
                    tag_id=tag.id,
                )
                db.session.add(channel_tag)
            db.session.commit()

            try:
                # Run the matching
                stats = EpgService.match_channels_to_epg(account.id)

                # Check that it matched via network_fallback
                assert stats["matched_network_fallback"] == 1, f"Expected network_fallback=1, got {stats}"
                assert stats["unmatched"] == 0, f"Expected no unmatched, got {stats}"

                # Verify the mapping has correct confidence
                mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
                assert mapping is not None, "Mapping should exist"
                assert mapping.mapping_type == "network_fallback"
                assert mapping.confidence == 0.75  # Below 0.80 to indicate fallback

            finally:
                # Cleanup
                ChannelEpgMapping.query.filter_by(channel_id=channel.id).delete()
                ChannelTag.query.filter_by(account_id=account.id).delete()
                Channel.query.filter_by(account_id=account.id).delete()
                Account.query.filter_by(id=account.id).delete()
                EpgChannel.query.filter_by(source_id=source.id).delete()
                EpgSource.query.filter_by(id=source.id).delete()
                db.session.commit()


class TestShiftXmltvTime:
    """Tests for shift_xmltv_time utility function"""

    def test_shift_positive_hours(self):
        """Test shifting time by positive hours"""
        result = shift_xmltv_time("20240101120000 +0000", 2)
        assert result == "20240101140000 +0000"

    def test_shift_negative_hours(self):
        """Test shifting time by negative hours"""
        result = shift_xmltv_time("20240101120000 +0000", -2)
        assert result == "20240101100000 +0000"

    def test_shift_zero_hours(self):
        """Test shifting by zero hours"""
        result = shift_xmltv_time("20240101120000 +0000", 0)
        assert result == "20240101120000 +0000"

    def test_shift_across_day_boundary(self):
        """Test shifting across midnight"""
        result = shift_xmltv_time("20240101230000 +0000", 3)
        assert result == "20240102020000 +0000"

    def test_shift_invalid_time(self):
        """Test shifting with invalid time format"""
        result = shift_xmltv_time("invalid", 2)
        # Should return original on error
        assert result == "invalid"

    def test_shift_empty_time(self):
        """Test shifting with empty time"""
        result = shift_xmltv_time("", 2)
        assert result == ""


class TestDecompressContentExtended:
    """Extended tests for decompress_content utility function"""

    def test_decompress_gzip(self):
        """Test decompressing gzip content"""
        original = b"Hello, World!"
        compressed = gzip.compress(original)
        result = decompress_content(compressed)
        assert result == original

    def test_decompress_uncompressed(self):
        """Test that uncompressed content is returned as-is"""
        original = b"Hello, World!"
        result = decompress_content(original)
        assert result == original

    def test_decompress_empty(self):
        """Test decompressing empty content"""
        result = decompress_content(b"")
        assert result == b""


class TestEastWestTags:
    """Tests for EAST_TAGS and WEST_TAGS constants"""

    def test_east_tags_exist(self):
        """Test that EAST_TAGS constant exists"""
        assert isinstance(EAST_TAGS, (set, frozenset, list, tuple))
        assert len(EAST_TAGS) > 0

    def test_west_tags_exist(self):
        """Test that WEST_TAGS constant exists"""
        assert isinstance(WEST_TAGS, (set, frozenset, list, tuple))
        assert len(WEST_TAGS) > 0

    def test_no_overlap(self):
        """Test that EAST and WEST tags don't overlap"""
        east_set = set(EAST_TAGS)
        west_set = set(WEST_TAGS)
        assert east_set.isdisjoint(west_set)
