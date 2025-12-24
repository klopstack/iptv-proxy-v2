"""
Tests for TagService
"""

import os

import pytest

os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import app, db
from models import Account, AccountRuleSet, RuleSet, TagRule
from services.tag_service import TagService


@pytest.fixture
def test_app():
    """Test app fixture with database"""
    app.config["TESTING"] = True
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"

    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def sample_ruleset(test_app):
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
def sample_account(test_app, sample_ruleset):
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

    def test_extract_tags_with_prefix(self, test_app, sample_ruleset):
        """Test extracting tags from prefix pattern"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            channel_name = "US| CNN News"
            category_name = "News"

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert cleaned_name == "CNN News"

    def test_extract_tags_with_multiple_patterns(self, test_app, sample_ruleset):
        """Test extracting multiple tags"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            channel_name = "US| ESPN 4K ᴿᴬᵂ"
            category_name = "Sports"

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "RAW" in tags
            assert "4K" in tags
            assert "ESPN" in cleaned_name

    def test_extract_tags_with_regex(self, test_app, sample_ruleset):
        """Test regex pattern matching"""
        with app.app_context():
            rules = TagRule.query.filter_by(ruleset_id=sample_ruleset).all()

            channel_name = "Discovery 4K UHD"
            category_name = "Documentary"

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "4K" in tags

    def test_normalize_tag_name(self, test_app):
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

    def test_get_rules_for_account_with_assigned_ruleset(self, test_app, sample_account, sample_ruleset):
        """Test getting rules for account with assigned ruleset"""
        with app.app_context():
            account = db.session.get(Account, sample_account)
            rules = TagService.get_rules_for_account(account)

            # Should have 3 rules from the test ruleset
            assert len(rules) == 3
            assert all(isinstance(rule, TagRule) for rule in rules)

    def test_get_rules_for_account_with_default_ruleset(self, test_app):
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

    def test_get_rules_for_account_no_rules(self, test_app):
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

    def test_match_pattern_prefix(self, test_app):
        """Test prefix pattern matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("US| Channel", "US|", "prefix")
            assert matched is True
            assert match_text == "US|"

            matched, match_text = TagService._match_pattern("Channel US|", "US|", "prefix")
            assert matched is False

    def test_match_pattern_suffix(self, test_app):
        """Test suffix pattern matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("Channel HD", "HD", "suffix")
            assert matched is True
            assert match_text == "HD"

            matched, match_text = TagService._match_pattern("HD Channel", "HD", "suffix")
            assert matched is False

    def test_match_pattern_contains(self, test_app):
        """Test contains pattern matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("Channel 4K HD", "4K", "contains")
            assert matched is True
            assert match_text == "4K"

    def test_match_pattern_regex(self, test_app):
        """Test regex pattern matching"""
        with app.app_context():
            matched, match_obj = TagService._match_pattern("Channel 4K", r"\b4K\b", "regex")
            assert matched is True
            # Regex returns match object for capture group access
            assert match_obj.group() == "4K"

            # Should not match 4K in middle of word
            matched, match_obj = TagService._match_pattern("Channel X4KUHD", r"\b4K\b", "regex")
            assert matched is False

    def test_match_pattern_case_insensitive(self, test_app):
        """Test case-insensitive matching"""
        with app.app_context():
            matched, match_text = TagService._match_pattern("us| Channel", "US|", "prefix")
            assert matched is True


class TestDefaultRulesetCreation:
    """Test default ruleset creation"""

    def test_create_default_ruleset(self, test_app):
        """Test creating default ruleset"""
        with app.app_context():
            ruleset = TagService.create_default_ruleset(db.session)

            assert ruleset is not None
            assert ruleset.name == "Default"
            assert ruleset.is_default is True
            assert len(ruleset.rules) > 0

    def test_create_default_ruleset_idempotent(self, test_app):
        """Test that creating default ruleset twice returns same ruleset"""
        with app.app_context():
            ruleset1 = TagService.create_default_ruleset(db.session)
            ruleset2 = TagService.create_default_ruleset(db.session)

            assert ruleset1.id == ruleset2.id


class TestSpecialTagTypes:
    """Test special tag behaviors like __LOCATION__, __CALLSIGN__, __CLEANUP__"""

    def test_location_extraction(self, test_app):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "[" not in cleaned_name
            assert "]" not in cleaned_name

    def test_cleanup_tag(self, test_app):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            # Should not create a tag
            assert "__CLEANUP__" not in tags
            # Should remove the pipe
            assert "|" not in cleaned_name


class TestTagRuleReplacement:
    """Test tag rule replacement functionality"""

    def test_simple_replacement(self, test_app, sample_ruleset):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "DISTRICT" in cleaned_name
            assert "DISCTRICT" not in cleaned_name
            assert cleaned_name == "ABC 7 DISTRICT OF COLUMBIA"

    def test_replacement_case_insensitive(self, test_app, sample_ruleset):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "DISTRICT" in cleaned_name
            assert "DISCTRICT" not in cleaned_name

    def test_replacement_with_tag(self, test_app, sample_ruleset):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "HD" in tags
            assert "ESPN HD" == cleaned_name.strip()

    def test_replacement_with_regex(self, test_app, sample_ruleset):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            # Multiple spaces should be reduced
            assert "  " not in cleaned_name

    def test_no_replacement_when_remove_false(self, test_app, sample_ruleset):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            # Tag should be added
            assert "ESPN" in tags
            # But name should NOT be modified because remove_from_name is False
            assert cleaned_name == "ESPN 4K"

    def test_replacement_none_means_remove(self, test_app, sample_ruleset):
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

            tags, cleaned_name = TagService.extract_tags(channel_name, category_name, rules)

            assert "US" in tags
            assert "US|" not in cleaned_name
            assert cleaned_name.strip() == "CNN"
