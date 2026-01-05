"""
Tests for TagService

Uses shared fixtures from conftest.py for proper test isolation.
"""

import pytest

from models import Account, AccountRuleSet, RuleSet, TagRule, db
from services.tag_service import TagService

# app fixture is provided by conftest.py


@pytest.fixture
def sample_ruleset(app):
    """Create a sample ruleset with rules"""
    with app.app_context():
        ruleset = RuleSet(
            name="Test Ruleset", description="Test ruleset for unit tests", is_default=False, enabled=True, priority=100
        )
        db.session.add(ruleset)
        db.session.flush()

        ruleset_id = ruleset.id

        # Add some rules
        rules = [
            TagRule(
                ruleset_id=ruleset_id,
                name="US Prefix",
                pattern="US|",
                pattern_type="prefix",
                tag_name="US",
                source="both",
                remove_from_name=True,
                priority=10,
            ),
            TagRule(
                ruleset_id=ruleset_id,
                name="RAW Badge",
                pattern="ᴿᴬᵂ",
                pattern_type="contains",
                tag_name="RAW",
                source="both",
                remove_from_name=True,
                priority=20,
            ),
            TagRule(
                ruleset_id=ruleset_id,
                name="4K Quality",
                pattern=r"\b4K\b",
                pattern_type="regex",
                tag_name="4K",
                source="both",
                remove_from_name=True,
                priority=20,
            ),
        ]

        for rule in rules:
            db.session.add(rule)

        db.session.commit()
        return ruleset_id


@pytest.fixture
def sample_account(app, sample_ruleset):
    """Create a sample account"""
    with app.app_context():
        account = Account(
            name="Test Account", server="test.server.com", username="testuser", password="testpass", enabled=True
        )
        db.session.add(account)
        db.session.flush()

        account_id = account.id

        # Assign ruleset to account
        assignment = AccountRuleSet(account_id=account_id, ruleset_id=sample_ruleset, priority=100)
        db.session.add(assignment)
        db.session.commit()

        return account_id


class TestTagExtraction:
    """Test tag extraction functionality"""

    def test_extract_tags_with_prefix(self, app, sample_ruleset):
        """Test extracting tags from prefix pattern"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            channel_name = "US| CNN News"
            category_name = "News"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert cleaned_name == "CNN News"

    def test_extract_tags_with_multiple_patterns(self, app, sample_ruleset):
        """Test extracting multiple tags"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            channel_name = "US| ESPN 4K ᴿᴬᵂ"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "RAW" in tags
            assert "4K" in tags
            assert "ESPN" in cleaned_name

    def test_extract_tags_with_regex(self, app, sample_ruleset):
        """Test regex pattern matching"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            channel_name = "Discovery 4K UHD"
            category_name = "Documentary"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "4K" in tags

    def test_normalize_tag_name(self, app):
        """Test tag name normalization"""
        with app.app_context():
            # Test superscript conversion
            assert TagService.normalize_tag_name("ᴿᴬᵂ") == "RAW"
            assert TagService.normalize_tag_name("⁶⁰ᶠᵖˢ") == "60FPS"

            # Test case conversion
            assert TagService.normalize_tag_name("us") == "US"
            assert TagService.normalize_tag_name("4k") == "4K"

            # Test space handling
            assert TagService.normalize_tag_name("US SPORTS") == "US_SPORTS"


class TestRulesetRetrieval:
    """Test ruleset and rule retrieval for accounts"""

    def test_get_rules_for_account_with_assigned_ruleset(self, app, sample_account, sample_ruleset):
        """Test getting rules for account with assigned ruleset"""
        with app.app_context():
            account = db.session.get(Account, sample_account)
            rules = TagService.get_rules_for_account(account)

            # Should have 3 rules from the test ruleset
            assert len(rules) == 3
            assert all(isinstance(rule, TagRule) for rule in rules)

    def test_get_rules_for_account_with_default_ruleset(self, app):
        """Test getting rules for account without assigned ruleset (uses default)"""
        with app.app_context():
            # Create a default ruleset
            default_ruleset = RuleSet(
                name="Default", description="Default rules", is_default=True, enabled=True, priority=100
            )
            db.session.add(default_ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=default_ruleset.id,
                name="Default Rule",
                pattern="TEST|",
                pattern_type="prefix",
                tag_name="TEST",
                source="both",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)

            # Create account without ruleset assignment
            account = Account(
                name="Test Account No Rules",
                server="test.server.com",
                username="testuser",
                password="testpass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            rules = TagService.get_rules_for_account(account)

            # Should get default ruleset rules
            assert len(rules) == 1
            assert rules[0].tag_name == "TEST"

    def test_get_rules_for_account_no_rules(self, app):
        """Test getting rules for account when no rulesets exist"""
        with app.app_context():
            account = Account(
                name="Test Account No Rules",
                server="test.server.com",
                username="testuser",
                password="testpass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            rules = TagService.get_rules_for_account(account)

            # Should return empty list
            assert len(rules) == 0


class TestPatternMatching:
    """Test pattern matching methods"""

    def test_match_pattern_prefix(self, app):
        """Test prefix pattern matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("US| Channel", "US|", "prefix")
            assert matched is True
            assert match_text == "US|"

            matched, match_text = TagService._match_pattern("Channel US|", "US|", "prefix")
            assert matched is False

    def test_match_pattern_suffix(self, app):
        """Test suffix pattern matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("Channel HD", "HD", "suffix")
            assert matched is True
            assert match_text == "HD"

            matched, match_text = TagService._match_pattern("HD Channel", "HD", "suffix")
            assert matched is False

    def test_match_pattern_contains(self, app):
        """Test contains pattern matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("Channel 4K HD", "4K", "contains")
            assert matched is True
            assert match_text == "4K"

    def test_match_pattern_regex(self, app):
        """Test regex pattern matching"""
        with app.app_context():
            matched, match_obj = TagService._match_pattern("Channel 4K", r"\b4K\b", "regex")
            assert matched is True
            # Regex returns match object for capture group access
            assert match_obj.group() == "4K"

            # Should not match 4K in middle of word
            matched, match_obj = TagService._match_pattern("Channel X4KUHD", r"\b4K\b", "regex")
            assert matched is False

    def test_match_pattern_case_insensitive(self, app):
        """Test case-insensitive matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("us| Channel", "US|", "prefix")
            assert matched is True


class TestDefaultRulesetCreation:
    """Test default ruleset creation"""

    def test_create_default_ruleset(self, app):
        """Test creating default ruleset"""
        with app.app_context():
            ruleset = TagService.create_default_ruleset(db.session)

            assert ruleset is not None
            assert ruleset.name == "Default"
            assert ruleset.is_default is True
            assert len(ruleset.rules) > 0

    def test_create_default_ruleset_idempotent(self, app):
        """Test that creating default ruleset twice returns same ruleset"""
        with app.app_context():
            ruleset1 = TagService.create_default_ruleset(db.session)
            ruleset2 = TagService.create_default_ruleset(db.session)

            assert ruleset1.id == ruleset2.id


class TestSpecialTagTypes:
    """Test special tag behaviors like __LOCATION__, __CALLSIGN__, __CLEANUP__"""

    def test_location_extraction(self, app):
        """Test __LOCATION__ tag extraction"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Location",
                pattern=r"\[([^\]]+)\]",
                pattern_type="regex",
                tag_name="__LOCATION__",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "ESPN [US]"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "[" not in cleaned_name
            assert "]" not in cleaned_name

    def test_cleanup_tag(self, app):
        """Test __CLEANUP__ tag that removes without creating tag"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Cleanup",
                pattern="|",
                pattern_type="contains",
                tag_name="__CLEANUP__",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "US| ESPN"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            # Should not create a tag
            assert "__CLEANUP__" not in tags
            # Should remove the pipe
            assert "|" not in cleaned_name


class TestTagRuleReplacement:
    """Test tag rule replacement functionality"""

    def test_simple_replacement(self, app, sample_ruleset):
        """Test replacing text instead of removing it"""
        with app.app_context():
            # Create a rule that replaces typo "DISCTRICT" with "DISTRICT"
            rule = TagRule(
                ruleset_id=sample_ruleset,
                name="Fix DISCTRICT typo",
                pattern="DISCTRICT",
                pattern_type="contains",
                tag_name="__CLEANUP__",
                source="channel_name",
                remove_from_name=True,
                replacement="DISTRICT",
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "ABC 7 DISCTRICT OF COLUMBIA"
            category_name = "US Local"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "DISTRICT" in cleaned_name
            assert "DISCTRICT" not in cleaned_name
            assert cleaned_name == "ABC 7 DISTRICT OF COLUMBIA"

    def test_replacement_case_insensitive(self, app, sample_ruleset):
        """Test that replacement works case-insensitively"""
        with app.app_context():
            rule = TagRule(
                ruleset_id=sample_ruleset,
                name="Fix lowercase typo",
                pattern="disctrict",
                pattern_type="contains",
                tag_name="__CLEANUP__",
                source="channel_name",
                remove_from_name=True,
                replacement="DISTRICT",
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "ABC 7 DISCTRICT OF COLUMBIA"
            category_name = "US Local"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "DISTRICT" in cleaned_name
            assert "DISCTRICT" not in cleaned_name

    def test_replacement_with_tag(self, app, sample_ruleset):
        """Test replacement that also creates a tag"""
        with app.app_context():
            rule = TagRule(
                ruleset_id=sample_ruleset,
                name="Fix HD typo and tag",
                pattern="HQ",
                pattern_type="contains",
                tag_name="HD",
                source="channel_name",
                remove_from_name=True,
                replacement="HD",
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "ESPN HQ"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "HD" in tags
            assert "ESPN HD" == cleaned_name.strip()

    def test_replacement_with_regex(self, app, sample_ruleset):
        """Test replacement with regex pattern"""
        with app.app_context():
            rule = TagRule(
                ruleset_id=sample_ruleset,
                name="Fix multiple spaces",
                pattern=r"\s{2,}",
                pattern_type="regex",
                tag_name="__CLEANUP__",
                source="channel_name",
                remove_from_name=True,
                replacement=" ",
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "ABC  7   News"
            category_name = "US Local"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            # Multiple spaces should be reduced
            assert "  " not in cleaned_name

    def test_no_replacement_when_remove_false(self, app, sample_ruleset):
        """Test that replacement is not applied when remove_from_name is False"""
        with app.app_context():
            rule = TagRule(
                ruleset_id=sample_ruleset,
                name="Tag only, no replace",
                pattern="ESPN",
                pattern_type="contains",
                tag_name="ESPN",
                source="channel_name",
                remove_from_name=False,
                replacement="SPORTS",
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "ESPN 4K"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            # Tag should be added
            assert "ESPN" in tags
            # But name should NOT be modified because remove_from_name is False
            assert cleaned_name == "ESPN 4K"

    def test_replacement_none_means_remove(self, app, sample_ruleset):
        """Test that None replacement means remove (backward compatible)"""
        with app.app_context():
            rule = TagRule(
                ruleset_id=sample_ruleset,
                name="Remove prefix",
                pattern="US|",
                pattern_type="prefix",
                tag_name="US",
                source="channel_name",
                remove_from_name=True,
                replacement=None,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "US| CNN"
            category_name = "News"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "US|" not in cleaned_name
            assert cleaned_name.strip() == "CNN"


class TestRemoveText:
    """Test _remove_text() static method"""

    def test_remove_text_basic(self, app):
        """Test basic text removal"""
        with app.app_context():
            result = TagService._remove_text("US| CNN", "US|")
            assert result == " CNN"

    def test_remove_text_case_insensitive(self, app):
        """Test case-insensitive removal"""
        with app.app_context():
            result = TagService._remove_text("US| CNN", "us|")
            assert result == " CNN"

    def test_remove_text_middle_of_string(self, app):
        """Test removing text from middle of string"""
        with app.app_context():
            result = TagService._remove_text("ESPN 4K UHD", "4K")
            assert result == "ESPN  UHD"

    def test_remove_text_not_found(self, app):
        """Test when text to remove is not found"""
        with app.app_context():
            original = "ESPN News"
            result = TagService._remove_text(original, "4K")
            assert result == original

    def test_remove_text_empty_to_remove(self, app):
        """Test removal with empty string"""
        with app.app_context():
            original = "ESPN"
            result = TagService._remove_text(original, "")
            assert result == original

    def test_remove_text_empty_original(self, app):
        """Test removal with empty original string"""
        with app.app_context():
            result = TagService._remove_text("", "text")
            assert result == ""

    def test_remove_text_entire_string(self, app):
        """Test removing entire string"""
        with app.app_context():
            result = TagService._remove_text("US|", "US|")
            assert result == ""

    def test_remove_text_first_occurrence(self, app):
        """Test that only first occurrence is removed"""
        with app.app_context():
            result = TagService._remove_text("US| ESPN US|", "US|")
            # Should only remove first occurrence
            assert result.count("US|") == 1


class TestReplaceText:
    """Test _replace_text() static method"""

    def test_replace_text_basic(self, app):
        """Test basic text replacement"""
        with app.app_context():
            result = TagService._replace_text("US| CNN", "US|", "")
            assert result == " CNN"

    def test_replace_text_with_replacement(self, app):
        """Test text replacement with new text"""
        with app.app_context():
            result = TagService._replace_text("DISCTRICT", "DISCTRICT", "DISTRICT")
            assert result == "DISTRICT"

    def test_replace_text_case_insensitive(self, app):
        """Test case-insensitive replacement"""
        with app.app_context():
            result = TagService._replace_text("ABC 4k UHD", "4k", "4K")
            assert result == "ABC 4K UHD"

    def test_replace_text_not_found(self, app):
        """Test when text to replace is not found"""
        with app.app_context():
            original = "ESPN News"
            result = TagService._replace_text(original, "4K", "UHD")
            assert result == original

    def test_replace_text_empty_to_replace(self, app):
        """Test replacement with empty string to replace"""
        with app.app_context():
            original = "ESPN"
            result = TagService._replace_text(original, "", "NEW")
            assert result == original

    def test_replace_text_empty_original(self, app):
        """Test replacement with empty original string"""
        with app.app_context():
            result = TagService._replace_text("", "text", "new")
            assert result == ""

    def test_replace_text_with_empty_replacement(self, app):
        """Test replacement with empty replacement string"""
        with app.app_context():
            result = TagService._replace_text("ABC 4K NEWS", "4K", "")
            assert result == "ABC  NEWS"

    def test_replace_text_first_occurrence_only(self, app):
        """Test that only first occurrence is replaced"""
        with app.app_context():
            result = TagService._replace_text("US| ESPN US|", "US|", "CA|")
            # Should only replace first occurrence
            assert result == "CA| ESPN US|"


class TestCleanupName:
    """Test _cleanup_name() static method"""

    def test_cleanup_name_leading_separator(self, app):
        """Test removal of leading separators"""
        with app.app_context():
            result = TagService._cleanup_name(": ESPN News")
            assert result == "ESPN News"

            result = TagService._cleanup_name("| CNN")
            assert result == "CNN"

            result = TagService._cleanup_name("- News")
            assert result == "News"

    def test_cleanup_name_trailing_separator(self, app):
        """Test removal of trailing separators"""
        with app.app_context():
            result = TagService._cleanup_name("ESPN :")
            assert result == "ESPN"

            result = TagService._cleanup_name("CNN |")
            assert result == "CNN"

    def test_cleanup_name_multiple_spaces(self, app):
        """Test removal of multiple spaces"""
        with app.app_context():
            result = TagService._cleanup_name("ESPN   News")
            assert result == "ESPN News"

            result = TagService._cleanup_name("ABC    7")
            assert result == "ABC 7"

    def test_cleanup_name_empty_brackets(self, app):
        """Test removal of empty brackets"""
        with app.app_context():
            result = TagService._cleanup_name("ESPN []")
            assert result == "ESPN"

            result = TagService._cleanup_name("[] CNN")
            assert result == "CNN"

    def test_cleanup_name_empty_parentheses(self, app):
        """Test removal of empty parentheses"""
        with app.app_context():
            result = TagService._cleanup_name("ESPN ()")
            assert result == "ESPN"

            result = TagService._cleanup_name("() CNN")
            assert result == "CNN"

    def test_cleanup_name_empty_braces(self, app):
        """Test removal of empty braces"""
        with app.app_context():
            result = TagService._cleanup_name("ESPN {}")
            assert result == "ESPN"

    def test_cleanup_name_whitespace_in_brackets(self, app):
        """Test removal of brackets with only whitespace"""
        with app.app_context():
            result = TagService._cleanup_name("ESPN [  ]")
            assert result == "ESPN"

    def test_cleanup_name_complex(self, app):
        """Test complex cleanup with multiple issues"""
        with app.app_context():
            result = TagService._cleanup_name(": ESPN  News []")
            assert result == "ESPN News"

    def test_cleanup_name_empty_string(self, app):
        """Test cleanup of empty string"""
        with app.app_context():
            result = TagService._cleanup_name("")
            assert result == ""

    def test_cleanup_name_only_whitespace(self, app):
        """Test cleanup of whitespace-only string"""
        with app.app_context():
            result = TagService._cleanup_name("   ")
            assert result == ""

    def test_cleanup_name_preserves_content(self, app):
        """Test that cleanup preserves actual content"""
        with app.app_context():
            result = TagService._cleanup_name("ABC 7 News Today")
            assert result == "ABC 7 News Today"


class TestNormalizeFilterTags:
    """Test normalize_filter_tags() static method"""

    def test_normalize_filter_tags_basic(self, app):
        """Test basic tag normalization for filtering"""
        with app.app_context():
            result = TagService.normalize_filter_tags(["us", "hd", "4k"])
            assert result == ["US", "HD", "4K"]

    def test_normalize_filter_tags_with_whitespace(self, app):
        """Test normalization with whitespace"""
        with app.app_context():
            result = TagService.normalize_filter_tags([" us ", "  hd  "])
            assert result == ["US", "HD"]

    def test_normalize_filter_tags_empty_list(self, app):
        """Test with empty list"""
        with app.app_context():
            result = TagService.normalize_filter_tags([])
            assert result == []

    def test_normalize_filter_tags_empty_strings(self, app):
        """Test filtering of empty strings"""
        with app.app_context():
            result = TagService.normalize_filter_tags(["us", "", "hd", ""])
            assert result == ["US", "HD"]

    def test_normalize_filter_tags_none_values(self, app):
        """Test filtering of None values"""
        with app.app_context():
            result = TagService.normalize_filter_tags(["us", None, "hd"])
            assert result == ["US", "HD"]

    def test_normalize_filter_tags_mixed_case(self, app):
        """Test mixed case conversion"""
        with app.app_context():
            result = TagService.normalize_filter_tags(["Us", "HD", "4k"])
            assert result == ["US", "HD", "4K"]

    def test_normalize_filter_tags_with_special_chars(self, app):
        """Test that special chars are preserved (unlike normalize_tag_name)"""
        with app.app_context():
            # Filter normalization should preserve user intent, including colons
            result = TagService.normalize_filter_tags(["network:fox"])
            assert result == ["NETWORK:FOX"]


class TestCaptureTags:
    """Test __CAPTURE__ special tag functionality"""

    def test_capture_basic(self, app):
        """Test basic capture group extraction"""
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

            rules = [rule]
            channel_name = "US| ESPN"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "ESPN" in cleaned_name

    def test_capture_with_replacement(self, app):
        """Test capture with replacement"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Capture and replace",
                pattern=r"^([A-Z]{2})\|",
                pattern_type="regex",
                tag_name="__CAPTURE__",
                source="channel_name",
                remove_from_name=True,
                replacement="",  # Empty replacement removes it
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "US| ESPN"
            category_name = "Sports"

            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            # Replacement with empty string removes the matched text
            assert cleaned_name == "ESPN"

    def test_capture_no_capture_group(self, app):
        """Test capture when regex has no capture group (logs warning)"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Bad capture",
                pattern=r"^[A-Z]{2}\|",  # No capture group
                pattern_type="regex",
                tag_name="__CAPTURE__",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            rules = [rule]
            channel_name = "US| ESPN"
            category_name = "Sports"

            # Should handle gracefully
            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)

            # Should not add a tag (no capture group)
            assert len(tags) == 0


class TestEdgeCases:
    """Test edge cases and error conditions"""

    def test_extract_tags_empty_channel_name(self, app):
        """Test with empty channel name"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Test",
                pattern="US|",
                pattern_type="prefix",
                tag_name="US",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            tags, cleaned_name, _, _ = TagService.extract_tags("", "Sports", [rule])
            assert len(tags) == 0
            assert cleaned_name == ""

    def test_extract_tags_empty_category_name(self, app):
        """Test with empty category name"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Test",
                pattern="SPORTS",
                pattern_type="contains",
                tag_name="SPORTS",
                source="category_name",
                remove_from_name=False,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            tags, cleaned_name, _, _ = TagService.extract_tags("ESPN", "", [rule])
            # Should not find tag from category
            assert "SPORTS" not in tags

    def test_extract_tags_no_rules(self, app):
        """Test extraction with no rules"""
        with app.app_context():
            tags, cleaned_name, _, _ = TagService.extract_tags("US| ESPN 4K", "Sports", [])
            assert len(tags) == 0
            assert cleaned_name == "US| ESPN 4K"

    def test_extract_tags_invalid_regex_pattern(self, app):
        """Test with invalid regex pattern"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Bad regex",
                pattern=r"[invalid",  # Invalid regex
                pattern_type="regex",
                tag_name="TEST",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            # Should handle gracefully and not crash
            tags, cleaned_name, _, _ = TagService.extract_tags("ESPN", "Sports", [rule])
            assert len(tags) == 0

    def test_normalize_tag_name_empty_after_normalization(self, app):
        """Test tag normalization that results in empty string"""
        with app.app_context():
            # Single character tags are filtered out
            result = TagService.normalize_tag_name("a")
            assert result == ""

    def test_normalize_tag_name_special_unicode(self, app):
        """Test normalization with various Unicode superscripts"""
        with app.app_context():
            assert TagService.normalize_tag_name("ᴿᴬᵂ") == "RAW"
            assert TagService.normalize_tag_name("⁶⁰ᶠᵖˢ") == "60FPS"
            # Note: ᴴ is not in the superscript_map, so it gets removed by regex
            # This is expected behavior - only mapped unicode characters are converted
            result = TagService.normalize_tag_name("ᴴᴰ")
            assert result != ""  # Should not be empty but will lose unmapped chars

    def test_extract_tags_priority_order(self, app):
        """Test that rules are applied in priority order"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            # High priority rule that removes the text and creates a tag
            rule_high = TagRule(
                ruleset_id=ruleset.id,
                name="High priority",
                pattern="4K",
                pattern_type="contains",
                tag_name="4K",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )

            # Low priority rule that searches for a different pattern
            rule_low = TagRule(
                ruleset_id=ruleset.id,
                name="Low priority",
                pattern="ESPN",
                pattern_type="contains",
                tag_name="SPORTS",
                source="channel_name",
                remove_from_name=False,
                priority=20,
            )

            db.session.add(rule_high)
            db.session.add(rule_low)
            db.session.commit()

            tags, cleaned_name, _, _ = TagService.extract_tags("ESPN 4K", "Sports", [rule_high, rule_low])

            # Both rules should match their patterns
            assert "4K" in tags
            assert "SPORTS" in tags
            # The 4K text should be removed from cleaned name
            assert "4K" not in cleaned_name
            assert "ESPN" in cleaned_name

    def test_match_pattern_with_empty_pattern(self, app):
        """Test pattern matching with empty pattern"""
        with app.app_context():
            matched, result = TagService._match_pattern("text", "", "prefix")
            assert matched is False

    def test_match_pattern_with_empty_text(self, app):
        """Test pattern matching with empty text"""
        with app.app_context():
            matched, result = TagService._match_pattern("", "pattern", "prefix")
            assert matched is False

    def test_extract_tags_with_unicode_channel_name(self, app):
        """Test extraction with Unicode characters in channel name"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="RAW badge",
                pattern="ᴿᴬᵂ",
                pattern_type="contains",
                tag_name="RAW",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            channel_name = "US| ESPN ᴿᴬᵂ"
            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, "Sports", [rule])

            assert "RAW" in tags
            assert "ᴿᴬᵂ" not in cleaned_name

    def test_extract_tags_multiple_matches_stops_at_first(self, app):
        """Test that rule stops matching after first hit per rule"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="US everywhere",
                pattern="US",
                pattern_type="contains",
                tag_name="US",
                source="channel_name",
                remove_from_name=True,
                priority=10,
            )
            db.session.add(rule)
            db.session.commit()

            channel_name = "US ESPN US Network"
            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, "Sports", [rule])

            # Tag created once even though US appears twice
            assert "US" in tags
            # Only first occurrence removed (per break statement in code)
            assert cleaned_name.count("US") >= 1


class TestProcessAccountTags:
    """Test process_account_tags() integration method"""

    def test_process_account_tags_not_found(self, app):
        """Test processing tags for nonexistent account"""
        with app.app_context():
            result = TagService.process_account_tags(99999)
            assert result["success"] is False
            assert "not found" in result["error"].lower()

    def test_process_account_tags_no_channels(self, app, sample_account):
        """Test processing tags for account with no synced channels"""
        with app.app_context():
            result = TagService.process_account_tags(sample_account)
            assert result["success"] is False
            assert "not synced" in result["error"].lower()

    def test_process_account_tags_basic(self, app, sample_account, sample_ruleset):
        """Test basic tag processing for channels"""
        from models import Category, Channel

        with app.app_context():
            # Create a test category
            category = Category(account_id=sample_account, category_id=1, category_name="Sports")
            db.session.add(category)
            db.session.flush()

            # Create test channels
            channels = [
                Channel(
                    account_id=sample_account,
                    stream_id=1,
                    stream_type="live",
                    name="US| ESPN 4K",
                    category_id=category.id,
                    is_active=True,
                ),
                Channel(
                    account_id=sample_account,
                    stream_id=2,
                    stream_type="live",
                    name="CNN News",
                    category_id=category.id,
                    is_active=True,
                ),
            ]
            for ch in channels:
                db.session.add(ch)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(sample_account)

            assert result["success"] is True
            assert result["processed"] == 2
            assert result["tags_created"] > 0
            assert "4K" in result["tag_counts"]
            assert result["unique_tags"] >= 2

    def test_process_account_tags_updates_cleaned_names(self, app, sample_account, sample_ruleset):
        """Test that cleaned names are updated in database"""
        from models import Category, Channel

        with app.app_context():
            # Create category and channel
            category = Category(account_id=sample_account, category_id=1, category_name="News")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=sample_account,
                stream_id=1,
                stream_type="live",
                name="US| CNN Breaking News",
                category_id=category.id,
                is_active=True,
                cleaned_name="",  # Initially empty
            )
            db.session.add(channel)
            db.session.commit()

            # Process tags
            TagService.process_account_tags(sample_account)

            # Verify cleaned name was updated
            updated_channel = db.session.get(Channel, 1)
            assert updated_channel.cleaned_name != ""
            assert "US|" not in updated_channel.cleaned_name

    def test_process_account_tags_creates_tags(self, app, sample_account, sample_ruleset):
        """Test that Tag records are created"""
        from models import Category, Channel, Tag

        with app.app_context():
            category = Category(account_id=sample_account, category_id=1, category_name="Sports")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=sample_account,
                stream_id=1,
                stream_type="live",
                name="US| ESPN 4K",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Count tags before
            tags_before = Tag.query.count()

            # Process
            TagService.process_account_tags(sample_account)

            # Should have created new tags
            tags_after = Tag.query.count()
            assert tags_after > tags_before

            # Verify US and 4K tags exist
            us_tag = Tag.query.filter_by(name="US").first()
            four_k_tag = Tag.query.filter_by(name="4K").first()
            assert us_tag is not None
            assert four_k_tag is not None

    def test_process_account_tags_creates_channel_tags(self, app, sample_account, sample_ruleset):
        """Test that ChannelTag associations are created"""
        from models import Category, Channel, ChannelTag

        with app.app_context():
            category = Category(account_id=sample_account, category_id=1, category_name="Sports")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=sample_account,
                stream_id=1,
                stream_type="live",
                name="US| ESPN",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Process tags
            TagService.process_account_tags(sample_account)

            # Check that ChannelTag associations exist
            channel_tags = ChannelTag.query.filter_by(
                account_id=sample_account, stream_id=1, source=ChannelTag.SOURCE_EXTRACTION
            ).all()
            assert len(channel_tags) > 0

    def test_process_account_tags_skips_inactive_channels(self, app, sample_account, sample_ruleset):
        """Test that inactive channels are not processed"""
        from models import Category, Channel

        with app.app_context():
            category = Category(account_id=sample_account, category_id=1, category_name="Sports")
            db.session.add(category)
            db.session.flush()

            # Create one active and one inactive channel
            active = Channel(
                account_id=sample_account,
                stream_id=1,
                stream_type="live",
                name="US| ESPN",
                category_id=category.id,
                is_active=True,
            )
            inactive = Channel(
                account_id=sample_account,
                stream_id=2,
                stream_type="live",
                name="US| NFL",
                category_id=category.id,
                is_active=False,
            )
            db.session.add(active)
            db.session.add(inactive)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(sample_account)

            # Should only process the active channel
            assert result["processed"] == 1

    def test_process_account_tags_handles_no_category(self, app, sample_account, sample_ruleset):
        """Test processing channels without category"""
        from models import Channel

        with app.app_context():
            # Create channel without category
            channel = Channel(
                account_id=sample_account,
                stream_id=1,
                stream_type="live",
                name="US| ESPN",
                category_id=None,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Should not crash
            result = TagService.process_account_tags(sample_account)

            assert result["success"] is True
            assert result["processed"] == 1

    def test_process_account_tags_counts_tag_occurrences(self, app, sample_account, sample_ruleset):
        """Test that tag_counts tracks how many channels have each tag"""
        from models import Category, Channel

        with app.app_context():
            category = Category(account_id=sample_account, category_id=1, category_name="Sports")
            db.session.add(category)
            db.session.flush()

            # Create multiple channels with same tag
            for i in range(3):
                channel = Channel(
                    account_id=sample_account,
                    stream_id=i + 1,
                    stream_type="live",
                    name="US| Channel " + str(i),
                    category_id=category.id,
                    is_active=True,
                )
                db.session.add(channel)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(sample_account)

            # US tag should appear 3 times
            assert result["tag_counts"]["US"] == 3


class TestExtractTagsIntegration:
    """Integration tests for tag extraction with real rulesets"""

    def test_extract_real_world_channel_names(self, app, sample_ruleset):
        """Test extraction with realistic channel names"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            # Test cases with real-world examples (only tags that are in sample_ruleset)
            # sample_ruleset contains: US|, ᴿᴬᵂ (RAW), and 4K regex patterns
            test_cases = [
                ("US| ESPN ᴿᴬᵂ", "Sports", {"US", "RAW"}),
                ("ESPN 4K UHD", "Sports", {"4K"}),
                ("Discovery Network", "News", set()),  # No matching patterns
            ]

            for channel_name, category_name, expected_tags in test_cases:
                tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, category_name, rules)
                assert tags == expected_tags, f"Expected {expected_tags} but got {tags} for channel {channel_name}"

    def test_extract_tags_with_location_and_callsign(self, app):
        """Test extraction of location and callsign from full patterns"""
        with app.app_context():
            # Create ruleset with location and callsign rules
            ruleset = RuleSet(name="Location Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rules_data = [
                {
                    "ruleset_id": ruleset.id,
                    "name": "Location",
                    "pattern": r"\[([^\]]+)\]",
                    "pattern_type": "regex",
                    "tag_name": "__LOCATION__",
                    "source": "channel_name",
                    "remove_from_name": True,
                    "priority": 10,
                },
                {
                    "ruleset_id": ruleset.id,
                    "name": "Callsign",
                    "pattern": r"\(([^\)]+)\)",
                    "pattern_type": "regex",
                    "tag_name": "__CALLSIGN__",
                    "source": "channel_name",
                    "remove_from_name": True,
                    "priority": 20,
                },
            ]

            for rd in rules_data:
                rule = TagRule(**rd)
                db.session.add(rule)
            db.session.commit()

            rules = TagRule.query.filter_by(ruleset_id=ruleset.id).all()

            # Test with location and callsign
            channel_name = "WGBH Boston [MA] (WGBH)"
            tags, cleaned_name, _, _ = TagService.extract_tags(channel_name, "News", rules)

            assert "MA" in tags
            assert "WGBH" in tags
            assert "[" not in cleaned_name
            assert "(" not in cleaned_name
