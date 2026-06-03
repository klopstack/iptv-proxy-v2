"""Unit tests for ConfigTransferService (no Flask request context)."""

import json

from models import Account, EpgMatchRule, EpgMatchRuleSet, FccMatchNetwork, Filter, RuleSet, TagRule, db
from services.config_transfer_service import ConfigTransferService


class TestConfigTransferServiceExport:
    def test_export_bundle_contains_expected_sections(self, app):
        with app.app_context():
            account = Account(name="Main Account", server="http://example.com", enabled=True)
            db.session.add(account)
            db.session.flush()

            db.session.add(
                Filter(
                    account_id=account.id,
                    name="Block Sports",
                    filter_type="category",
                    filter_action="blacklist",
                    filter_value="Sports",
                    enabled=True,
                )
            )

            ruleset = RuleSet(name="Tags A", description="Primary", enabled=True, priority=10)
            db.session.add(ruleset)
            db.session.flush()
            db.session.add(
                TagRule(
                    ruleset_id=ruleset.id,
                    name="US Prefix",
                    pattern="US|",
                    pattern_type="prefix",
                    tag_name="US",
                    source="both",
                    remove_from_name=True,
                    priority=10,
                    enabled=True,
                )
            )

            epg_ruleset = EpgMatchRuleSet(name="EPG A", description="EPG", enabled=True, priority=20)
            db.session.add(epg_ruleset)
            db.session.flush()
            db.session.add(
                EpgMatchRule(
                    ruleset_id=epg_ruleset.id,
                    name="Exact",
                    match_type="exact_name",
                    source="cleaned_name",
                    action="map_epg",
                    priority=5,
                    enabled=True,
                )
            )

            db.session.add(
                FccMatchNetwork(
                    name="ABC",
                    display_name="ABC",
                    fcc_affiliation_pattern="%ABC%",
                    tag_patterns=json.dumps(["ABC"]),
                    enabled=True,
                    priority=10,
                )
            )
            db.session.commit()

            payload = ConfigTransferService.export_bundle()
            assert payload["type"] == "iptv-proxy-config-bundle"
            assert len(payload["rulesets"]) == 1
            assert len(payload["rulesets"][0]["rules"]) == 1
            assert len(payload["filters"]) == 1
            assert len(payload["epg_match_rulesets"]) == 1
            assert len(payload["epg_match_rulesets"][0]["rules"]) == 1
            assert len(payload["fcc_patterns"]["networks"]) == 1

    def test_export_bundle_excludes_accounts_when_requested(self, app):
        with app.app_context():
            db.session.add(Account(name="Hidden", server="http://example.com", enabled=True))
            db.session.commit()

            payload = ConfigTransferService.export_bundle(include_accounts=False)
            assert payload["accounts"] == []


class TestConfigTransferServiceImport:
    def _sample_bundle(self, **options):
        return {
            "type": "iptv-proxy-config-bundle",
            "version": "1.0",
            "accounts": [
                {
                    "name": "Imported Account",
                    "server": "http://imported.example",
                    "enabled": True,
                }
            ],
            "rulesets": [
                {
                    "name": "Imported Ruleset",
                    "description": "Imported tag rules",
                    "enabled": True,
                    "priority": 100,
                    "rules": [
                        {
                            "name": "4K",
                            "pattern": " 4K",
                            "pattern_type": "suffix",
                            "tag_name": "4K",
                            "source": "channel_name",
                            "remove_from_name": False,
                            "priority": 20,
                            "enabled": True,
                        }
                    ],
                }
            ],
            "filters": [
                {
                    "account_name": "Imported Account",
                    "name": "Whitelist News",
                    "filter_type": "category",
                    "filter_action": "whitelist",
                    "filter_value": "News",
                    "enabled": True,
                }
            ],
            "account_ruleset_assignments": [
                {
                    "account_name": "Imported Account",
                    "ruleset_name": "Imported Ruleset",
                    "priority": 42,
                }
            ],
            "epg_match_rulesets": [
                {
                    "name": "Imported EPG Ruleset",
                    "description": "Imported epg",
                    "enabled": True,
                    "priority": 100,
                    "rules": [
                        {
                            "name": "Provider",
                            "match_type": "provider_id",
                            "source": "epg_channel_id",
                            "action": "map_epg",
                            "priority": 5,
                            "enabled": True,
                        }
                    ],
                }
            ],
            "account_epg_match_ruleset_assignments": [
                {
                    "account_name": "Imported Account",
                    "ruleset_name": "Imported EPG Ruleset",
                    "priority": 33,
                }
            ],
            "epg_exclusion_patterns": [],
            "epg_channel_name_mappings": [],
            "fcc_patterns": {
                "networks": [
                    {
                        "name": "NBC",
                        "display_name": "NBC",
                        "fcc_affiliation_pattern": "%NBC%",
                        "tag_patterns": ["NBC"],
                        "enabled": True,
                        "priority": 50,
                    }
                ],
                "channel_patterns": [],
                "location_patterns": [],
                "strategies": [],
                "country_suffixes": [],
                "quality_tags": [],
                "country_tags": [],
                "callsign_suffixes": [],
            },
            "options": options,
        }

    def test_import_bundle_creates_configuration(self, app):
        bundle = self._sample_bundle(overwrite=False, create_missing_accounts=True)

        with app.app_context():
            result = ConfigTransferService.import_bundle(
                bundle,
                overwrite=False,
                create_missing_accounts=True,
            )
            assert result["success"] is True

            account = Account.query.filter_by(name="Imported Account").first()
            assert account is not None
            assert Filter.query.filter_by(account_id=account.id).count() == 1

            ruleset = RuleSet.query.filter_by(name="Imported Ruleset").first()
            assert ruleset is not None
            assert TagRule.query.filter_by(ruleset_id=ruleset.id).count() == 1

            epg_ruleset = EpgMatchRuleSet.query.filter_by(name="Imported EPG Ruleset").first()
            assert epg_ruleset is not None
            assert EpgMatchRule.query.filter_by(ruleset_id=epg_ruleset.id).count() == 1

            nbc = FccMatchNetwork.query.filter_by(name="NBC").first()
            assert nbc is not None
            assert json.loads(nbc.tag_patterns) == ["NBC"]

    def test_import_bundle_overwrite_updates_existing(self, app):
        with app.app_context():
            db.session.add(RuleSet(name="Shared", description="Old", enabled=True, priority=100))
            db.session.add(
                FccMatchNetwork(
                    name="FOX",
                    display_name="Old",
                    fcc_affiliation_pattern="%OLD%",
                    tag_patterns=json.dumps(["OLD"]),
                    enabled=True,
                    priority=100,
                )
            )
            db.session.commit()

        bundle = self._sample_bundle(overwrite=True, create_missing_accounts=False)
        bundle["accounts"] = []
        bundle["filters"] = []
        bundle["rulesets"] = [
            {
                "name": "Shared",
                "description": "New",
                "enabled": False,
                "priority": 5,
                "rules": [],
            }
        ]
        bundle["account_ruleset_assignments"] = []
        bundle["epg_match_rulesets"] = []
        bundle["account_epg_match_ruleset_assignments"] = []
        bundle["fcc_patterns"]["networks"] = [
            {
                "name": "FOX",
                "display_name": "Fox Updated",
                "fcc_affiliation_pattern": "%FOX%",
                "tag_patterns": ["FOX"],
                "enabled": True,
                "priority": 1,
            }
        ]

        with app.app_context():
            ConfigTransferService.import_bundle(
                bundle,
                overwrite=True,
                create_missing_accounts=False,
            )

            ruleset = RuleSet.query.filter_by(name="Shared").first()
            assert ruleset is not None
            assert ruleset.description == "New"
            assert ruleset.enabled is False
            assert ruleset.priority == 5

            network = FccMatchNetwork.query.filter_by(name="FOX").first()
            assert network is not None
            assert network.display_name == "Fox Updated"
            assert network.fcc_affiliation_pattern == "%FOX%"
            assert network.priority == 1
            assert json.loads(network.tag_patterns) == ["FOX"]
