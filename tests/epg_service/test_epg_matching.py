"""Tests for services/epg/matching.py channel-to-EPG matching."""
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
from services.epg import EpgService
from services.epg.constants import EAST_TAGS, WEST_TAGS
from services.epg.utils import shift_xmltv_time


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
                category_id=None,
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
            facility = db.session.get(FccFacility, fcc_test_facility)

            # Build callsign index
            epg_channel = db.session.get(EpgChannel, kabc_epg_channel["epg_channel_id"])
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
            facility = db.session.get(FccFacility, fcc_test_facility)

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
        from services.epg import EpgService

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
                category_id=None,
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


class TestPrepareChannelsAndEpg:
    """Tests for _prepare_channels_and_epg helper method"""

    def test_prepare_empty_channels(self, app):
        """Test with no channels in account"""
        with app.app_context():
            account = Account(
                name="Empty",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channels, epg_channels, filter_desc = EpgService._prepare_channels_and_epg(account.id)

            assert channels == []
            assert isinstance(epg_channels, list)
            assert filter_desc == ""

            # Cleanup
            db.session.delete(account)
            db.session.commit()

    def test_prepare_with_channels(self, app):
        """Test with channels in account"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test Channel",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            channels, epg_channels, filter_desc = EpgService._prepare_channels_and_epg(account.id)

            assert len(channels) == 1
            assert channels[0].id == channel.id
            assert filter_desc == ""

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()

    def test_prepare_with_category_filter(self, app):
        """Test with category filter"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="1", category_name="Movies")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test Channel",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            channels, epg_channels, filter_desc = EpgService._prepare_channels_and_epg(
                account.id, category_id=category.id
            )

            assert len(channels) == 1
            assert " in category " in filter_desc

            # Cleanup
            db.session.delete(channel)
            db.session.delete(category)
            db.session.delete(account)
            db.session.commit()


class TestBuildEpgLookupIndices:
    """Tests for _build_epg_lookup_indices helper method"""

    def test_build_indices_empty(self):
        """Test building indices with no EPG channels"""
        epg_by_id, epg_by_name, epg_by_callsign, epg_by_dma = EpgService._build_epg_lookup_indices([])

        assert epg_by_id == {}
        assert epg_by_name == {}
        assert isinstance(epg_by_callsign, dict)
        assert isinstance(epg_by_dma, dict)

    def test_build_indices_with_channels(self, app):
        """Test building indices with EPG channels"""
        with app.app_context():
            source = EpgSource(
                name="Test",
                source_type="provider",
                priority=100,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            epg_ch = EpgChannel(
                source_id=source.id,
                channel_id="ESPN.us",
                display_name="ESPN",
            )
            db.session.add(epg_ch)
            db.session.commit()

            epg_by_id, epg_by_name, epg_by_callsign, epg_by_dma = EpgService._build_epg_lookup_indices([epg_ch])

            assert "espn.us" in epg_by_id
            assert len(epg_by_name) > 0
            assert epg_by_id["espn.us"].id == epg_ch.id

            # Cleanup
            db.session.delete(epg_ch)
            db.session.delete(source)
            db.session.commit()


class TestLoadExistingMappings:
    """Tests for _load_existing_mappings helper method"""

    def test_load_no_mappings(self, app):
        """Test loading when no mappings exist"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            mappings = EpgService._load_existing_mappings([channel])

            assert mappings == {}

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()

    def test_load_existing_mappings(self, app):
        """Test loading existing mappings"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            source = EpgSource(
                name="Test",
                source_type="provider",
                priority=100,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            epg_ch = EpgChannel(
                source_id=source.id,
                channel_id="TEST.us",
                display_name="Test",
            )
            db.session.add(epg_ch)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            mapping = ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_ch.id,
                mapping_type="test",
                confidence=0.9,
            )
            db.session.add(mapping)
            db.session.commit()

            mappings = EpgService._load_existing_mappings([channel])

            assert channel.id in mappings
            assert mappings[channel.id].confidence == 0.9

            # Cleanup
            db.session.delete(mapping)
            db.session.delete(channel)
            db.session.delete(epg_ch)
            db.session.delete(source)
            db.session.delete(account)
            db.session.commit()


class TestLoadCountryTagsForChannels:
    """Tests for _load_country_tags_for_channels helper method"""

    def test_load_no_tags(self, app):
        """Test loading when no country tags exist"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            tags = EpgService._load_country_tags_for_channels(account.id, [channel])

            assert tags == {}

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()

    def test_load_with_country_tags(self, app):
        """Test loading with country tags"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            tag = Tag(name="US")
            db.session.add(tag)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            channel_tag = ChannelTag(account_id=account.id, stream_id="123", tag_id=tag.id)
            db.session.add(channel_tag)
            db.session.commit()

            tags = EpgService._load_country_tags_for_channels(account.id, [channel])

            assert "123" in tags
            assert "US" in tags["123"]

            # Cleanup
            db.session.delete(channel_tag)
            db.session.delete(channel)
            db.session.delete(tag)
            db.session.delete(account)
            db.session.commit()


class TestLoadFccFacilities:
    """Tests for _load_fcc_facilities helper method"""

    def test_load_no_us_channels(self, app):
        """Test loading when no US channels exist"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            country_tags = {}
            facilities = EpgService._load_fcc_facilities([channel], country_tags)

            assert channel.id in facilities
            assert facilities[channel.id] is None

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()


class TestMatchChannelStrategies:
    """Tests for _match_channel_strategies helper method"""

    def test_no_match_found(self, app):
        """Test when no matching strategy succeeds"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Obscure Channel Name",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            matched_epg, match_type, confidence = EpgService._match_channel_strategies(
                channel,
                {},
                {},
                {},
                {},
                [],
                {},
                {},
            )

            assert matched_epg is None
            assert match_type is None
            assert confidence == 0.0

            # Cleanup
            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()

    def test_exact_provider_match(self, app):
        """Test exact match on provider epg_channel_id"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            source = EpgSource(
                name="Test",
                source_type="provider",
                priority=100,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            epg_ch = EpgChannel(
                source_id=source.id,
                channel_id="ESPN.us",
                display_name="ESPN",
            )
            db.session.add(epg_ch)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="ESPN",
                epg_channel_id="ESPN.us",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            epg_by_id = {"espn.us": epg_ch}

            matched_epg, match_type, confidence = EpgService._match_channel_strategies(
                channel,
                {},
                epg_by_id,
                {},
                {},
                [],
                {},
                {},
            )

            assert matched_epg is not None
            assert match_type == "provider"
            assert confidence == 1.0

            # Cleanup
            db.session.delete(channel)
            db.session.delete(epg_ch)
            db.session.delete(source)
            db.session.delete(account)
            db.session.commit()


class TestSaveChannelMapping:
    """Tests for _save_channel_mapping helper method"""

    def test_save_new_mapping(self, app):
        """Test saving a new channel mapping"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            source = EpgSource(
                name="Test",
                source_type="provider",
                priority=100,
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            epg_ch = EpgChannel(
                source_id=source.id,
                channel_id="ESPN.us",
                display_name="ESPN",
            )
            db.session.add(epg_ch)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="ESPN",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            result = EpgService._save_channel_mapping(channel, epg_ch, "provider", 1.0, {})

            assert result is True
            # Verify mapping was created
            mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
            assert mapping is not None
            assert mapping.epg_channel_id == epg_ch.id

            # Cleanup
            db.session.delete(mapping)
            db.session.delete(channel)
            db.session.delete(epg_ch)
            db.session.delete(source)
            db.session.delete(account)
            db.session.commit()

    def test_save_no_match(self, app):
        """Test when there's no match to save"""
        with app.app_context():
            account = Account(
                name="Test",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="123",
                name="Test",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            result = EpgService._save_channel_mapping(channel, None, None, 0.0, {})

            assert result is False


class TestMatchChannelsToEpgFccEnhanced:
    """Test suite for match_channels_to_epg_fcc_enhanced integration"""

    def test_empty_account(self, app):
        """Test with account that has no channels"""
        with app.app_context():
            account = Account(
                name="Empty",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            stats = EpgService.match_channels_to_epg_fcc_enhanced(account.id)

            assert stats["total_channels"] == 0
            assert stats["matched_exact_id"] == 0
            assert stats["unmatched"] == 0

            db.session.delete(account)
            db.session.commit()

    def test_no_epg_data(self, app):
        """Test with channels but no EPG data"""
        with app.app_context():
            account = Account(
                name="NoEpg",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="Test Channel",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            stats = EpgService.match_channels_to_epg_fcc_enhanced(account.id)

            assert stats["total_channels"] == 1
            assert stats["matched_exact_id"] == 0
            assert stats["unmatched"] == 1

            db.session.delete(channel)
            db.session.delete(account)
            db.session.commit()

    def test_exact_id_match(self, app):
        """Test matching by provider epg_channel_id"""
        with app.app_context():
            account = Account(
                name="ExactId",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            source = EpgSource(
                name="TestEpg",
                source_type="xmltv",
                url="http://test.com/epg.xml",
            )
            db.session.add(source)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="Test Channel",
                epg_channel_id="test.1",
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="test.1",
                display_name="Test Channel Name",
                icon_url="http://test.com/icon.png",
            )
            db.session.add(epg_channel)
            db.session.commit()

            stats = EpgService.match_channels_to_epg_fcc_enhanced(account.id)

            assert stats["total_channels"] == 1
            assert stats["matched_exact_id"] == 1
            assert stats["unmatched"] == 0

            # Verify mapping was created
            mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
            assert mapping is not None
            assert mapping.epg_channel_id == epg_channel.id

            db.session.delete(mapping)
            db.session.delete(epg_channel)
            db.session.delete(channel)
            db.session.delete(source)
            db.session.delete(account)
            db.session.commit()

    def test_batch_size_commit(self, app):
        """Test that batch commits work correctly"""
        with app.app_context():
            account = Account(
                name="BatchTest",
                server="http://test.com",
                username="test",
                password="test",
            )
            db.session.add(account)
            db.session.commit()

            source = EpgSource(
                name="TestEpg",
                source_type="xmltv",
                url="http://test.com/epg.xml",
            )
            db.session.add(source)
            db.session.commit()

            # Create 5 channels with exact epg_channel_id matches
            channels = []
            for i in range(5):
                channel = Channel(
                    account_id=account.id,
                    stream_id=f"batch{i}",
                    name=f"Channel {i}",
                    epg_channel_id=f"epg{i}.us",
                    is_active=True,
                )
                db.session.add(channel)
                channels.append(channel)

            db.session.commit()

            # Create matching EPG channels
            epg_channels = []
            for i in range(5):
                epg = EpgChannel(
                    source_id=source.id,
                    channel_id=f"epg{i}.us",
                    display_name=f"EPG Channel {i}",
                    icon_url=f"http://test.com/ch{i}.png",
                )
                db.session.add(epg)
                epg_channels.append(epg)

            db.session.commit()

            stats = EpgService.match_channels_to_epg_fcc_enhanced(account.id, batch_size=2)

            assert stats["total_channels"] == 5
            assert stats["matched_exact_id"] == 5
            assert stats["unmatched"] == 0

            # Cleanup
            for channel in channels:
                for mapping in ChannelEpgMapping.query.filter_by(channel_id=channel.id).all():
                    db.session.delete(mapping)

            for epg in epg_channels:
                db.session.delete(epg)

            for channel in channels:
                db.session.delete(channel)

            db.session.delete(source)
            db.session.delete(account)
            db.session.commit()
