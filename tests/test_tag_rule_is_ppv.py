"""
Tests for tag rule is_ppv field functionality
"""

from models import Account, Category, Channel, RuleSet, TagRule, db
from services.tag_service import TagService


class TestTagRuleIsPpv:
    """Test suite for set_is_ppv field in tag rules"""

    def test_extract_tags_set_is_ppv_keep(self, app):
        """Test that 'keep' directive doesn't change is_ppv"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Test Rule",
                pattern="Sports",
                pattern_type="contains",
                tag_name="SPORTS",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="keep",
            )
            db.session.add(rule)
            db.session.commit()

            tags, _, _, is_ppv_directive = TagService.extract_tags("ESPN", "Sports", [rule])
            assert is_ppv_directive == "keep"
            assert "SPORTS" in tags

    def test_extract_tags_set_is_ppv_true(self, app):
        """Test that set_true directive is returned"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="PPV Marker",
                pattern="PPV",
                pattern_type="contains",
                tag_name="PPV",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="set_true",
            )
            db.session.add(rule)
            db.session.commit()

            tags, _, _, is_ppv_directive = TagService.extract_tags("Boxing Match", "PPV Events", [rule])
            assert is_ppv_directive == "set_true"

    def test_extract_tags_set_is_ppv_false(self, app):
        """Test that set_false directive is returned"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Not PPV",
                pattern="Bally Sports|FanDuel Sports",
                pattern_type="regex",
                tag_name="REGIONAL",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="set_false",
            )
            db.session.add(rule)
            db.session.commit()

            tags, _, _, is_ppv_directive = TagService.extract_tags("Wild vs Avalanche", "Bally Sports PPV", [rule])
            assert is_ppv_directive == "set_false"

    def test_extract_tags_first_match_wins(self, app):
        """Test that first matching rule with set_true/set_false wins"""
        with app.app_context():
            ruleset = RuleSet(name="Test", enabled=True, priority=100)
            db.session.add(ruleset)
            db.session.flush()

            # First rule (higher priority - lower number) sets false
            rule1 = TagRule(
                ruleset_id=ruleset.id,
                name="Regional Override",
                pattern="Bally",
                pattern_type="contains",
                tag_name="REGIONAL",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="set_false",
            )

            # Second rule would set true but shouldn't win
            rule2 = TagRule(
                ruleset_id=ruleset.id,
                name="PPV Category",
                pattern="PPV",
                pattern_type="contains",
                tag_name="PPV_CAT",
                source="category_name",
                remove_from_name=False,
                priority=20,
                set_is_ppv="set_true",
            )

            db.session.add_all([rule1, rule2])
            db.session.commit()

            # Sort by priority as TagService does
            rules = sorted([rule1, rule2], key=lambda r: r.priority)

            tags, _, _, is_ppv_directive = TagService.extract_tags("Game", "Bally Sports PPV", rules)
            # First matching rule (rule1) should win
            assert is_ppv_directive == "set_false"

    def test_process_account_tags_sets_is_ppv_true(self, app):
        """Test that process_account_tags applies set_true directive"""
        with app.app_context():
            account = Account(name="Test", server="example.com", enabled=True)
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="PPV Events",
                is_active=True,
            )
            db.session.add(category)
            db.session.flush()

            # Channel not marked as PPV initially
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC Fight",
                category_id=category.id,
                is_active=True,
                is_ppv=False,
            )
            db.session.add(channel)

            ruleset = RuleSet(name="Test", enabled=True, priority=100, is_default=True)
            db.session.add(ruleset)
            db.session.flush()

            rule = TagRule(
                ruleset_id=ruleset.id,
                name="PPV Marker",
                pattern="PPV",
                pattern_type="contains",
                tag_name="PPV",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="set_true",
            )
            db.session.add(rule)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(account.id)

            assert result["success"] is True
            assert result["is_ppv_changed"] == 1

            # Verify channel is now marked as PPV
            db.session.refresh(channel)
            assert channel.is_ppv is True

    def test_process_account_tags_sets_is_ppv_false(self, app):
        """Test that process_account_tags applies set_false directive"""
        with app.app_context():
            account = Account(name="Test", server="example.com", enabled=True)
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Bally Sports PPV",
                is_active=True,
                is_ppv=True,  # Category marked as PPV
            )
            db.session.add(category)
            db.session.flush()

            # Channel inherits PPV from category
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="Wild vs Avalanche",
                category_id=category.id,
                is_active=True,
                is_ppv=True,  # Marked as PPV from category
            )
            db.session.add(channel)

            ruleset = RuleSet(name="Test", enabled=True, priority=100, is_default=True)
            db.session.add(ruleset)
            db.session.flush()

            # Rule to un-mark Bally Sports channels as PPV
            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Bally Not PPV",
                pattern="Bally",
                pattern_type="contains",
                tag_name="REGIONAL",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="set_false",
            )
            db.session.add(rule)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(account.id)

            assert result["success"] is True
            assert result["is_ppv_changed"] == 1

            # Verify channel is no longer marked as PPV
            db.session.refresh(channel)
            assert channel.is_ppv is False

    def test_process_account_tags_keep_doesnt_change(self, app):
        """Test that 'keep' directive doesn't change is_ppv"""
        with app.app_context():
            account = Account(name="Test", server="example.com", enabled=True)
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Sports",
                is_active=True,
            )
            db.session.add(category)
            db.session.flush()

            # Channel marked as PPV
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="ESPN",
                category_id=category.id,
                is_active=True,
                is_ppv=True,
            )
            db.session.add(channel)

            ruleset = RuleSet(name="Test", enabled=True, priority=100, is_default=True)
            db.session.add(ruleset)
            db.session.flush()

            # Rule with keep directive
            rule = TagRule(
                ruleset_id=ruleset.id,
                name="Sports Tag",
                pattern="Sports",
                pattern_type="contains",
                tag_name="SPORTS",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="keep",
            )
            db.session.add(rule)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(account.id)

            assert result["success"] is True
            assert result["is_ppv_changed"] == 0

            # Verify channel is_ppv unchanged
            db.session.refresh(channel)
            assert channel.is_ppv is True

    def test_process_account_tags_no_change_if_already_correct(self, app):
        """Test that is_ppv_changed only counts actual changes"""
        with app.app_context():
            account = Account(name="Test", server="example.com", enabled=True)
            db.session.add(account)
            db.session.flush()

            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="PPV Events",
                is_active=True,
            )
            db.session.add(category)
            db.session.flush()

            # Channel already marked as PPV
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC Fight",
                category_id=category.id,
                is_active=True,
                is_ppv=True,
            )
            db.session.add(channel)

            ruleset = RuleSet(name="Test", enabled=True, priority=100, is_default=True)
            db.session.add(ruleset)
            db.session.flush()

            # Rule to set PPV true (but it's already true)
            rule = TagRule(
                ruleset_id=ruleset.id,
                name="PPV Marker",
                pattern="PPV",
                pattern_type="contains",
                tag_name="PPV",
                source="category_name",
                remove_from_name=False,
                priority=10,
                set_is_ppv="set_true",
            )
            db.session.add(rule)
            db.session.commit()

            # Process tags
            result = TagService.process_account_tags(account.id)

            assert result["success"] is True
            assert result["is_ppv_changed"] == 0  # No change needed

            # Verify channel is still PPV
            db.session.refresh(channel)
            assert channel.is_ppv is True
