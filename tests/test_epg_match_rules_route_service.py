"""Unit tests for EpgMatchRulesRouteService (no Flask request context)."""

from unittest.mock import patch

from models import Account, Category, Channel, EpgChannelNameMapping, EpgMatchRuleSet, db
from services.epg.match_rules.route_service import (
    DEFAULT_EPG_MATCH_RULES,
    DEFAULT_EXCLUSION_PATTERNS,
    MATCH_TYPES_INFO,
    EpgMatchRulesRouteService,
)


class TestMatchTypesInfo:
    def test_get_match_types_returns_static_catalog(self):
        data = EpgMatchRulesRouteService.get_match_types()
        assert data == MATCH_TYPES_INFO
        assert any(m["value"] == "provider_id" for m in data["match_types"])


class TestRulesetCrud:
    def test_create_ruleset_duplicate_name(self, app):
        with app.app_context():
            db.session.add(EpgMatchRuleSet(name="Existing", description="", enabled=True, priority=100))
            db.session.commit()
            payload, error, status = EpgMatchRulesRouteService.create_ruleset({"name": "Existing"})
            assert payload is None
            assert status == 409
            assert "already exists" in error

    def test_list_rulesets_includes_assigned_accounts(self, app):
        with app.app_context():
            account = Account(name="Acct", server="http://x", username="u", password="p")
            ruleset = EpgMatchRuleSet(name="RS1", description="", enabled=True, priority=1)
            db.session.add_all([account, ruleset])
            db.session.flush()
            from models import AccountEpgMatchRuleSet

            db.session.add(AccountEpgMatchRuleSet(account_id=account.id, ruleset_id=ruleset.id, priority=10))
            db.session.commit()
            rows = EpgMatchRulesRouteService.list_rulesets()
            rs = next(r for r in rows if r["name"] == "RS1")
            assert rs["assigned_accounts"] == [{"id": account.id, "name": "Acct"}]


class TestPreviewChannelNameMapping:
    def test_missing_old_name(self, app):
        with app.app_context():
            payload, status = EpgMatchRulesRouteService.preview_channel_name_mapping({})
            assert status == 200
            assert payload["error"] == "old_name is required"

    def test_invalid_regex(self, app):
        with app.app_context():
            payload, status = EpgMatchRulesRouteService.preview_channel_name_mapping(
                {"old_name": "[", "match_type": "regex"}
            )
            assert status == 200
            assert "Invalid regex" in payload["error"]

    def test_contains_match(self, app):
        with app.app_context():
            account = Account(name="A", server="http://x", username="u", password="p")
            db.session.add(account)
            db.session.flush()
            db.session.add(
                Channel(
                    account_id=account.id,
                    stream_id="1",
                    name="ESPN HD",
                    cleaned_name="ESPN HD",
                    is_active=True,
                )
            )
            db.session.commit()
            payload, status = EpgMatchRulesRouteService.preview_channel_name_mapping(
                {
                    "old_name": "ESPN",
                    "new_name": "ESPN US",
                    "match_type": "contains",
                    "account_id": account.id,
                }
            )
            assert status == 200
            assert payload["total_count"] == 1
            assert payload["matches"][0]["transformed_name"] == "ESPN US HD"


class TestPreviewExclusionPattern:
    def test_empty_pattern(self, app):
        with app.app_context():
            payload = EpgMatchRulesRouteService.preview_exclusion_pattern({})
            assert payload["error"] == "Pattern is required"

    def test_invalid_regex(self, app):
        with app.app_context():
            payload = EpgMatchRulesRouteService.preview_exclusion_pattern({"pattern": "[", "is_regex": True})
            assert "Invalid regex" in payload["error"]


class TestPreviewRulePattern:
    def test_invalid_main_regex(self, app):
        with app.app_context():
            payload = EpgMatchRulesRouteService.preview_rule_pattern({"match_type": "regex", "pattern": "("})
            assert "Invalid regex pattern" in payload["error"]

    def test_regex_channel_name_match(self, app):
        with app.app_context():
            account = Account(name="A", server="http://x", username="u", password="p")
            category = Category(account_id=1, category_id="1", category_name="Sports", is_active=True)
            db.session.add(account)
            db.session.flush()
            category.account_id = account.id
            db.session.add(category)
            db.session.flush()
            db.session.add(
                Channel(
                    account_id=account.id,
                    stream_id="1",
                    name="ESPN",
                    cleaned_name="ESPN",
                    category_id=category.id,
                    is_active=True,
                )
            )
            db.session.commit()
            payload = EpgMatchRulesRouteService.preview_rule_pattern(
                {
                    "match_type": "regex",
                    "source": "channel_name",
                    "pattern": "ESPN",
                    "account_id": account.id,
                }
            )
            assert payload["total_count"] == 1
            assert payload["matches"][0]["name"] == "ESPN"


class TestCreateDefaults:
    @patch("services.epg.match_rules.route_service.cache_service")
    def test_create_default_epg_match_ruleset(self, _cache, app):
        with app.app_context():
            payload, status = EpgMatchRulesRouteService.create_default_epg_match_ruleset()
            assert status == 200
            assert payload["success"] is True
            assert payload["rule_count"] == len(DEFAULT_EPG_MATCH_RULES)

    @patch("services.epg.match_rules.route_service.cache_service")
    def test_create_default_epg_match_ruleset_idempotent(self, _cache, app):
        with app.app_context():
            EpgMatchRulesRouteService.create_default_epg_match_ruleset()
            payload, status = EpgMatchRulesRouteService.create_default_epg_match_ruleset()
            assert status == 400
            assert payload["success"] is False

    @patch("services.epg.match_rules.route_service.cache_service")
    def test_create_default_exclusion_patterns(self, _cache, app):
        with app.app_context():
            payload = EpgMatchRulesRouteService.create_default_exclusion_patterns()
            assert payload["patterns_created"] == len(DEFAULT_EXCLUSION_PATTERNS)
            assert payload["patterns_skipped"] == 0

    @patch("services.epg.match_rules.route_service.cache_service")
    def test_create_default_exclusion_patterns_skip_existing(self, _cache, app):
        with app.app_context():
            EpgMatchRulesRouteService.create_default_exclusion_patterns()
            payload = EpgMatchRulesRouteService.create_default_exclusion_patterns()
            assert payload["patterns_created"] == 0
            assert payload["patterns_skipped"] == len(DEFAULT_EXCLUSION_PATTERNS)


class TestNameMappingCrud:
    @patch("services.epg.match_rules.route_service.clear_fcc_pattern_cache")
    @patch("services.epg.match_rules.route_service.cache_service")
    def test_create_name_mapping(self, _cache, _fcc, app):
        with app.app_context():
            data = EpgMatchRulesRouteService.create_name_mapping(
                {
                    "name": "Map1",
                    "old_name": "FOO",
                    "new_name": "BAR",
                }
            )
            assert data["old_name"] == "FOO"
            assert data["new_name"] == "BAR"
            row = EpgChannelNameMapping.query.filter_by(name="Map1").first()
            assert row is not None
