"""Tests for shared route serializers used by API routes and config export."""

import json

from models import (
    Credential,
    EpgChannelNameMapping,
    EpgExclusionPattern,
    EpgMatchRule,
    EpgMatchRuleSet,
    EpgSource,
    FccMatchChannelPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    RuleSet,
    TagRule,
    db,
)
from services.serializers.credentials import serialize_credential
from services.serializers.epg_match import (
    serialize_epg_channel_name_mapping,
    serialize_epg_exclusion_pattern,
    serialize_epg_match_rule,
    serialize_epg_ruleset,
    serialize_ruleset,
    serialize_tag_rule,
)
from services.serializers.epg_sources import serialize_epg_source
from services.serializers.fcc import serialize_fcc_channel_pattern, serialize_fcc_network, serialize_fcc_strategy


class TestFccSerializers:
    def test_serialize_fcc_network_include_id(self, app):
        with app.app_context():
            network = FccMatchNetwork(
                name="ABC",
                display_name="ABC",
                fcc_affiliation_pattern="%ABC%",
                tag_patterns=json.dumps(["ABC"]),
                enabled=True,
                priority=10,
            )
            db.session.add(network)
            db.session.commit()

            data = serialize_fcc_network(network)
            assert data["id"] == network.id
            assert data["tag_patterns"] == ["ABC"]

    def test_serialize_fcc_network_omit_id_for_export(self, app):
        with app.app_context():
            network = FccMatchNetwork(
                name="NBC",
                display_name="NBC",
                fcc_affiliation_pattern="%NBC%",
                enabled=True,
                priority=20,
            )
            db.session.add(network)
            db.session.commit()

            data = serialize_fcc_network(network, include_id=False)
            assert "id" not in data
            assert data["name"] == "NBC"


class TestEpgMatchSerializers:
    def test_serialize_epg_match_rule_for_routes(self, app):
        with app.app_context():
            ruleset = EpgMatchRuleSet(name="EPG Rules", enabled=True, priority=1)
            db.session.add(ruleset)
            db.session.flush()
            rule = EpgMatchRule(
                ruleset_id=ruleset.id,
                name="Exact",
                match_type="exact_name",
                source="cleaned_name",
                action="map_epg",
                priority=5,
                enabled=True,
            )
            db.session.add(rule)
            db.session.commit()

            data = serialize_epg_match_rule(rule)
            assert data["id"] == rule.id
            assert data["ruleset_id"] == ruleset.id

    def test_serialize_epg_ruleset_for_export(self, app):
        with app.app_context():
            ruleset = EpgMatchRuleSet(name="Export Rules", enabled=True, priority=1)
            db.session.add(ruleset)
            db.session.flush()
            db.session.add(
                EpgMatchRule(
                    ruleset_id=ruleset.id,
                    name="Rule A",
                    match_type="exact_name",
                    source="cleaned_name",
                    action="map_epg",
                    priority=1,
                    enabled=True,
                )
            )
            db.session.commit()

            data = serialize_epg_ruleset(ruleset)
            assert len(data["rules"]) == 1
            assert "id" not in data["rules"][0]
            assert "ruleset_id" not in data["rules"][0]


class TestTagRulesetSerializers:
    def test_serialize_ruleset_matches_tag_rule_helper(self, app):
        with app.app_context():
            ruleset = RuleSet(name="Tags", enabled=True, priority=1)
            db.session.add(ruleset)
            db.session.flush()
            rule = TagRule(
                ruleset_id=ruleset.id,
                name="US Prefix",
                pattern="US|",
                pattern_type="prefix",
                tag_name="US",
                source="channel_name",
                remove_from_name=True,
                priority=10,
                enabled=True,
            )
            db.session.add(rule)
            db.session.commit()

            exported = serialize_ruleset(ruleset)
            assert exported["rules"] == [serialize_tag_rule(rule)]


class TestEpgConfigSerializers:
    def test_serialize_exclusion_pattern_omit_id(self, app):
        with app.app_context():
            pattern = EpgExclusionPattern(
                name="PPV",
                pattern_type="category_name",
                pattern="PPV",
                enabled=True,
                priority=1,
            )
            db.session.add(pattern)
            db.session.commit()

            data = serialize_epg_exclusion_pattern(pattern, include_id=False)
            assert "id" not in data
            assert data["pattern"] == "PPV"

    def test_serialize_channel_name_mapping_includes_timestamps_with_id(self, app):
        with app.app_context():
            mapping = EpgChannelNameMapping(
                name="HD Removal",
                old_name="HD",
                new_name="",
                match_type="contains",
                priority=1,
                enabled=True,
            )
            db.session.add(mapping)
            db.session.commit()

            with_id = serialize_epg_channel_name_mapping(mapping)
            without_id = serialize_epg_channel_name_mapping(mapping, include_id=False)
            assert "created_at" in with_id
            assert "created_at" not in without_id


class TestEpgSourceSerializer:
    def test_serialize_epg_source_includes_mapping_count(self, app, test_account):
        with app.app_context():
            source = EpgSource(
                name="Guide",
                source_type="xmltv_url",
                url="http://example.com/epg.xml",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()

            data = serialize_epg_source(source, mapping_count=3)
            assert data["used_mapping_count"] == 3
            assert data["name"] == "Guide"


class TestCredentialSerializer:
    def test_serialize_credential_defaults(self, app, test_account):
        with app.app_context():
            credential = Credential(
                account_id=test_account,
                username="user1",
                password="secret",
                enabled=True,
            )
            db.session.add(credential)
            db.session.commit()

            data = serialize_credential(credential)
            assert data["username"] == "user1"
            assert data["max_connections"] == 1
            assert data["active_connections"] == 0


class TestFccChannelAndStrategySerializers:
    def test_serialize_fcc_channel_pattern(self, app):
        with app.app_context():
            pattern = FccMatchChannelPattern(
                name="Major",
                pattern=r"(\\d+)",
                pattern_type="regex",
                enabled=True,
                priority=5,
            )
            db.session.add(pattern)
            db.session.commit()

            data = serialize_fcc_channel_pattern(pattern, include_id=False)
            assert data["name"] == "Major"
            assert "id" not in data

    def test_serialize_fcc_strategy(self, app):
        with app.app_context():
            strategy = FccMatchStrategy(
                name="Full Match",
                strategy_type="full",
                enabled=True,
                priority=1,
            )
            db.session.add(strategy)
            db.session.commit()

            data = serialize_fcc_strategy(strategy)
            assert data["id"] == strategy.id
            assert data["strategy_type"] == "full"
