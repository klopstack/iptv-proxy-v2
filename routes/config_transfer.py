"""
Configuration export/import routes.

Provides a portable JSON bundle for backing up and restoring configuration entities:
- Accounts (optional)
- Filters
- Tag rulesets and tag rules
- Account->tag-ruleset assignments
- EPG match rulesets and rules
- Account->EPG-ruleset assignments
- EPG exclusion patterns
- EPG channel name mappings
- FCC matching patterns
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import (
    Account,
    AccountEpgMatchRuleSet,
    AccountRuleSet,
    CallsignSuffix,
    CountryTag,
    EpgChannelNameMapping,
    EpgCountrySuffix,
    EpgExclusionPattern,
    EpgMatchRule,
    EpgMatchRuleSet,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    Filter,
    QualityTag,
    RuleSet,
    TagRule,
    db,
)
from services.cache_service import cache_service
from services.config_bundle_validation import validate_config_import_bundle
from services.epg.match_rules import clear_fcc_pattern_cache
from services.serializers.epg_match import (
    serialize_epg_channel_name_mapping,
    serialize_epg_exclusion_pattern,
    serialize_epg_ruleset,
    serialize_ruleset,
)
from services.serializers.fcc import (
    serialize_fcc_channel_pattern,
    serialize_fcc_location_pattern,
    serialize_fcc_network,
    serialize_fcc_strategy,
)
from services.tag_service import TagService

logger = logging.getLogger(__name__)

config_transfer_bp = Blueprint("config_transfer", __name__)


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _safe_json_loads(value: Optional[str], default: Any = None) -> Any:
    if not value:
        return default
    return json.loads(value)


@config_transfer_bp.route("/api/config/export", methods=["GET"])
@handle_errors(return_json=True, default_message="Error exporting configuration bundle")
def export_config_bundle():
    """Export a full configuration bundle as JSON."""
    include_accounts = _parse_bool(request.args.get("include_accounts"), default=True)

    accounts = Account.query.order_by(Account.name).all()
    rulesets = RuleSet.query.order_by(RuleSet.priority, RuleSet.name).all()
    epg_rulesets = EpgMatchRuleSet.query.order_by(EpgMatchRuleSet.priority, EpgMatchRuleSet.name).all()

    bundle = {
        "version": "1.0",
        "type": "iptv-proxy-config-bundle",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "accounts": [
            {
                "name": account.name,
                "server": account.server,
                "user_agent": account.user_agent,
                "enabled": account.enabled,
                "ppv_visibility": account.ppv_visibility,
                "ppv_rename_format": account.ppv_rename_format,
                "ppv_rename_timezone": account.ppv_rename_timezone,
                "fcc_rename_format": account.fcc_rename_format,
            }
            for account in accounts
        ]
        if include_accounts
        else [],
        "filters": [
            {
                "account_name": filter_obj.account.name if filter_obj.account else None,
                "name": filter_obj.name,
                "filter_type": filter_obj.filter_type,
                "filter_action": filter_obj.filter_action,
                "filter_value": filter_obj.filter_value,
                "enabled": filter_obj.enabled,
            }
            for filter_obj in Filter.query.order_by(Filter.account_id, Filter.id).all()
            if filter_obj.account is not None
        ],
        "rulesets": [serialize_ruleset(ruleset) for ruleset in rulesets],
        "account_ruleset_assignments": [
            {
                "account_name": account.name,
                "ruleset_name": ruleset.name,
                "priority": assignment.priority,
            }
            for assignment, ruleset, account in db.session.query(AccountRuleSet, RuleSet, Account)
            .join(RuleSet, RuleSet.id == AccountRuleSet.ruleset_id)
            .join(Account, Account.id == AccountRuleSet.account_id)
            .order_by(Account.name, AccountRuleSet.priority)
            .all()
        ],
        "epg_match_rulesets": [serialize_epg_ruleset(ruleset) for ruleset in epg_rulesets],
        "account_epg_match_ruleset_assignments": [
            {
                "account_name": account.name,
                "ruleset_name": ruleset.name,
                "priority": assignment.priority,
            }
            for assignment, ruleset, account in db.session.query(AccountEpgMatchRuleSet, EpgMatchRuleSet, Account)
            .join(EpgMatchRuleSet, EpgMatchRuleSet.id == AccountEpgMatchRuleSet.ruleset_id)
            .join(Account, Account.id == AccountEpgMatchRuleSet.account_id)
            .order_by(Account.name, AccountEpgMatchRuleSet.priority)
            .all()
        ],
        "epg_exclusion_patterns": [
            serialize_epg_exclusion_pattern(pattern, include_id=False)
            for pattern in EpgExclusionPattern.query.order_by(
                EpgExclusionPattern.priority, EpgExclusionPattern.name
            ).all()
        ],
        "epg_channel_name_mappings": [
            serialize_epg_channel_name_mapping(mapping, include_id=False)
            for mapping in EpgChannelNameMapping.query.order_by(
                EpgChannelNameMapping.priority, EpgChannelNameMapping.name
            ).all()
        ],
        "fcc_patterns": {
            "networks": [
                serialize_fcc_network(model, include_id=False)
                for model in FccMatchNetwork.query.order_by(FccMatchNetwork.priority).all()
            ],
            "channel_patterns": [
                serialize_fcc_channel_pattern(model, include_id=False)
                for model in FccMatchChannelPattern.query.order_by(FccMatchChannelPattern.priority).all()
            ],
            "location_patterns": [
                serialize_fcc_location_pattern(model, include_id=False)
                for model in FccMatchLocationPattern.query.order_by(FccMatchLocationPattern.priority).all()
            ],
            "strategies": [
                serialize_fcc_strategy(model, include_id=False)
                for model in FccMatchStrategy.query.order_by(FccMatchStrategy.priority).all()
            ],
            "country_suffixes": [
                {
                    "country_code": model.country_code,
                    "country_name": model.country_name,
                    "epg_suffixes": _safe_json_loads(model.epg_suffixes, default=[]),
                    "enabled": model.enabled,
                    "priority": model.priority,
                }
                for model in EpgCountrySuffix.query.order_by(EpgCountrySuffix.priority).all()
            ],
            "quality_tags": [
                {
                    "tag_name": model.tag_name,
                    "display_name": model.display_name,
                    "category": model.category,
                    "quality_score": model.quality_score,
                    "exclude_from_location": model.exclude_from_location,
                    "enabled": model.enabled,
                }
                for model in QualityTag.query.order_by(QualityTag.tag_name).all()
            ],
            "country_tags": [
                {
                    "tag_name": model.tag_name,
                    "country_name": model.country_name,
                    "iso_code": model.iso_code,
                    "exclude_from_location": model.exclude_from_location,
                    "enabled": model.enabled,
                }
                for model in CountryTag.query.order_by(CountryTag.tag_name).all()
            ],
            "callsign_suffixes": [
                {
                    "suffix": model.suffix,
                    "description": model.description,
                    "try_on_miss": model.try_on_miss,
                    "strip_on_normalize": model.strip_on_normalize,
                    "enabled": model.enabled,
                    "priority": model.priority,
                }
                for model in CallsignSuffix.query.order_by(CallsignSuffix.priority).all()
            ],
        },
    }

    response = jsonify(bundle)
    response.headers["Content-Disposition"] = 'attachment; filename="iptv_proxy_config_bundle.json"'
    return response


def _resolve_account(
    name: Optional[str], create_missing: bool, account_payload_by_name: dict[str, dict]
) -> Optional[Account]:
    if not name:
        return None

    account = Account.query.filter_by(name=name).first()
    if account:
        return account

    if not create_missing:
        return None

    payload = account_payload_by_name.get(name)
    if not payload:
        return None

    account = Account(
        name=payload["name"],
        server=payload.get("server", ""),
        user_agent=payload.get("user_agent")
        or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        enabled=payload.get("enabled", True),
        ppv_visibility=payload.get("ppv_visibility", "hide_inactive"),
        ppv_rename_format=payload.get("ppv_rename_format"),
        ppv_rename_timezone=payload.get("ppv_rename_timezone"),
        fcc_rename_format=payload.get("fcc_rename_format"),
    )
    db.session.add(account)
    db.session.flush()
    return account


@config_transfer_bp.route("/api/config/import", methods=["POST"])
@handle_errors(return_json=True, default_message="Error importing configuration bundle")
def import_config_bundle():
    """Import a full configuration bundle.

    Expected body:
    {
      "type": "iptv-proxy-config-bundle",
      ...,
      "options": {
        "overwrite": false,
        "create_missing_accounts": false
      }
    }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "No JSON body provided"}), 400

    validation_error = validate_config_import_bundle(data)
    if validation_error:
        return jsonify({"error": validation_error}), 400

    options = data.get("options") or {}
    overwrite = bool(options.get("overwrite", False))
    create_missing_accounts = bool(options.get("create_missing_accounts", False))

    stats = {
        "accounts": {"created": 0, "updated": 0, "skipped": 0},
        "filters": {"created": 0, "updated": 0, "skipped": 0},
        "rulesets": {"created": 0, "updated": 0, "skipped": 0},
        "tag_rules": {"created": 0, "skipped": 0},
        "account_ruleset_assignments": {"created": 0, "updated": 0, "skipped": 0},
        "epg_match_rulesets": {"created": 0, "updated": 0, "skipped": 0},
        "epg_match_rules": {"created": 0, "skipped": 0},
        "account_epg_match_ruleset_assignments": {"created": 0, "updated": 0, "skipped": 0},
        "epg_exclusion_patterns": {"created": 0, "updated": 0, "skipped": 0},
        "epg_channel_name_mappings": {"created": 0, "updated": 0, "skipped": 0},
        "fcc_networks": {"created": 0, "updated": 0, "skipped": 0},
        "fcc_channel_patterns": {"created": 0, "updated": 0, "skipped": 0},
        "fcc_location_patterns": {"created": 0, "updated": 0, "skipped": 0},
        "fcc_strategies": {"created": 0, "updated": 0, "skipped": 0},
        "epg_country_suffixes": {"created": 0, "updated": 0, "skipped": 0},
        "quality_tags": {"created": 0, "updated": 0, "skipped": 0},
        "country_tags": {"created": 0, "updated": 0, "skipped": 0},
        "callsign_suffixes": {"created": 0, "updated": 0, "skipped": 0},
    }

    accounts_data = data.get("accounts") or []
    account_payload_by_name = {row.get("name"): row for row in accounts_data if row.get("name")}

    # 1) Accounts
    for account_data in accounts_data:
        name = account_data.get("name")
        server = account_data.get("server")
        if not name or not server:
            stats["accounts"]["skipped"] += 1
            continue

        account = Account.query.filter_by(name=name).first()
        if account:
            if not overwrite:
                stats["accounts"]["skipped"] += 1
                continue

            account.server = server
            account.user_agent = account_data.get("user_agent", account.user_agent)
            account.enabled = account_data.get("enabled", account.enabled)
            account.ppv_visibility = account_data.get("ppv_visibility", account.ppv_visibility)
            account.ppv_rename_format = account_data.get("ppv_rename_format", account.ppv_rename_format)
            account.ppv_rename_timezone = account_data.get("ppv_rename_timezone", account.ppv_rename_timezone)
            account.fcc_rename_format = account_data.get("fcc_rename_format", account.fcc_rename_format)
            stats["accounts"]["updated"] += 1
            continue

        db.session.add(
            Account(
                name=name,
                server=server,
                user_agent=account_data.get("user_agent")
                or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                enabled=account_data.get("enabled", True),
                ppv_visibility=account_data.get("ppv_visibility", "hide_inactive"),
                ppv_rename_format=account_data.get("ppv_rename_format"),
                ppv_rename_timezone=account_data.get("ppv_rename_timezone"),
                fcc_rename_format=account_data.get("fcc_rename_format"),
            )
        )
        stats["accounts"]["created"] += 1

    db.session.flush()

    # 2) Rulesets and Tag Rules
    special_tags = {"__CLEANUP__", "__LOCATION__", "__CALLSIGN__", "__CAPTURE__"}
    rulesets_by_name: dict[str, RuleSet] = {}

    for ruleset_data in data.get("rulesets") or []:
        name = ruleset_data.get("name")
        if not name:
            stats["rulesets"]["skipped"] += 1
            continue

        ruleset = RuleSet.query.filter_by(name=name).first()
        if ruleset:
            rulesets_by_name[name] = ruleset
            if not overwrite:
                stats["rulesets"]["skipped"] += 1
                continue

            ruleset.description = ruleset_data.get("description", ruleset.description)
            ruleset.is_default = ruleset_data.get("is_default", ruleset.is_default)
            ruleset.enabled = ruleset_data.get("enabled", ruleset.enabled)
            ruleset.priority = ruleset_data.get("priority", ruleset.priority)
            TagRule.query.filter_by(ruleset_id=ruleset.id).delete()
            stats["rulesets"]["updated"] += 1
        else:
            ruleset = RuleSet(
                name=name,
                description=ruleset_data.get("description", ""),
                is_default=ruleset_data.get("is_default", False),
                enabled=ruleset_data.get("enabled", True),
                priority=ruleset_data.get("priority", 100),
            )
            db.session.add(ruleset)
            db.session.flush()
            rulesets_by_name[name] = ruleset
            stats["rulesets"]["created"] += 1

        for rule_data in ruleset_data.get("rules") or []:
            required = {"name", "pattern", "pattern_type", "tag_name", "source"}
            if not required.issubset(rule_data.keys()):
                stats["tag_rules"]["skipped"] += 1
                continue
            if rule_data["pattern_type"] not in {"prefix", "suffix", "contains", "regex"}:
                stats["tag_rules"]["skipped"] += 1
                continue
            if rule_data["source"] not in {"channel_name", "category_name", "both"}:
                stats["tag_rules"]["skipped"] += 1
                continue

            tag_name = rule_data["tag_name"]
            if tag_name not in special_tags:
                normalized = TagService.normalize_tag_name(tag_name)
                if normalized:
                    tag_name = normalized

            db.session.add(
                TagRule(
                    ruleset_id=ruleset.id,
                    name=rule_data["name"],
                    pattern=rule_data["pattern"],
                    pattern_type=rule_data["pattern_type"],
                    tag_name=tag_name,
                    source=rule_data["source"],
                    remove_from_name=rule_data.get("remove_from_name", True),
                    replacement=rule_data.get("replacement"),
                    set_is_ppv=rule_data.get("set_is_ppv", TagRule.PPV_KEEP),
                    priority=rule_data.get("priority", 100),
                    enabled=rule_data.get("enabled", True),
                )
            )
            stats["tag_rules"]["created"] += 1

    # 3) Filters
    for filter_data in data.get("filters") or []:
        account = _resolve_account(
            filter_data.get("account_name"),
            create_missing_accounts,
            account_payload_by_name,
        )
        if not account:
            stats["filters"]["skipped"] += 1
            continue

        name = filter_data.get("name")
        filter_type = filter_data.get("filter_type")
        filter_action = filter_data.get("filter_action")
        filter_value = filter_data.get("filter_value")
        if not all([name, filter_type, filter_action, filter_value]):
            stats["filters"]["skipped"] += 1
            continue

        existing = Filter.query.filter_by(
            account_id=account.id,
            name=name,
            filter_type=filter_type,
            filter_action=filter_action,
            filter_value=filter_value,
        ).first()

        if existing:
            if not overwrite:
                stats["filters"]["skipped"] += 1
                continue
            existing.enabled = filter_data.get("enabled", existing.enabled)
            stats["filters"]["updated"] += 1
        else:
            db.session.add(
                Filter(
                    account_id=account.id,
                    name=name,
                    filter_type=filter_type,
                    filter_action=filter_action,
                    filter_value=filter_value,
                    enabled=filter_data.get("enabled", True),
                )
            )
            stats["filters"]["created"] += 1

    # 4) Account->Ruleset assignments
    for assignment_data in data.get("account_ruleset_assignments") or []:
        account = _resolve_account(
            assignment_data.get("account_name"),
            create_missing_accounts,
            account_payload_by_name,
        )
        ruleset_name = assignment_data.get("ruleset_name")
        ruleset = rulesets_by_name.get(ruleset_name) or RuleSet.query.filter_by(name=ruleset_name).first()

        if not account or not ruleset:
            stats["account_ruleset_assignments"]["skipped"] += 1
            continue

        existing = AccountRuleSet.query.filter_by(account_id=account.id, ruleset_id=ruleset.id).first()
        if existing:
            if not overwrite:
                stats["account_ruleset_assignments"]["skipped"] += 1
                continue
            existing.priority = assignment_data.get("priority", existing.priority)
            stats["account_ruleset_assignments"]["updated"] += 1
        else:
            db.session.add(
                AccountRuleSet(
                    account_id=account.id,
                    ruleset_id=ruleset.id,
                    priority=assignment_data.get("priority", 100),
                )
            )
            stats["account_ruleset_assignments"]["created"] += 1

    # 5) EPG match rulesets and rules
    epg_rulesets_by_name: dict[str, EpgMatchRuleSet] = {}
    for ruleset_data in data.get("epg_match_rulesets") or []:
        name = ruleset_data.get("name")
        if not name:
            stats["epg_match_rulesets"]["skipped"] += 1
            continue

        ruleset = EpgMatchRuleSet.query.filter_by(name=name).first()
        if ruleset:
            epg_rulesets_by_name[name] = ruleset
            if not overwrite:
                stats["epg_match_rulesets"]["skipped"] += 1
                continue

            ruleset.description = ruleset_data.get("description", ruleset.description)
            ruleset.is_default = ruleset_data.get("is_default", ruleset.is_default)
            ruleset.enabled = ruleset_data.get("enabled", ruleset.enabled)
            ruleset.priority = ruleset_data.get("priority", ruleset.priority)
            EpgMatchRule.query.filter_by(ruleset_id=ruleset.id).delete()
            stats["epg_match_rulesets"]["updated"] += 1
        else:
            ruleset = EpgMatchRuleSet(
                name=name,
                description=ruleset_data.get("description", ""),
                is_default=ruleset_data.get("is_default", False),
                enabled=ruleset_data.get("enabled", True),
                priority=ruleset_data.get("priority", 100),
            )
            db.session.add(ruleset)
            db.session.flush()
            epg_rulesets_by_name[name] = ruleset
            stats["epg_match_rulesets"]["created"] += 1

        for rule_data in ruleset_data.get("rules") or []:
            if not rule_data.get("name") or not rule_data.get("match_type"):
                stats["epg_match_rules"]["skipped"] += 1
                continue

            db.session.add(
                EpgMatchRule(
                    ruleset_id=ruleset.id,
                    name=rule_data["name"],
                    description=rule_data.get("description", ""),
                    match_type=rule_data["match_type"],
                    source=rule_data.get("source", EpgMatchRule.SOURCE_CLEANED_NAME),
                    pattern=rule_data.get("pattern"),
                    action=rule_data.get("action", EpgMatchRule.ACTION_MAP_EPG),
                    min_confidence=rule_data.get("min_confidence", 0.75),
                    required_tags=json.dumps(rule_data["required_tags"]) if rule_data.get("required_tags") else None,
                    excluded_tags=json.dumps(rule_data["excluded_tags"]) if rule_data.get("excluded_tags") else None,
                    fallback_epg_id=rule_data.get("fallback_epg_id"),
                    category_pattern=rule_data.get("category_pattern"),
                    category_exclude_pattern=rule_data.get("category_exclude_pattern"),
                    country_codes=json.dumps(rule_data["country_codes"]) if rule_data.get("country_codes") else None,
                    epg_source_ids=json.dumps(rule_data["epg_source_ids"]) if rule_data.get("epg_source_ids") else None,
                    time_offset_hours=rule_data.get("time_offset_hours", 0),
                    priority=rule_data.get("priority", 100),
                    enabled=rule_data.get("enabled", True),
                    stop_on_match=rule_data.get("stop_on_match", True),
                )
            )
            stats["epg_match_rules"]["created"] += 1

    # 6) Account->EPG match ruleset assignments
    for assignment_data in data.get("account_epg_match_ruleset_assignments") or []:
        account = _resolve_account(
            assignment_data.get("account_name"),
            create_missing_accounts,
            account_payload_by_name,
        )
        ruleset_name = assignment_data.get("ruleset_name")
        ruleset = epg_rulesets_by_name.get(ruleset_name) or EpgMatchRuleSet.query.filter_by(name=ruleset_name).first()

        if not account or not ruleset:
            stats["account_epg_match_ruleset_assignments"]["skipped"] += 1
            continue

        existing = AccountEpgMatchRuleSet.query.filter_by(account_id=account.id, ruleset_id=ruleset.id).first()
        if existing:
            if not overwrite:
                stats["account_epg_match_ruleset_assignments"]["skipped"] += 1
                continue
            existing.priority = assignment_data.get("priority", existing.priority)
            stats["account_epg_match_ruleset_assignments"]["updated"] += 1
        else:
            db.session.add(
                AccountEpgMatchRuleSet(
                    account_id=account.id,
                    ruleset_id=ruleset.id,
                    priority=assignment_data.get("priority", 100),
                )
            )
            stats["account_epg_match_ruleset_assignments"]["created"] += 1

    # 7) EPG exclusion patterns
    for pattern_data in data.get("epg_exclusion_patterns") or []:
        name = pattern_data.get("name")
        pattern_type = pattern_data.get("pattern_type")
        pattern = pattern_data.get("pattern")
        if not all([name, pattern_type, pattern]):
            stats["epg_exclusion_patterns"]["skipped"] += 1
            continue

        existing = EpgExclusionPattern.query.filter_by(
            name=name,
            pattern_type=pattern_type,
            pattern=pattern,
        ).first()

        if existing:
            if not overwrite:
                stats["epg_exclusion_patterns"]["skipped"] += 1
                continue
            existing.description = pattern_data.get("description", existing.description)
            existing.is_regex = pattern_data.get("is_regex", existing.is_regex)
            existing.hide_channel = pattern_data.get("hide_channel", existing.hide_channel)
            existing.enabled = pattern_data.get("enabled", existing.enabled)
            existing.priority = pattern_data.get("priority", existing.priority)
            stats["epg_exclusion_patterns"]["updated"] += 1
        else:
            db.session.add(
                EpgExclusionPattern(
                    name=name,
                    description=pattern_data.get("description", ""),
                    pattern_type=pattern_type,
                    pattern=pattern,
                    is_regex=pattern_data.get("is_regex", True),
                    hide_channel=pattern_data.get("hide_channel", False),
                    enabled=pattern_data.get("enabled", True),
                    priority=pattern_data.get("priority", 100),
                )
            )
            stats["epg_exclusion_patterns"]["created"] += 1

    # 8) EPG channel name mappings
    for mapping_data in data.get("epg_channel_name_mappings") or []:
        key_name = mapping_data.get("name")
        old_name = mapping_data.get("old_name")
        new_name = mapping_data.get("new_name")
        if not all([key_name, old_name, new_name]):
            stats["epg_channel_name_mappings"]["skipped"] += 1
            continue

        existing = EpgChannelNameMapping.query.filter_by(name=key_name, old_name=old_name, new_name=new_name).first()

        if existing:
            if not overwrite:
                stats["epg_channel_name_mappings"]["skipped"] += 1
                continue
            existing.description = mapping_data.get("description", existing.description)
            existing.match_type = mapping_data.get("match_type", existing.match_type)
            existing.case_sensitive = mapping_data.get("case_sensitive", existing.case_sensitive)
            existing.enabled = mapping_data.get("enabled", existing.enabled)
            existing.priority = mapping_data.get("priority", existing.priority)
            stats["epg_channel_name_mappings"]["updated"] += 1
        else:
            db.session.add(
                EpgChannelNameMapping(
                    name=key_name,
                    description=mapping_data.get("description", ""),
                    old_name=old_name,
                    new_name=new_name,
                    match_type=mapping_data.get("match_type", "contains"),
                    case_sensitive=mapping_data.get("case_sensitive", False),
                    enabled=mapping_data.get("enabled", True),
                    priority=mapping_data.get("priority", 100),
                )
            )
            stats["epg_channel_name_mappings"]["created"] += 1

    fcc_data = data.get("fcc_patterns") or {}

    # 9) FCC networks
    for row in fcc_data.get("networks") or []:
        name = row.get("name")
        affiliation = row.get("fcc_affiliation_pattern")
        if not name or not affiliation:
            stats["fcc_networks"]["skipped"] += 1
            continue

        existing = FccMatchNetwork.query.filter_by(name=name).first()
        if existing:
            if not overwrite:
                stats["fcc_networks"]["skipped"] += 1
                continue
            existing.display_name = row.get("display_name", existing.display_name)
            existing.description = row.get("description", existing.description)
            existing.fcc_affiliation_pattern = affiliation
            existing.tag_patterns = json.dumps(row.get("tag_patterns") or [])
            existing.enabled = row.get("enabled", existing.enabled)
            existing.priority = row.get("priority", existing.priority)
            stats["fcc_networks"]["updated"] += 1
        else:
            db.session.add(
                FccMatchNetwork(
                    name=name,
                    display_name=row.get("display_name"),
                    description=row.get("description"),
                    fcc_affiliation_pattern=affiliation,
                    tag_patterns=json.dumps(row.get("tag_patterns") or []),
                    enabled=row.get("enabled", True),
                    priority=row.get("priority", 100),
                )
            )
            stats["fcc_networks"]["created"] += 1

    # 10) FCC channel patterns
    for row in fcc_data.get("channel_patterns") or []:
        name = row.get("name")
        pattern = row.get("pattern")
        if not name or not pattern:
            stats["fcc_channel_patterns"]["skipped"] += 1
            continue

        existing = FccMatchChannelPattern.query.filter_by(name=name, pattern=pattern).first()
        if existing:
            if not overwrite:
                stats["fcc_channel_patterns"]["skipped"] += 1
                continue
            existing.description = row.get("description", existing.description)
            existing.pattern_type = row.get("pattern_type", existing.pattern_type)
            existing.capture_group = row.get("capture_group", existing.capture_group)
            existing.networks = json.dumps(row.get("networks")) if row.get("networks") else None
            existing.enabled = row.get("enabled", existing.enabled)
            existing.priority = row.get("priority", existing.priority)
            stats["fcc_channel_patterns"]["updated"] += 1
        else:
            db.session.add(
                FccMatchChannelPattern(
                    name=name,
                    description=row.get("description"),
                    pattern=pattern,
                    pattern_type=row.get("pattern_type", "regex"),
                    capture_group=row.get("capture_group", 1),
                    networks=json.dumps(row.get("networks")) if row.get("networks") else None,
                    enabled=row.get("enabled", True),
                    priority=row.get("priority", 100),
                )
            )
            stats["fcc_channel_patterns"]["created"] += 1

    # 11) FCC location patterns
    for row in fcc_data.get("location_patterns") or []:
        name = row.get("name")
        pattern = row.get("pattern")
        if not name or not pattern:
            stats["fcc_location_patterns"]["skipped"] += 1
            continue

        existing = FccMatchLocationPattern.query.filter_by(name=name, pattern=pattern).first()
        if existing:
            if not overwrite:
                stats["fcc_location_patterns"]["skipped"] += 1
                continue
            existing.description = row.get("description", existing.description)
            existing.pattern_type = row.get("pattern_type", existing.pattern_type)
            existing.extract_city = row.get("extract_city", existing.extract_city)
            existing.extract_state = row.get("extract_state", existing.extract_state)
            existing.city_group = row.get("city_group", existing.city_group)
            existing.state_group = row.get("state_group", existing.state_group)
            existing.enabled = row.get("enabled", existing.enabled)
            existing.priority = row.get("priority", existing.priority)
            stats["fcc_location_patterns"]["updated"] += 1
        else:
            db.session.add(
                FccMatchLocationPattern(
                    name=name,
                    description=row.get("description"),
                    pattern=pattern,
                    pattern_type=row.get("pattern_type", "regex"),
                    extract_city=row.get("extract_city", True),
                    extract_state=row.get("extract_state", True),
                    city_group=row.get("city_group", 1),
                    state_group=row.get("state_group", 2),
                    enabled=row.get("enabled", True),
                    priority=row.get("priority", 100),
                )
            )
            stats["fcc_location_patterns"]["created"] += 1

    # 12) FCC strategies
    for row in fcc_data.get("strategies") or []:
        name = row.get("name")
        strategy_type = row.get("strategy_type")
        if not name or not strategy_type:
            stats["fcc_strategies"]["skipped"] += 1
            continue

        existing = FccMatchStrategy.query.filter_by(name=name, strategy_type=strategy_type).first()
        if existing:
            if not overwrite:
                stats["fcc_strategies"]["skipped"] += 1
                continue
            existing.description = row.get("description", existing.description)
            existing.require_network = row.get("require_network", existing.require_network)
            existing.require_channel_number = row.get("require_channel_number", existing.require_channel_number)
            existing.require_state = row.get("require_state", existing.require_state)
            existing.require_city = row.get("require_city", existing.require_city)
            existing.match_nielsen_dma = row.get("match_nielsen_dma", existing.match_nielsen_dma)
            existing.match_community_city = row.get("match_community_city", existing.match_community_city)
            existing.match_community_state = row.get("match_community_state", existing.match_community_state)
            existing.enabled = row.get("enabled", existing.enabled)
            existing.priority = row.get("priority", existing.priority)
            stats["fcc_strategies"]["updated"] += 1
        else:
            db.session.add(
                FccMatchStrategy(
                    name=name,
                    description=row.get("description"),
                    strategy_type=strategy_type,
                    require_network=row.get("require_network", True),
                    require_channel_number=row.get("require_channel_number", False),
                    require_state=row.get("require_state", False),
                    require_city=row.get("require_city", False),
                    match_nielsen_dma=row.get("match_nielsen_dma", True),
                    match_community_city=row.get("match_community_city", True),
                    match_community_state=row.get("match_community_state", True),
                    enabled=row.get("enabled", True),
                    priority=row.get("priority", 100),
                )
            )
            stats["fcc_strategies"]["created"] += 1

    # 13) Country suffixes
    for row in fcc_data.get("country_suffixes") or []:
        code = row.get("country_code")
        suffixes = row.get("epg_suffixes")
        if not code or suffixes is None:
            stats["epg_country_suffixes"]["skipped"] += 1
            continue

        existing = EpgCountrySuffix.query.filter_by(country_code=code).first()
        if existing:
            if not overwrite:
                stats["epg_country_suffixes"]["skipped"] += 1
                continue
            existing.country_name = row.get("country_name", existing.country_name)
            existing.epg_suffixes = json.dumps(suffixes)
            existing.enabled = row.get("enabled", existing.enabled)
            existing.priority = row.get("priority", existing.priority)
            stats["epg_country_suffixes"]["updated"] += 1
        else:
            db.session.add(
                EpgCountrySuffix(
                    country_code=code,
                    country_name=row.get("country_name"),
                    epg_suffixes=json.dumps(suffixes),
                    enabled=row.get("enabled", True),
                    priority=row.get("priority", 100),
                )
            )
            stats["epg_country_suffixes"]["created"] += 1

    # 14) Quality tags
    for row in fcc_data.get("quality_tags") or []:
        tag_name = row.get("tag_name")
        if not tag_name:
            stats["quality_tags"]["skipped"] += 1
            continue

        existing = QualityTag.query.filter_by(tag_name=tag_name).first()
        if existing:
            if not overwrite:
                stats["quality_tags"]["skipped"] += 1
                continue
            existing.display_name = row.get("display_name", existing.display_name)
            existing.category = row.get("category", existing.category)
            existing.quality_score = row.get("quality_score", existing.quality_score)
            existing.exclude_from_location = row.get("exclude_from_location", existing.exclude_from_location)
            existing.enabled = row.get("enabled", existing.enabled)
            stats["quality_tags"]["updated"] += 1
        else:
            db.session.add(
                QualityTag(
                    tag_name=tag_name,
                    display_name=row.get("display_name"),
                    category=row.get("category"),
                    quality_score=row.get("quality_score", 0),
                    exclude_from_location=row.get("exclude_from_location", True),
                    enabled=row.get("enabled", True),
                )
            )
            stats["quality_tags"]["created"] += 1

    # 15) Country tags
    for row in fcc_data.get("country_tags") or []:
        tag_name = row.get("tag_name")
        if not tag_name:
            stats["country_tags"]["skipped"] += 1
            continue

        existing = CountryTag.query.filter_by(tag_name=tag_name).first()
        if existing:
            if not overwrite:
                stats["country_tags"]["skipped"] += 1
                continue
            existing.country_name = row.get("country_name", existing.country_name)
            existing.iso_code = row.get("iso_code", existing.iso_code)
            existing.exclude_from_location = row.get("exclude_from_location", existing.exclude_from_location)
            existing.enabled = row.get("enabled", existing.enabled)
            stats["country_tags"]["updated"] += 1
        else:
            db.session.add(
                CountryTag(
                    tag_name=tag_name,
                    country_name=row.get("country_name"),
                    iso_code=row.get("iso_code"),
                    exclude_from_location=row.get("exclude_from_location", True),
                    enabled=row.get("enabled", True),
                )
            )
            stats["country_tags"]["created"] += 1

    # 16) Callsign suffixes
    for row in fcc_data.get("callsign_suffixes") or []:
        suffix = row.get("suffix")
        if not suffix:
            stats["callsign_suffixes"]["skipped"] += 1
            continue

        existing = CallsignSuffix.query.filter_by(suffix=suffix).first()
        if existing:
            if not overwrite:
                stats["callsign_suffixes"]["skipped"] += 1
                continue
            existing.description = row.get("description", existing.description)
            existing.try_on_miss = row.get("try_on_miss", existing.try_on_miss)
            existing.strip_on_normalize = row.get("strip_on_normalize", existing.strip_on_normalize)
            existing.enabled = row.get("enabled", existing.enabled)
            existing.priority = row.get("priority", existing.priority)
            stats["callsign_suffixes"]["updated"] += 1
        else:
            db.session.add(
                CallsignSuffix(
                    suffix=suffix,
                    description=row.get("description"),
                    try_on_miss=row.get("try_on_miss", True),
                    strip_on_normalize=row.get("strip_on_normalize", True),
                    enabled=row.get("enabled", True),
                    priority=row.get("priority", 100),
                )
            )
            stats["callsign_suffixes"]["created"] += 1

    db.session.commit()
    cache_service.clear_all()
    clear_fcc_pattern_cache()

    return jsonify(
        {
            "success": True,
            "overwrite": overwrite,
            "create_missing_accounts": create_missing_accounts,
            "stats": stats,
        }
    )
