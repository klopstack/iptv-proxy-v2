"""
Tests for SdMatchingService - Station matching logic
"""
from unittest.mock import Mock, patch

from services.sd_matching_service import SdMatchingService


class TestExtractCallsignFromXmltvId:
    """Test callsign extraction from various XMLTV ID formats"""

    def test_extract_from_schedules_direct_format(self):
        """SD format: I{digits}.json.schedulesdirect.org"""
        result = SdMatchingService.extract_callsign_from_xmltv_id("I9009.json.schedulesdirect.org")
        assert result == "9009"

    def test_extract_from_schedules_direct_format_case_insensitive(self):
        """SD format should work with different cases"""
        result = SdMatchingService.extract_callsign_from_xmltv_id("I12345.JSON.SchedulesDirect.org")
        assert result == "12345"

    def test_extract_from_dot_separated_format(self):
        """Standard XMLTV format: CALLSIGN.tld"""
        result = SdMatchingService.extract_callsign_from_xmltv_id("ESPN.us")
        assert result == "ESPN"

    def test_extract_from_complex_callsign(self):
        """Handle complex callsigns with hyphens/numbers"""
        result = SdMatchingService.extract_callsign_from_xmltv_id("NBC-HD.com")
        assert result == "NBC-HD"

    def test_extract_no_dot(self):
        """Simple string without dots returns as-is"""
        result = SdMatchingService.extract_callsign_from_xmltv_id("CNN")
        assert result == "CNN"

    def test_extract_empty_string(self):
        """Empty string returns empty"""
        result = SdMatchingService.extract_callsign_from_xmltv_id("")
        assert result == ""

    def test_extract_none_returns_empty(self):
        """None returns empty string"""
        result = SdMatchingService.extract_callsign_from_xmltv_id(None)
        assert result == ""


class TestBuildChannelLookupStructures:
    """Test building efficient lookup structures from channels"""

    def test_empty_channels_list(self):
        """Empty channel list returns empty structures"""
        by_name, by_epg_id, by_epg_callsign, all_ch = SdMatchingService.build_channel_lookup_structures([])
        assert by_name == {}
        assert by_epg_id == {}
        assert by_epg_callsign == {}
        assert all_ch == []

    def test_single_channel_with_epg_id(self):
        """Single channel with EPG ID builds all structures"""
        ch = Mock()
        ch.name = "ESPN"
        ch.cleaned_name = "ESPN"
        ch.epg_channel_id = "ESPN.us"
        ch.id = "ch1"

        by_name, by_epg_id, by_epg_callsign, all_ch = SdMatchingService.build_channel_lookup_structures([ch])

        assert "espn" in by_name
        assert "espn.us" in by_epg_id
        assert "espn" in by_epg_callsign
        assert len(all_ch) == 1
        assert all_ch[0]["channel"] == ch

    def test_channel_without_cleaned_name_uses_name(self):
        """Channels without cleaned_name use name field"""
        ch = Mock()
        ch.name = "HBO"
        ch.cleaned_name = None
        ch.epg_channel_id = "HBO.us"
        ch.id = "ch1"

        by_name, _, _, all_ch = SdMatchingService.build_channel_lookup_structures([ch])
        assert "hbo" in by_name
        assert all_ch[0]["name"] == "HBO"

    def test_channel_without_epg_id_still_in_name_lookup(self):
        """Channel without EPG ID still indexed by name"""
        ch = Mock()
        ch.name = "LOCAL"
        ch.cleaned_name = "LOCAL"
        ch.epg_channel_id = None
        ch.id = "ch1"

        by_name, by_epg_id, by_epg_callsign, all_ch = SdMatchingService.build_channel_lookup_structures([ch])

        assert "local" in by_name
        assert len(by_epg_id) == 0
        assert len(by_epg_callsign) == 0

    def test_schedules_direct_format_extracts_to_callsign_map(self):
        """SD format IDs extract callsign to separate map"""
        ch = Mock()
        ch.name = "CNN"
        ch.cleaned_name = "CNN"
        ch.epg_channel_id = "I9009.json.schedulesdirect.org"
        ch.id = "ch1"

        by_name, by_epg_id, by_epg_callsign, all_ch = SdMatchingService.build_channel_lookup_structures([ch])

        assert "9009" in by_epg_callsign
        assert by_epg_callsign["9009"] == ch

    def test_multiple_channels_all_indexed(self):
        """Multiple channels with different formats all indexed"""
        ch1 = Mock()
        ch1.name = "ESPN"
        ch1.cleaned_name = "ESPN"
        ch1.epg_channel_id = "ESPN.us"
        ch1.id = "ch1"

        ch2 = Mock()
        ch2.name = "CNN"
        ch2.cleaned_name = "CNN"
        ch2.epg_channel_id = "I9009.json.schedulesdirect.org"
        ch2.id = "ch2"

        by_name, by_epg_id, by_epg_callsign, all_ch = SdMatchingService.build_channel_lookup_structures([ch1, ch2])

        assert len(all_ch) == 2
        assert "espn" in by_name
        assert "cnn" in by_name
        assert "espn.us" in by_epg_id
        assert "i9009.json.schedulesdirect.org" in by_epg_id
        assert "9009" in by_epg_callsign


class TestMatchExactCallsign:
    """Test exact callsign matching strategies"""

    def test_match_callsign_to_channel_name(self):
        """Match callsign against channel name lookup"""
        ch = Mock()
        by_name = {"espn": ch}
        by_epg_id = {}
        by_epg_callsign = {}

        found, match, mtype = SdMatchingService.match_exact_callsign("ESPN", by_name, by_epg_id, by_epg_callsign)
        assert found is True
        assert match == ch
        assert mtype == "exact_callsign_to_name"

    def test_match_callsign_to_epg_id(self):
        """Match callsign against EPG ID lookup"""
        ch = Mock()
        by_name = {}
        by_epg_id = {"espn.us": ch}
        by_epg_callsign = {}

        found, match, mtype = SdMatchingService.match_exact_callsign("ESPN.us", by_name, by_epg_id, by_epg_callsign)
        assert found is True
        assert match == ch
        assert mtype == "exact_callsign_to_epg_id"

    def test_match_callsign_to_extracted_xmltv(self):
        """Match against extracted XMLTV callsigns"""
        ch = Mock()
        by_name = {}
        by_epg_id = {}
        by_epg_callsign = {"9009": ch}

        found, match, mtype = SdMatchingService.match_exact_callsign("9009", by_name, by_epg_id, by_epg_callsign)
        assert found is True
        assert match == ch
        assert mtype == "exact_callsign_to_xmltv"

    def test_no_match_returns_false(self):
        """Non-existent callsign returns False"""
        by_name = {}
        by_epg_id = {}
        by_epg_callsign = {}

        found, match, mtype = SdMatchingService.match_exact_callsign("NOTFOUND", by_name, by_epg_id, by_epg_callsign)
        assert found is False
        assert match is None
        assert mtype is None

    def test_empty_callsign_returns_false(self):
        """Empty callsign returns False"""
        by_name = {"espn": Mock()}
        by_epg_id = {}
        by_epg_callsign = {}

        found, match, mtype = SdMatchingService.match_exact_callsign("", by_name, by_epg_id, by_epg_callsign)
        assert found is False

    def test_case_insensitive_matching(self):
        """Matching is case-insensitive"""
        ch = Mock()
        by_name = {"espn": ch}
        by_epg_id = {}
        by_epg_callsign = {}

        found, match, mtype = SdMatchingService.match_exact_callsign("EsPn", by_name, by_epg_id, by_epg_callsign)
        assert found is True
        assert match == ch


class TestMatchStationIdInXmltvId:
    """Test matching SD station IDs to XMLTV IDs"""

    def test_match_station_id_contained_in_xmltv(self):
        """Station ID contained in XMLTV ID matches"""
        ch = Mock()
        all_ch = [{"channel": ch, "epg_id": "I9009.json.schedulesdirect.org"}]

        found, match, mtype = SdMatchingService.match_station_id_in_xmltv("9009", all_ch)
        assert found is True
        assert match == ch
        assert mtype == "exact_station_id_in_xmltv"

    def test_no_match_when_station_id_not_in_xmltv(self):
        """Station ID not in XMLTV ID returns False"""
        ch = Mock()
        all_ch = [{"channel": ch, "epg_id": "ESPN.us"}]

        found, match, mtype = SdMatchingService.match_station_id_in_xmltv("9009", all_ch)
        assert found is False

    def test_no_match_empty_station_id(self):
        """Empty station ID returns False"""
        ch = Mock()
        all_ch = [{"channel": ch, "epg_id": "I9009.json.schedulesdirect.org"}]

        found, match, mtype = SdMatchingService.match_station_id_in_xmltv("", all_ch)
        assert found is False

    def test_no_match_no_channels(self):
        """No channels to search returns False"""
        found, match, mtype = SdMatchingService.match_station_id_in_xmltv("9009", [])
        assert found is False


class TestMatchFuzzy:
    """Test fuzzy matching logic"""

    def test_fuzzy_match_above_threshold(self):
        """Terms matching above confidence threshold"""
        ch = Mock()
        all_ch = [
            {
                "channel": ch,
                "name": "ESPN",
                "name_lower": "espn",
                "epg_id": "ESPN.us",
            }
        ]

        found, match, confidence, mtype = SdMatchingService.match_fuzzy(
            ["ESPN"], min_confidence=0.8, all_channels=all_ch
        )
        assert found is True
        assert match == ch
        assert confidence >= 0.8
        assert mtype == "fuzzy_name"

    def test_fuzzy_match_below_threshold(self):
        """Terms below confidence threshold not matched"""
        ch = Mock()
        all_ch = [
            {
                "channel": ch,
                "name": "ESPN",
                "name_lower": "espn",
                "epg_id": "ESPN.us",
            }
        ]

        found, match, confidence, mtype = SdMatchingService.match_fuzzy(
            ["XYZ"], min_confidence=0.9, all_channels=all_ch
        )
        assert found is False

    def test_fuzzy_match_picks_best_confidence(self):
        """Best confidence match is selected"""
        ch1 = Mock()
        ch2 = Mock()
        all_ch = [
            {
                "channel": ch1,
                "name": "ESPN",
                "name_lower": "espn",
                "epg_id": "ESPN.us",
            },
            {
                "channel": ch2,
                "name": "CNN",
                "name_lower": "cnn",
                "epg_id": "CNN.us",
            },
        ]

        # "ESPN" should match ch1 better than ch2
        found, match, confidence, mtype = SdMatchingService.match_fuzzy(
            ["ESPN"], min_confidence=0.5, all_channels=all_ch
        )
        assert match == ch1

    def test_fuzzy_match_empty_terms(self):
        """Empty search terms returns no match"""
        all_ch = [
            {
                "channel": Mock(),
                "name": "ESPN",
                "name_lower": "espn",
                "epg_id": "ESPN.us",
            }
        ]

        found, match, confidence, mtype = SdMatchingService.match_fuzzy([], min_confidence=0.8, all_channels=all_ch)
        assert found is False

    def test_fuzzy_match_none_terms_skipped(self):
        """None/empty strings in terms are skipped"""
        ch = Mock()
        all_ch = [
            {
                "channel": ch,
                "name": "ESPN",
                "name_lower": "espn",
                "epg_id": "ESPN.us",
            }
        ]

        found, match, confidence, mtype = SdMatchingService.match_fuzzy(
            [None, "", "ESPN"], min_confidence=0.8, all_channels=all_ch
        )
        assert found is True
        assert match == ch

    def test_fuzzy_match_against_extracted_xmltv(self):
        """Can also fuzzy match against extracted XMLTV callsigns"""
        ch = Mock()
        all_ch = [
            {
                "channel": ch,
                "name": "CNN",
                "name_lower": "cnn",
                "epg_id": "I9009.json.schedulesdirect.org",
            }
        ]

        found, match, confidence, mtype = SdMatchingService.match_fuzzy(
            ["9009"], min_confidence=0.8, all_channels=all_ch
        )
        assert found is True
        assert match == ch
        assert mtype == "fuzzy_xmltv"


class TestMatchStation:
    """Test matching a single station to channels"""

    @patch("services.sd_matching_service.Channel")
    def test_match_station_no_active_channels(self, mock_channel_class):
        """Station with no active channels returns unmatched"""
        mock_channel_class.query.filter_by.return_value.all.return_value = []

        station = Mock()
        station.id = "st1"
        station.station_id = "9009"
        station.callsign = "CNN"
        station.name = "CNN HD"

        result = SdMatchingService.match_station(
            station,
            account_id=1,
            source_id=1,
        )

        assert result["matched"] is False
        assert "No active channels" in result["reason"]

    @patch("services.sd_matching_service.Channel")
    def test_match_station_exact_callsign(self, mock_channel_class):
        """Station matches with exact callsign"""
        ch_espn = Mock()
        ch_espn.id = "ch1"
        ch_espn.name = "ESPN"
        ch_espn.cleaned_name = "ESPN"
        ch_espn.epg_channel_id = "ESPN.us"

        mock_channel_class.query.filter_by.return_value.all.return_value = [ch_espn]

        station = Mock()
        station.id = "st1"
        station.station_id = "0000"
        station.callsign = "ESPN"
        station.name = ""

        result = SdMatchingService.match_station(
            station,
            account_id=1,
            source_id=1,
            match_mode="exact",
        )

        assert result["matched"] is True
        assert result["station_callsign"] == "ESPN"

    @patch("services.sd_matching_service.Channel")
    def test_match_station_ignored_inactive_channels(self, mock_channel_class):
        """Inactive channels not matched"""
        ch_inactive = Mock()
        ch_inactive.id = "ch1"
        ch_inactive.name = "INACTIVE"
        ch_inactive.cleaned_name = "INACTIVE"
        ch_inactive.epg_channel_id = "INACT.us"
        ch_inactive.is_active = False

        # Only active channels returned
        mock_channel_class.query.filter_by.return_value.all.return_value = []

        station = Mock()
        station.id = "st1"
        station.station_id = "0000"
        station.callsign = "INACTIVE"
        station.name = ""

        result = SdMatchingService.match_station(
            station,
            account_id=1,
            source_id=1,
            match_mode="exact",
        )

        # Should not match because channel is inactive
        assert result["matched"] is False

    @patch("services.sd_matching_service.Channel")
    def test_match_station_station_id_in_xmltv(self, mock_channel_class):
        """Station matches via station ID in XMLTV ID"""
        ch_cnn = Mock()
        ch_cnn.id = "ch2"
        ch_cnn.name = "CNN"
        ch_cnn.cleaned_name = "CNN"
        ch_cnn.epg_channel_id = "I9009.json.schedulesdirect.org"

        mock_channel_class.query.filter_by.return_value.all.return_value = [ch_cnn]

        station = Mock()
        station.id = "st1"
        station.station_id = "9009"
        station.callsign = ""
        station.name = ""

        result = SdMatchingService.match_station(
            station,
            account_id=1,
            source_id=1,
            match_mode="exact",
        )

        assert result["matched"] is True

    @patch("services.sd_matching_service.Channel")
    def test_match_station_fuzzy_mode(self, mock_channel_class):
        """Station matches in fuzzy mode with confidence score"""
        ch_espn = Mock()
        ch_espn.id = "ch1"
        ch_espn.name = "ESPN"
        ch_espn.cleaned_name = "ESPN"
        ch_espn.epg_channel_id = "ESPN.us"

        mock_channel_class.query.filter_by.return_value.all.return_value = [ch_espn]

        station = Mock()
        station.id = "st1"
        station.station_id = "0000"
        station.callsign = "ESPIN"  # Misspelled ESPN
        station.name = ""

        result = SdMatchingService.match_station(
            station,
            account_id=1,
            source_id=1,
            match_mode="fuzzy",
            min_confidence=0.7,
        )

        assert result["matched"] is True
        assert result["confidence"] > 0

    @patch("services.sd_matching_service.Channel")
    def test_match_station_no_match_returns_unmatched_dict(self, mock_channel_class):
        """Unmatched station returns proper dict structure"""
        ch_espn = Mock()
        ch_espn.id = "ch1"
        ch_espn.name = "ESPN"
        ch_espn.cleaned_name = "ESPN"
        ch_espn.epg_channel_id = "ESPN.us"

        mock_channel_class.query.filter_by.return_value.all.return_value = [ch_espn]

        station = Mock()
        station.id = "st1"
        station.station_id = "0000"
        station.callsign = "UNKNOWN"
        station.name = "Unknown Channel"
        station.channel_number = None

        result = SdMatchingService.match_station(
            station,
            account_id=1,
            source_id=1,
        )

        assert result["matched"] is False
        assert result["station_id"] == "st1"
        assert result["sd_station_id"] == "0000"


class TestMatchStationsBatch:
    """Test batch matching of stations"""

    @patch("services.sd_matching_service.Channel")
    def test_batch_match_empty_stations(self, mock_channel_class, app):
        """Empty stations list returns valid response"""
        with app.app_context():
            mock_channel_class.query.filter_by.return_value.all.return_value = []

            result = SdMatchingService.match_stations_batch(
                [],
                account_id=1,
                source_id=1,
            )

            assert result["account_id"] == 1
            assert result["stats"]["total_stations"] == 0
            assert result["stats"]["matched"] == 0

    @patch("services.sd_matching_service.SdMatchingService.match_station")
    @patch("services.sd_matching_service.Channel")
    def test_batch_match_with_matches(self, mock_channel_class, mock_match_station, app):
        """Batch matching aggregates results"""
        with app.app_context():
            mock_channel_class.query.filter_by.return_value.all.return_value = [Mock(id="ch1")]

            st1 = Mock()
            st1.id = "st1"
            st2 = Mock()
            st2.id = "st2"

            mock_match_station.side_effect = [
                {"matched": True, "channel_id": "ch1"},
                {"matched": False},
            ]

            result = SdMatchingService.match_stations_batch(
                [st1, st2],
                account_id=1,
                source_id=1,
            )

            assert result["stats"]["total_stations"] == 2
            assert result["stats"]["matched"] == 1
            assert result["stats"]["unmatched_stations"] == 1
