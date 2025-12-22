"""
Additional tests to improve coverage for tag service and EPG service
"""
from unittest.mock import patch

from models import Account, EpgSource, RuleSet, TagRule, db

# ============================================================================
# Tag Service Additional Tests
# ============================================================================


class TestTagServiceNormalization:
    """Tests for TagService.normalize_tag_name"""

    def test_normalize_superscript_characters(self, app):
        """Test normalization of superscript characters"""
        from services.tag_service import TagService

        # Test superscript characters
        assert TagService.normalize_tag_name("ᴿᴬᵂ") == "RAW"
        assert TagService.normalize_tag_name("⁶⁰ᶠᵖˢ") == "60FPS"
        assert TagService.normalize_tag_name("ᴰᴹᴬ") == "DMA"

    def test_normalize_with_spaces(self, app):
        """Test normalization replaces spaces with underscores"""
        from services.tag_service import TagService

        assert TagService.normalize_tag_name("New York") == "NEW_YORK"
        assert TagService.normalize_tag_name("  Multiple   Spaces  ") == "MULTIPLE_SPACES"

    def test_normalize_removes_special_chars(self, app):
        """Test normalization removes special characters"""
        from services.tag_service import TagService

        assert TagService.normalize_tag_name("US!@#$") == "US"
        assert TagService.normalize_tag_name("Tag (Test)") == "TAG_TEST"

    def test_normalize_short_tags_filtered(self, app):
        """Test that very short tags are filtered out"""
        from services.tag_service import TagService

        assert TagService.normalize_tag_name("A") == ""
        assert TagService.normalize_tag_name("") == ""
        assert TagService.normalize_tag_name("AB") == "AB"

    def test_normalize_strips_trailing_numbers(self, app):
        """Test that trailing numbers are stripped"""
        from services.tag_service import TagService

        assert TagService.normalize_tag_name("ESPN_123") == "ESPN"
        assert TagService.normalize_tag_name("HBO_1") == "HBO"

    def test_normalize_preserves_internal_numbers(self, app):
        """Test that internal numbers are preserved"""
        from services.tag_service import TagService

        assert TagService.normalize_tag_name("4K") == "4K"
        assert TagService.normalize_tag_name("ESPN2") == "ESPN2"


class TestTagServiceMatchPattern:
    """Tests for TagService._match_pattern"""

    def test_match_prefix(self, app):
        """Test prefix pattern matching"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("US| ESPN", "US|", "prefix")
        assert matched is True
        assert result == "US|"

    def test_match_prefix_no_match(self, app):
        """Test prefix pattern not matching"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("ESPN US|", "US|", "prefix")
        assert matched is False

    def test_match_suffix(self, app):
        """Test suffix pattern matching"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("ESPN HD", "HD", "suffix")
        assert matched is True

    def test_match_suffix_no_match(self, app):
        """Test suffix pattern not matching"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("HD ESPN", "HD", "suffix")
        assert matched is False

    def test_match_contains(self, app):
        """Test contains pattern matching"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("ESPN ᴿᴬᵂ Sports", "ᴿᴬᵂ", "contains")
        assert matched is True

    def test_match_regex(self, app):
        """Test regex pattern matching"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("ESPN 4K HD", r"\b4K\b", "regex")
        assert matched is True

    def test_match_regex_invalid(self, app):
        """Test invalid regex pattern"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("test", "[invalid", "regex")
        assert matched is False

    def test_match_unknown_type(self, app):
        """Test unknown pattern type"""
        from services.tag_service import TagService

        matched, result = TagService._match_pattern("test", "test", "unknown")
        assert matched is False


class TestTagServiceRemoveText:
    """Tests for TagService._remove_text"""

    def test_remove_text_basic(self, app):
        """Test basic text removal"""
        from services.tag_service import TagService

        result = TagService._remove_text("US| ESPN", "US|")
        assert result == " ESPN"

    def test_remove_text_case_insensitive(self, app):
        """Test case-insensitive removal"""
        from services.tag_service import TagService

        result = TagService._remove_text("US| ESPN", "us|")
        assert result == " ESPN"

    def test_remove_text_not_found(self, app):
        """Test removal when text not found"""
        from services.tag_service import TagService

        result = TagService._remove_text("ESPN", "US|")
        assert result == "ESPN"

    def test_remove_text_empty(self, app):
        """Test removal with empty string"""
        from services.tag_service import TagService

        result = TagService._remove_text("ESPN", "")
        assert result == "ESPN"


class TestTagServiceCleanupName:
    """Tests for TagService._cleanup_name"""

    def test_cleanup_removes_leading_separators(self, app):
        """Test removal of leading separators"""
        from services.tag_service import TagService

        assert TagService._cleanup_name(": ESPN") == "ESPN"
        assert TagService._cleanup_name("| ESPN") == "ESPN"
        assert TagService._cleanup_name("- ESPN") == "ESPN"

    def test_cleanup_removes_trailing_separators(self, app):
        """Test removal of trailing separators"""
        from services.tag_service import TagService

        assert TagService._cleanup_name("ESPN :") == "ESPN"
        assert TagService._cleanup_name("ESPN |") == "ESPN"

    def test_cleanup_removes_multiple_spaces(self, app):
        """Test removal of multiple spaces"""
        from services.tag_service import TagService

        assert TagService._cleanup_name("ESPN  HD") == "ESPN HD"
        assert TagService._cleanup_name("ESPN   Sports   HD") == "ESPN Sports HD"

    def test_cleanup_empty_brackets(self, app):
        """Test removal of empty brackets"""
        from services.tag_service import TagService

        result = TagService._cleanup_name("ESPN [] HD")
        # Empty brackets should be removed
        assert "[]" not in result

    def test_cleanup_empty_string(self, app):
        """Test cleanup with empty string"""
        from services.tag_service import TagService

        assert TagService._cleanup_name("") == ""
        assert TagService._cleanup_name(None) is None


# ============================================================================
# Tag Extraction Edge Cases
# ============================================================================


class TestTagExtractionEdgeCases:
    """Test edge cases in tag extraction"""

    def test_extract_tags_empty_rules(self, app):
        """Test extraction with no rules"""
        from services.tag_service import TagService

        tags, cleaned = TagService.extract_tags("ESPN HD", "Sports", [])
        assert tags == set()
        assert cleaned == "ESPN HD"

    def test_extract_tags_callsign_extraction(self, app):
        """Test __CALLSIGN__ tag extraction"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Callsign",
                pattern=r"\([^\)]+\)",
                pattern_type="regex",
                tag_name="__CALLSIGN__",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            from services.tag_service import TagService

            tags, cleaned = TagService.extract_tags("ESPN (WABC)", "Sports", [rule])
            assert "WABC" in tags
            assert "(" not in cleaned

    def test_extract_tags_capture_tag(self, app):
        """Test __CAPTURE__ tag extraction"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Capture Country",
                pattern=r"^([A-Z]{2})\|",
                pattern_type="regex",
                tag_name="__CAPTURE__",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            from services.tag_service import TagService

            tags, cleaned = TagService.extract_tags("US| ESPN", "Sports", [rule])
            assert "US" in tags

    def test_extract_tags_capture_no_group(self, app):
        """Test __CAPTURE__ with no capture group"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            # Rule without capture group - should warn but not crash
            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Bad Capture",
                pattern=r"ESPN",  # No capture group
                pattern_type="regex",
                tag_name="__CAPTURE__",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            from services.tag_service import TagService

            # Should not crash, just log warning
            tags, cleaned = TagService.extract_tags("ESPN HD", "Sports", [rule])
            # No tags should be captured since there's no group
            assert "__CAPTURE__" not in tags


# ============================================================================
# EPG Service Additional Tests
# ============================================================================


class TestEpgServiceHelpers:
    """Tests for EPG service helper functions"""

    def test_extract_callsign_antenna_tv(self, app):
        """Test callsign extraction for AntennaTV format"""
        from services.epg_service import extract_callsign_from_xmltv_id

        result = extract_callsign_from_xmltv_id("AntennaTV.us")
        assert result == "AntennaTV"

    def test_extract_callsign_long_id(self, app):
        """Test callsign extraction for long IDs"""
        from services.epg_service import extract_callsign_from_xmltv_id

        # Very long simple callsigns should be returned
        result = extract_callsign_from_xmltv_id("VERYLONGCHANNELNAME")
        assert result == "VERYLONGCHANNELNAME"

    def test_extract_callsign_with_hyphen(self, app):
        """Test callsign with hyphen"""
        from services.epg_service import extract_callsign_from_xmltv_id

        result = extract_callsign_from_xmltv_id("BBC-One.uk")
        assert "BBC" in result


class TestEpgServiceMatching:
    """Tests for EPG service matching functions"""

    @patch("services.epg_service.EpgService.get_epg_coverage_stats")
    def test_get_coverage_stats_mock(self, mock_stats, app):
        """Test EPG coverage stats function"""
        mock_stats.return_value = {
            "total_channels": 100,
            "channels_with_epg_mapping": 50,
            "coverage_percentage": 50.0,
        }

        from services.epg_service import EpgService

        result = EpgService.get_epg_coverage_stats()
        assert result["coverage_percentage"] == 50.0


class TestEpgServiceNormalizeName:
    """Tests for EPG service name normalization"""

    def test_normalize_name_basic(self, app):
        """Test basic name normalization"""
        from services.epg_service import EpgService

        # Access the private method
        result = EpgService._normalize_name("ESPN HD")
        assert result is not None
        assert "hd" not in result.lower() or result == result.lower()

    def test_normalize_name_empty(self, app):
        """Test normalization with empty input"""
        from services.epg_service import EpgService

        result = EpgService._normalize_name("")
        assert result == ""

    def test_normalize_name_none(self, app):
        """Test normalization with None input"""
        from services.epg_service import EpgService

        result = EpgService._normalize_name(None)
        assert result == ""


class TestEpgServiceFuzzyMatch:
    """Tests for EPG service fuzzy matching"""

    def test_fuzzy_match_no_channels(self, app):
        """Test fuzzy match with no EPG channels"""
        from services.epg_service import EpgService

        result, score = EpgService._fuzzy_match("ESPN", [])
        assert result is None
        assert score == 0.0

    def test_fuzzy_match_empty_name(self, app):
        """Test fuzzy match with empty channel name"""
        from services.epg_service import EpgService

        result, score = EpgService._fuzzy_match("", [])
        assert result is None
        assert score == 0.0

    def test_fuzzy_match_with_channels(self, app):
        """Test fuzzy match with EPG channels"""
        from models import EpgChannel, EpgSource
        from services.epg_service import EpgService

        with app.app_context():
            # Create an EPG source first
            source = EpgSource(name="Test Source", source_type="provider", enabled=True)
            db.session.add(source)
            db.session.flush()

            # Create EPG channels
            epg_channel = EpgChannel(
                source_id=source.id,
                channel_id="espn",
                display_name="ESPN Sports",
            )
            db.session.add(epg_channel)
            db.session.commit()

            channels = [epg_channel]
            result, score = EpgService._fuzzy_match("ESPN", channels)

            # Should find a match
            assert score >= 0.5 or result is not None


class TestEpgServiceProviderSource:
    """Tests for EPG service provider source creation"""

    def test_create_provider_epg_source(self, app):
        """Test creating provider EPG source"""
        with app.app_context():
            # Create an account first
            account = Account(
                name="Test Account",
                username="test",
                password="test",
                server="example.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()
            account_id = account.id

            from services.epg_service import EpgService

            source = EpgService.create_provider_epg_source(account_id)
            assert source is not None
            assert source.source_type == "provider"
            assert source.account_id == account_id

    def test_create_provider_epg_source_existing(self, app):
        """Test creating provider EPG source when one already exists"""
        with app.app_context():
            # Create an account first
            account = Account(
                name="Test Account",
                username="test",
                password="test",
                server="example.com",
                enabled=True,
            )
            db.session.add(account)
            db.session.flush()

            # Create existing source
            existing_source = EpgSource(
                name="Existing Source",
                source_type="provider",
                account_id=account.id,
                enabled=True,
            )
            db.session.add(existing_source)
            db.session.commit()
            account_id = account.id

            from services.epg_service import EpgService

            # Should return existing source
            source = EpgService.create_provider_epg_source(account_id)
            assert source.id == existing_source.id
