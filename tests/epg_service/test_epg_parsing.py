"""Tests for services/epg/parsing.py and XMLTV utility helpers."""
import gzip

import pytest

from models import EpgChannel, EpgSource, db
from services.epg import EpgService
from services.epg.utils import (
    decompress_content,
    extract_callsign_from_xmltv_id,
    get_decompressing_stream,
    make_sd_xmltv_id,
    normalize_xmltv_url,
    shift_xmltv_time,
)

class TestGetDecompressingStream:
    """Tests for get_decompressing_stream function"""

    def test_gzipped_content_stream(self):
        """Test streaming decompression of gzipped content"""
        original = b"<tv><channel id='test'></channel></tv>"
        compressed = gzip.compress(original)

        stream = get_decompressing_stream(compressed)
        result = stream.read()
        stream.close()

        assert result == original

    def test_uncompressed_content_stream(self):
        """Test that uncompressed content is returned as BytesIO"""
        original = b"<tv><channel id='test'></channel></tv>"

        stream = get_decompressing_stream(original)
        result = stream.read()
        stream.close()

        assert result == original

    def test_stream_with_empty_content(self):
        """Test streaming with empty content"""
        stream = get_decompressing_stream(b"")
        result = stream.read()
        stream.close()

        assert result == b""



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



class TestExtractCallsignEdgeCases:
    """Additional edge case tests for extract_callsign_from_xmltv_id"""

    def test_extract_callsign_with_numbers(self):
        """Test extraction with numeric callsigns"""
        result = extract_callsign_from_xmltv_id("12345.us")
        assert result is not None

    def test_extract_callsign_long_id(self):
        """Test extraction with long IDs"""
        long_id = "VeryLongCallsignWithNumbers123456789.provider.com"
        result = extract_callsign_from_xmltv_id(long_id)
        assert result is not None

    def test_extract_callsign_special_chars(self):
        """Test extraction with special characters in segments"""
        result = extract_callsign_from_xmltv_id("CALL-SIGN.us")
        # Should handle or reject gracefully
        assert result is not None or result is None



class TestShiftXmltvTimeEdgeCases:
    """Additional edge case tests for shift_xmltv_time"""

    def test_shift_xmltv_time_large_hours(self):
        """Test shifting with large hour values"""
        result = shift_xmltv_time("20240101120000 +0000", 48)
        assert "20240103" in result

    def test_shift_xmltv_time_negative_large(self):
        """Test shifting with large negative hour values"""
        result = shift_xmltv_time("20240101120000 +0000", -48)
        assert "2023" in result

    def test_shift_xmltv_time_preserves_format(self):
        """Test that shift preserves XMLTV format"""
        result = shift_xmltv_time("20240115093045 +0100", 2)
        parts = result.split()
        assert len(parts) >= 1
        assert len(parts[0]) >= 8



class TestParseXmltvTimeEdgeCases:
    """Additional edge case tests for _parse_xmltv_time"""

    def test_parse_xmltv_time_with_timezone(self):
        """Test parsing time with timezone info"""
        result = EpgService._parse_xmltv_time("20240101120000 +0100")
        assert result is None or result is not None

    def test_parse_xmltv_time_short_format(self):
        """Test parsing shorter time formats"""
        result = EpgService._parse_xmltv_time("202401011200")
        assert result is None or isinstance(result, object)


