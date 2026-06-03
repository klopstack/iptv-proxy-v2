"""
EPG match rules admin operations for HTTP routes.

Extracted from routes/epg/match_rules.py so handlers stay thin (parse → service → respond).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from models import (
    Account,
    AccountEpgMatchRuleSet,
    Category,
    Channel,
    ChannelTag,
    EpgChannelNameMapping,
    EpgExclusionPattern,
    EpgMatchRule,
    EpgMatchRuleSet,
    Tag,
    db,
)
from services.cache_service import cache_service
from services.epg.match_rules.patterns import clear_fcc_pattern_cache
from services.serializers.epg_match import (
    serialize_epg_channel_name_mapping,
    serialize_epg_exclusion_pattern,
    serialize_epg_match_rule,
)

logger = logging.getLogger(__name__)

_RULE_SORT_KEY = lambda rule: (rule.priority, rule.id)  # noqa: E731

DEFAULT_EPG_MATCH_RULES: List[Dict[str, Any]] = [
    {
        "name": "Provider EPG ID",
        "description": "Match using provider-assigned EPG channel ID",
        "match_type": "provider_id",
        "priority": 10,
    },
    {
        "name": "Callsign Tag Match",
        "description": "Match using channel's callsign tags (e.g., KABC, WNBC)",
        "match_type": "callsign_tag",
        "priority": 20,
    },
    {
        "name": "FCC Database Lookup",
        "description": "Look up callsign from FCC data using location and network tags",
        "match_type": "fcc_lookup",
        "priority": 30,
    },
    {
        "name": "Callsign from Name",
        "description": "Extract callsign from cleaned channel name",
        "match_type": "callsign_name",
        "priority": 40,
    },
    {
        "name": "Exact Name Match",
        "description": "Match on exact normalized channel name",
        "match_type": "exact_name",
        "source": "cleaned_name",
        "priority": 50,
    },
    {
        "name": "Fuzzy Name Match",
        "description": "Fuzzy matching on channel name (75% threshold)",
        "match_type": "fuzzy_name",
        "source": "cleaned_name",
        "min_confidence": 0.75,
        "priority": 60,
    },
    {
        "name": "Network Fallback",
        "description": "Use generic network EPG when no local match found",
        "match_type": "network_fallback",
        "priority": 100,
    },
]

DEFAULT_EXCLUSION_PATTERNS: List[Dict[str, Any]] = [
    {
        "name": "PPV Categories",
        "description": "Exclude channels in PPV categories from EPG matching",
        "pattern_type": "category_name",
        "pattern": r"\bPPV\b",
        "is_regex": True,
        "hide_channel": False,
        "priority": 10,
    },
    {
        "name": "Pay-Per-View Categories",
        "description": "Exclude channels in Pay-Per-View categories",
        "pattern_type": "category_name",
        "pattern": r"PAY[\s-]?PER[\s-]?VIEW",
        "is_regex": True,
        "hide_channel": False,
        "priority": 20,
    },
    {
        "name": "No Event Streaming",
        "description": "Hide channels with 'NO EVENT STREAMING' placeholder",
        "pattern_type": "channel_name",
        "pattern": r"NO\s+EVENT\s+STREAMING",
        "is_regex": True,
        "hide_channel": True,
        "priority": 30,
    },
    {
        "name": "PPV Placeholder Channels",
        "description": "Numbered PPV channels without event info",
        "pattern_type": "channel_name",
        "pattern": r"^(?:[A-Z]{2}[:\s])?(?:[A-Z0-9\+\s]+)?PPV[\s\-]*\d+\s*(?:ᴿᴬᵂ|ᴴᴰ|⁴ᴷ|4K|HD|SD)?$",
        "is_regex": True,
        "hide_channel": True,
        "priority": 40,
    },
]

MATCH_TYPES_INFO: Dict[str, Any] = {
    "match_types": [
        {
            "value": "provider_id",
            "label": "Provider EPG ID",
            "description": "Match using the epg_channel_id field assigned by the IPTV provider",
        },
        {
            "value": "callsign_tag",
            "label": "Callsign Tag",
            "description": "Match channel's callsign tags (e.g., KABC, WNBC) to EPG channel IDs",
        },
        {
            "value": "callsign_name",
            "label": "Callsign from Name",
            "description": "Extract callsign (K/W prefix) from cleaned channel name",
        },
        {
            "value": "fcc_lookup",
            "label": "FCC Database Lookup",
            "description": "Look up callsign using FCC data based on location and network tags",
        },
        {
            "value": "exact_name",
            "label": "Exact Name Match",
            "description": "Match on exact normalized channel name",
        },
        {
            "value": "fuzzy_name",
            "label": "Fuzzy Name Match",
            "description": "Fuzzy matching on channel name with configurable threshold",
        },
        {
            "value": "tag_based",
            "label": "Tag-Based",
            "description": "Match based on specific channel tags",
        },
        {
            "value": "category_pattern",
            "label": "Category Pattern",
            "description": "Match channels based on category name patterns",
        },
        {
            "value": "network_fallback",
            "label": "Network Fallback",
            "description": "Use generic network EPG when no local match is found",
        },
        {
            "value": "regex",
            "label": "Regex Pattern",
            "description": "Match using a custom regex pattern against source field",
        },
    ],
    "actions": [
        {
            "value": "map_epg",
            "label": "Map EPG",
            "description": "Create EPG mapping to matched EPG channel",
        },
        {
            "value": "skip",
            "label": "Skip",
            "description": "Skip this channel - no EPG will be assigned",
        },
        {
            "value": "use_fallback",
            "label": "Use Fallback",
            "description": "Use a specified fallback EPG channel ID",
        },
    ],
    "sources": [
        {
            "value": "channel_name",
            "label": "Channel Name",
            "description": "Original channel name from provider",
        },
        {
            "value": "cleaned_name",
            "label": "Cleaned Name",
            "description": "Processed channel name after tag extraction",
        },
        {
            "value": "category_name",
            "label": "Category Name",
            "description": "Category name from provider",
        },
        {
            "value": "epg_channel_id",
            "label": "EPG Channel ID",
            "description": "Provider-assigned EPG channel ID",
        },
        {
            "value": "tags",
            "label": "Channel Tags",
            "description": "Tags extracted from channel/category names",
        },
    ],
    "exclusion_types": [
        {
            "value": "category_name",
            "label": "Category Name",
            "description": "Match against category name",
        },
        {
            "value": "channel_name",
            "label": "Channel Name",
            "description": "Match against channel name",
        },
        {
            "value": "tag",
            "label": "Tag",
            "description": "Exclude channels with specific tags",
        },
    ],
    "name_mapping_match_types": [
        {
            "value": "exact",
            "label": "Exact Match",
            "description": "Old name must match exactly (case-insensitive by default)",
        },
        {
            "value": "contains",
            "label": "Contains",
            "description": "Old name pattern must be found in channel name",
        },
        {
            "value": "prefix",
            "label": "Prefix",
            "description": "Channel name must start with old name pattern",
        },
        {
            "value": "suffix",
            "label": "Suffix",
            "description": "Channel name must end with old name pattern",
        },
        {
            "value": "regex",
            "label": "Regex",
            "description": "Old name is a regex pattern for flexible matching",
        },
    ],
}


class EpgMatchRulesRouteService:
    """CRUD, preview, and bootstrap helpers for EPG match rules admin routes."""

    @staticmethod
    def _clear_cache() -> None:
        cache_service.clear_all()

    @staticmethod
    def _ruleset_summary(ruleset: EpgMatchRuleSet, *, rule_count: Optional[int] = None) -> Dict[str, Any]:
        return {
            "id": ruleset.id,
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rule_count": rule_count if rule_count is not None else len(ruleset.rules),
        }

    @staticmethod
    def list_rulesets() -> List[Dict[str, Any]]:
        rulesets = EpgMatchRuleSet.query.order_by(EpgMatchRuleSet.priority, EpgMatchRuleSet.name).all()
        assignments = (
            db.session.query(AccountEpgMatchRuleSet.ruleset_id, Account.id, Account.name)
            .join(Account, Account.id == AccountEpgMatchRuleSet.account_id)
            .all()
        )
        ruleset_accounts: Dict[int, List[Dict[str, Any]]] = {}
        for ruleset_id, account_id, account_name in assignments:
            ruleset_accounts.setdefault(ruleset_id, []).append({"id": account_id, "name": account_name})
        return [
            {
                **EpgMatchRulesRouteService._ruleset_summary(rs),
                "assigned_accounts": ruleset_accounts.get(rs.id, []),
            }
            for rs in rulesets
        ]

    @staticmethod
    def create_ruleset(data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        existing = EpgMatchRuleSet.query.filter_by(name=data["name"]).first()
        if existing:
            return None, f"Ruleset with name '{data['name']}' already exists", 409
        ruleset = EpgMatchRuleSet(
            name=data["name"],
            description=data.get("description", ""),
            is_default=data.get("is_default", False),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(ruleset)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return {**EpgMatchRulesRouteService._ruleset_summary(ruleset, rule_count=0)}, None, 201

    @staticmethod
    def get_ruleset_detail(ruleset: EpgMatchRuleSet) -> Dict[str, Any]:
        return {
            **EpgMatchRulesRouteService._ruleset_summary(ruleset),
            "rules": [serialize_epg_match_rule(r) for r in sorted(ruleset.rules, key=_RULE_SORT_KEY)],
        }

    @staticmethod
    def update_ruleset(ruleset: EpgMatchRuleSet, data: Dict[str, Any]) -> Dict[str, Any]:
        ruleset.name = data.get("name", ruleset.name)
        ruleset.description = data.get("description", ruleset.description)
        ruleset.is_default = data.get("is_default", ruleset.is_default)
        ruleset.enabled = data.get("enabled", ruleset.enabled)
        ruleset.priority = data.get("priority", ruleset.priority)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return EpgMatchRulesRouteService._ruleset_summary(ruleset)

    @staticmethod
    def delete_ruleset(ruleset_id: int) -> None:
        AccountEpgMatchRuleSet.query.filter_by(ruleset_id=ruleset_id).delete()
        ruleset = EpgMatchRuleSet.query.get_or_404(ruleset_id)
        db.session.delete(ruleset)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()

    @staticmethod
    def duplicate_ruleset(ruleset_id: int) -> Tuple[Dict[str, Any], int]:
        source = EpgMatchRuleSet.query.get_or_404(ruleset_id)
        base_name = f"{source.name} (Copy)"
        counter = 1
        new_name = base_name
        while EpgMatchRuleSet.query.filter_by(name=new_name).first():
            counter += 1
            new_name = f"{base_name} {counter}"
        new_ruleset = EpgMatchRuleSet(
            name=new_name,
            description=source.description,
            is_default=False,
            enabled=source.enabled,
            priority=source.priority + 10,
        )
        db.session.add(new_ruleset)
        db.session.flush()
        for rule in source.rules:
            db.session.add(
                EpgMatchRule(
                    ruleset_id=new_ruleset.id,
                    name=rule.name,
                    description=rule.description,
                    match_type=rule.match_type,
                    source=rule.source,
                    pattern=rule.pattern,
                    action=rule.action,
                    min_confidence=rule.min_confidence,
                    required_tags=rule.required_tags,
                    excluded_tags=rule.excluded_tags,
                    fallback_epg_id=rule.fallback_epg_id,
                    category_pattern=rule.category_pattern,
                    category_exclude_pattern=rule.category_exclude_pattern,
                    country_codes=rule.country_codes,
                    epg_source_ids=rule.epg_source_ids,
                    time_offset_hours=rule.time_offset_hours,
                    priority=rule.priority,
                    enabled=rule.enabled,
                    stop_on_match=rule.stop_on_match,
                )
            )
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return (
            {
                "id": new_ruleset.id,
                "name": new_ruleset.name,
                "rule_count": len(source.rules),
                "message": f"Duplicated ruleset with {len(source.rules)} rules",
            },
            201,
        )

    @staticmethod
    def list_rules(ruleset_id: Optional[int]) -> List[Dict[str, Any]]:
        query = EpgMatchRule.query
        if ruleset_id:
            query = query.filter_by(ruleset_id=ruleset_id)
        rules = query.order_by(EpgMatchRule.priority, EpgMatchRule.id).all()
        return [serialize_epg_match_rule(r) for r in rules]

    @staticmethod
    def create_rule(data: Dict[str, Any]) -> Dict[str, Any]:
        ruleset = EpgMatchRuleSet.query.get_or_404(data["ruleset_id"])
        rule = EpgMatchRule(
            ruleset_id=ruleset.id,
            name=data["name"],
            description=data.get("description", ""),
            match_type=data["match_type"],
            source=data.get("source", "cleaned_name"),
            pattern=data.get("pattern"),
            action=data.get("action", "map_epg"),
            min_confidence=data.get("min_confidence", 0.75),
            required_tags=json.dumps(data["required_tags"]) if data.get("required_tags") else None,
            excluded_tags=json.dumps(data["excluded_tags"]) if data.get("excluded_tags") else None,
            fallback_epg_id=data.get("fallback_epg_id"),
            category_pattern=data.get("category_pattern"),
            category_exclude_pattern=data.get("category_exclude_pattern"),
            country_codes=json.dumps(data["country_codes"]) if data.get("country_codes") else None,
            epg_source_ids=json.dumps(data["epg_source_ids"]) if data.get("epg_source_ids") else None,
            time_offset_hours=data.get("time_offset_hours", 0),
            priority=data.get("priority", 100),
            enabled=data.get("enabled", True),
            stop_on_match=data.get("stop_on_match", True),
        )
        db.session.add(rule)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return serialize_epg_match_rule(rule)

    @staticmethod
    def update_rule(rule: EpgMatchRule, data: Dict[str, Any]) -> Dict[str, Any]:
        field_map = {
            "name": "name",
            "description": "description",
            "match_type": "match_type",
            "source": "source",
            "pattern": "pattern",
            "action": "action",
            "min_confidence": "min_confidence",
            "fallback_epg_id": "fallback_epg_id",
            "category_pattern": "category_pattern",
            "category_exclude_pattern": "category_exclude_pattern",
            "time_offset_hours": "time_offset_hours",
            "priority": "priority",
            "enabled": "enabled",
            "stop_on_match": "stop_on_match",
        }
        for key, attr in field_map.items():
            if key in data:
                setattr(rule, attr, data[key])
        if "required_tags" in data:
            rule.required_tags = json.dumps(data["required_tags"]) if data["required_tags"] else None
        if "excluded_tags" in data:
            rule.excluded_tags = json.dumps(data["excluded_tags"]) if data["excluded_tags"] else None
        if "country_codes" in data:
            rule.country_codes = json.dumps(data["country_codes"]) if data["country_codes"] else None
        if "epg_source_ids" in data:
            rule.epg_source_ids = json.dumps(data["epg_source_ids"]) if data["epg_source_ids"] else None
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return serialize_epg_match_rule(rule)

    @staticmethod
    def delete_rule(rule: EpgMatchRule) -> None:
        db.session.delete(rule)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()

    @staticmethod
    def list_exclusion_patterns() -> List[Dict[str, Any]]:
        patterns = EpgExclusionPattern.query.order_by(EpgExclusionPattern.priority, EpgExclusionPattern.name).all()
        return [serialize_epg_exclusion_pattern(p) for p in patterns]

    @staticmethod
    def create_exclusion_pattern(data: Dict[str, Any]) -> Dict[str, Any]:
        pattern = EpgExclusionPattern(
            name=data["name"],
            description=data.get("description", ""),
            pattern_type=data["pattern_type"],
            pattern=data["pattern"],
            is_regex=data.get("is_regex", True),
            hide_channel=data.get("hide_channel", False),
            enabled=data.get("enabled", True),
            priority=data.get("priority", 100),
        )
        db.session.add(pattern)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return serialize_epg_exclusion_pattern(pattern)

    @staticmethod
    def update_exclusion_pattern(pattern: EpgExclusionPattern, data: Dict[str, Any]) -> Dict[str, Any]:
        for key in (
            "name",
            "description",
            "pattern_type",
            "pattern",
            "is_regex",
            "hide_channel",
            "enabled",
            "priority",
        ):
            if key in data:
                setattr(pattern, key, data[key])
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return serialize_epg_exclusion_pattern(pattern)

    @staticmethod
    def delete_exclusion_pattern(pattern: EpgExclusionPattern) -> None:
        db.session.delete(pattern)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()

    @staticmethod
    def list_name_mappings() -> List[Dict[str, Any]]:
        mappings = EpgChannelNameMapping.query.order_by(
            EpgChannelNameMapping.priority, EpgChannelNameMapping.name
        ).all()
        return [serialize_epg_channel_name_mapping(m) for m in mappings]

    @staticmethod
    def create_name_mapping(data: Dict[str, Any]) -> Dict[str, Any]:
        mapping = EpgChannelNameMapping(
            name=data["name"],
            description=data.get("description", ""),
            old_name=data["old_name"],
            new_name=data["new_name"],
            match_type=data.get("match_type", "contains"),
            case_sensitive=data.get("case_sensitive", False),
            priority=data.get("priority", 100),
            enabled=data.get("enabled", True),
        )
        db.session.add(mapping)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        clear_fcc_pattern_cache()
        return serialize_epg_channel_name_mapping(mapping)

    @staticmethod
    def update_name_mapping(mapping: EpgChannelNameMapping, data: Dict[str, Any]) -> Dict[str, Any]:
        for key in (
            "name",
            "description",
            "old_name",
            "new_name",
            "match_type",
            "case_sensitive",
            "priority",
            "enabled",
        ):
            if key in data:
                setattr(mapping, key, data[key])
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        clear_fcc_pattern_cache()
        return serialize_epg_channel_name_mapping(mapping)

    @staticmethod
    def delete_name_mapping(mapping: EpgChannelNameMapping) -> None:
        db.session.delete(mapping)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        clear_fcc_pattern_cache()

    @staticmethod
    def list_account_rulesets(account_id: int) -> List[Dict[str, Any]]:
        Account.query.get_or_404(account_id)
        assignments = (
            db.session.query(AccountEpgMatchRuleSet, EpgMatchRuleSet)
            .join(EpgMatchRuleSet, EpgMatchRuleSet.id == AccountEpgMatchRuleSet.ruleset_id)
            .filter(AccountEpgMatchRuleSet.account_id == account_id)
            .order_by(AccountEpgMatchRuleSet.priority)
            .all()
        )
        return [
            {
                "id": a.id,
                "ruleset_id": rs.id,
                "ruleset_name": rs.name,
                "priority": a.priority,
                "enabled": rs.enabled,
                "rule_count": len(rs.rules),
            }
            for a, rs in assignments
        ]

    @staticmethod
    def assign_ruleset_to_account(account_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
        Account.query.get_or_404(account_id)
        ruleset = EpgMatchRuleSet.query.get_or_404(data["ruleset_id"])
        existing = AccountEpgMatchRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset.id).first()
        if existing:
            existing.priority = data.get("priority", 100)
        else:
            db.session.add(
                AccountEpgMatchRuleSet(
                    account_id=account_id,
                    ruleset_id=ruleset.id,
                    priority=data.get("priority", 100),
                )
            )
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return {
            "success": True,
            "message": f"Assigned ruleset '{ruleset.name}' to account",
        }

    @staticmethod
    def unassign_ruleset_from_account(account_id: int, ruleset_id: int) -> None:
        Account.query.get_or_404(account_id)
        assignment = AccountEpgMatchRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset_id).first_or_404()
        db.session.delete(assignment)
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()

    @staticmethod
    def preview_channel_name_mapping(data: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
        old_name = data.get("old_name", "")
        new_name = data.get("new_name", "")
        match_type = data.get("match_type", "contains")
        case_sensitive = data.get("case_sensitive", False)
        account_id = data.get("account_id")

        if not old_name:
            return {"matches": [], "total_count": 0, "error": "old_name is required"}, 200

        if match_type == "regex":
            try:
                re.compile(old_name)
            except re.error as e:
                return {"matches": [], "total_count": 0, "error": f"Invalid regex: {e}"}, 200

        matches: List[Dict[str, Any]] = []
        try:
            query = Channel.query.filter(Channel.is_active == True)  # noqa: E712
            if account_id:
                query = query.filter(Channel.account_id == account_id)
            channels = query.limit(1000).all()
            flags = 0 if case_sensitive else re.IGNORECASE

            for channel in channels:
                name = channel.cleaned_name or channel.name
                if not name:
                    continue
                transformed = None
                matched = False

                if match_type == "exact":
                    if case_sensitive:
                        matched = name == old_name
                    else:
                        matched = name.lower() == old_name.lower()
                    if matched:
                        transformed = new_name
                elif match_type == "contains":
                    if case_sensitive:
                        matched = old_name in name
                    else:
                        matched = old_name.lower() in name.lower()
                    if matched:
                        if case_sensitive:
                            transformed = name.replace(old_name, new_name)
                        else:
                            pattern = re.compile(re.escape(old_name), flags)
                            transformed = pattern.sub(new_name, name)
                elif match_type == "prefix":
                    if case_sensitive:
                        matched = name.startswith(old_name)
                    else:
                        matched = name.lower().startswith(old_name.lower())
                    if matched:
                        transformed = new_name + name[len(old_name) :]
                elif match_type == "suffix":
                    if case_sensitive:
                        matched = name.endswith(old_name)
                    else:
                        matched = name.lower().endswith(old_name.lower())
                    if matched:
                        transformed = name[: -len(old_name)] + new_name
                elif match_type == "regex":
                    try:
                        if re.search(old_name, name, flags):
                            matched = True
                            transformed = re.sub(old_name, new_name, name, flags=flags)
                    except re.error as e:
                        logger.debug("Invalid regex in name mapping preview for pattern %r: %s", old_name, e)

                if matched:
                    matches.append(
                        {
                            "channel_id": channel.id,
                            "stream_id": channel.stream_id,
                            "account_id": channel.account_id,
                            "original_name": name,
                            "transformed_name": transformed,
                        }
                    )
                    if len(matches) >= 100:
                        break
        except Exception as e:
            logger.exception("Error previewing channel name mapping: %s", e)
            return {"matches": [], "total_count": 0, "error": str(e)}, 500

        return (
            {
                "matches": matches,
                "total_count": len(matches),
                "truncated": len(matches) >= 100,
            },
            200,
        )

    @staticmethod
    def preview_exclusion_pattern(data: Dict[str, Any]) -> Dict[str, Any]:
        pattern_type = data.get("pattern_type", "channel_name")
        pattern = data.get("pattern", "")
        is_regex = data.get("is_regex", True)
        account_id = data.get("account_id")

        if not pattern:
            return {"matches": [], "total_count": 0, "error": "Pattern is required"}

        if is_regex:
            try:
                re.compile(pattern)
            except re.error as e:
                return {"matches": [], "total_count": 0, "error": f"Invalid regex: {e}"}

        matches: List[Dict[str, Any]] = []
        total_count = 0

        try:
            if pattern_type == "tag":
                tag_pattern = pattern.upper()
                if is_regex:
                    matching_tags = Tag.query.filter(Tag.name.op("REGEXP")(tag_pattern)).all()
                    if not matching_tags:
                        all_tags = Tag.query.all()
                        try:
                            regex = re.compile(tag_pattern, re.IGNORECASE)
                            matching_tags = [t for t in all_tags if regex.search(t.name)]
                        except re.error:
                            matching_tags = []
                else:
                    matching_tags = Tag.query.filter(Tag.name == tag_pattern).all()

                if matching_tags:
                    tag_ids = [t.id for t in matching_tags]
                    query = (
                        db.session.query(Channel, Category.category_name)
                        .outerjoin(Category, Channel.category_id == Category.id)
                        .join(ChannelTag, ChannelTag.stream_id == Channel.stream_id)
                        .filter(
                            ChannelTag.account_id == Channel.account_id,
                            ChannelTag.tag_id.in_(tag_ids),
                            Channel.is_active,
                        )
                    )
                    if account_id:
                        query = query.filter(Channel.account_id == account_id)
                    total_count = query.distinct().count()
                    results = query.distinct().limit(100).all()
                    for channel, category_name in results:
                        matches.append(
                            {
                                "stream_id": channel.stream_id,
                                "name": channel.name,
                                "cleaned_name": channel.cleaned_name,
                                "category": category_name,
                                "account_id": channel.account_id,
                            }
                        )
            elif pattern_type == "category_name":
                query = (
                    db.session.query(Channel, Category.category_name)
                    .join(Category, Channel.category_id == Category.id)
                    .filter(Channel.is_active)
                )
                if account_id:
                    query = query.filter(Channel.account_id == account_id)
                results = query.all()
                if is_regex:
                    try:
                        regex = re.compile(pattern, re.IGNORECASE)
                        filtered = [(c, cat) for c, cat in results if cat and regex.search(cat)]
                    except re.error:
                        filtered = []
                else:
                    pattern_lower = pattern.lower()
                    filtered = [(c, cat) for c, cat in results if cat and pattern_lower in cat.lower()]
                total_count = len(filtered)
                for channel, category_name in filtered[:100]:
                    matches.append(
                        {
                            "stream_id": channel.stream_id,
                            "name": channel.name,
                            "cleaned_name": channel.cleaned_name,
                            "category": category_name,
                            "account_id": channel.account_id,
                        }
                    )
            elif pattern_type == "channel_name":
                query = (
                    db.session.query(Channel, Category.category_name)
                    .outerjoin(Category, Channel.category_id == Category.id)
                    .filter(Channel.is_active)
                )
                if account_id:
                    query = query.filter(Channel.account_id == account_id)
                results = query.all()
                if is_regex:
                    try:
                        regex = re.compile(pattern, re.IGNORECASE)
                        filtered = [(c, cat) for c, cat in results if c.name and regex.search(c.name)]
                    except re.error:
                        filtered = []
                else:
                    pattern_lower = pattern.lower()
                    filtered = [(c, cat) for c, cat in results if c.name and pattern_lower in c.name.lower()]
                total_count = len(filtered)
                for channel, category_name in filtered[:100]:
                    matches.append(
                        {
                            "stream_id": channel.stream_id,
                            "name": channel.name,
                            "cleaned_name": channel.cleaned_name,
                            "category": category_name,
                            "account_id": channel.account_id,
                        }
                    )
        except Exception as e:
            logger.error("Error previewing exclusion pattern: %s", e)
            return {"matches": [], "total_count": 0, "error": str(e)}

        return {"matches": matches, "total_count": total_count, "showing": len(matches)}

    @staticmethod
    def preview_rule_pattern(data: Dict[str, Any]) -> Dict[str, Any]:
        match_type = data.get("match_type", "regex")
        source = data.get("source", "channel_name")
        pattern = data.get("pattern", "")
        category_pattern = data.get("category_pattern")
        category_exclude_pattern = data.get("category_exclude_pattern")
        account_id = data.get("account_id")

        if match_type in ("regex", "category_pattern") and pattern:
            try:
                re.compile(pattern)
            except re.error as e:
                return {"matches": [], "total_count": 0, "error": f"Invalid regex pattern: {e}"}

        if category_pattern:
            try:
                re.compile(category_pattern)
            except re.error as e:
                return {"matches": [], "total_count": 0, "error": f"Invalid category pattern: {e}"}

        if category_exclude_pattern:
            try:
                re.compile(category_exclude_pattern)
            except re.error as e:
                return {
                    "matches": [],
                    "total_count": 0,
                    "error": f"Invalid category exclude pattern: {e}",
                }

        matches: List[Dict[str, Any]] = []
        total_count = 0

        try:
            query = (
                db.session.query(Channel, Category.category_name)
                .outerjoin(Category, Channel.category_id == Category.id)
                .filter(Channel.is_active)
            )
            if account_id:
                query = query.filter(Channel.account_id == account_id)
            results = query.all()

            if category_pattern:
                try:
                    cat_regex = re.compile(category_pattern, re.IGNORECASE)
                    results = [(c, cat) for c, cat in results if cat and cat_regex.search(cat)]
                except re.error:
                    pass

            if category_exclude_pattern:
                try:
                    cat_excl_regex = re.compile(category_exclude_pattern, re.IGNORECASE)
                    results = [(c, cat) for c, cat in results if not (cat and cat_excl_regex.search(cat))]
                except re.error:
                    pass

            if pattern:
                filtered = []
                for channel, category_name in results:
                    if source == "channel_name":
                        source_value = channel.name
                    elif source == "cleaned_name":
                        source_value = channel.cleaned_name
                    elif source == "category_name":
                        source_value = category_name
                    else:
                        source_value = channel.name

                    if not source_value:
                        continue

                    if match_type == "regex":
                        try:
                            if re.search(pattern, source_value, re.IGNORECASE):
                                filtered.append((channel, category_name))
                        except re.error as e:
                            logger.debug("Invalid regex in rule preview for pattern %r: %s", pattern, e)
                    elif match_type == "exact_name":
                        normalized = re.sub(r"[^a-z0-9]", "", source_value.lower())
                        pattern_normalized = re.sub(r"[^a-z0-9]", "", pattern.lower())
                        if normalized == pattern_normalized:
                            filtered.append((channel, category_name))
                    elif match_type == "fuzzy_name":
                        if pattern.lower() in source_value.lower():
                            filtered.append((channel, category_name))
                    else:
                        filtered.append((channel, category_name))
                results = filtered

            total_count = len(results)
            for channel, category_name in results[:100]:
                matches.append(
                    {
                        "stream_id": channel.stream_id,
                        "name": channel.name,
                        "cleaned_name": channel.cleaned_name,
                        "category": category_name,
                        "account_id": channel.account_id,
                        "epg_channel_id": channel.epg_channel_id,
                    }
                )
        except Exception as e:
            logger.error("Error previewing rule pattern: %s", e)
            return {"matches": [], "total_count": 0, "error": str(e)}

        return {"matches": matches, "total_count": total_count, "showing": len(matches)}

    @staticmethod
    def create_default_epg_match_ruleset() -> Tuple[Dict[str, Any], int]:
        existing = EpgMatchRuleSet.query.filter_by(name="Default EPG Matching").first()
        if existing:
            return (
                {
                    "success": False,
                    "error": "Default EPG match ruleset already exists",
                    "id": existing.id,
                },
                400,
            )
        ruleset = EpgMatchRuleSet(
            name="Default EPG Matching",
            description="Standard EPG matching rules for IPTV channels",
            is_default=True,
            enabled=True,
            priority=100,
        )
        db.session.add(ruleset)
        db.session.flush()
        for rule_data in DEFAULT_EPG_MATCH_RULES:
            db.session.add(
                EpgMatchRule(
                    ruleset_id=ruleset.id,
                    name=rule_data["name"],
                    description=rule_data.get("description", ""),
                    match_type=rule_data["match_type"],
                    source=rule_data.get("source", "cleaned_name"),
                    min_confidence=rule_data.get("min_confidence", 0.75),
                    priority=rule_data.get("priority", 100),
                    enabled=True,
                    stop_on_match=True,
                )
            )
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return (
            {
                "success": True,
                "id": ruleset.id,
                "name": ruleset.name,
                "rule_count": len(DEFAULT_EPG_MATCH_RULES),
                "message": f"Created default EPG match ruleset with {len(DEFAULT_EPG_MATCH_RULES)} rules",
            },
            200,
        )

    @staticmethod
    def create_default_exclusion_patterns() -> Dict[str, Any]:
        patterns_created = 0
        patterns_skipped = 0
        for pattern_data in DEFAULT_EXCLUSION_PATTERNS:
            existing = EpgExclusionPattern.query.filter_by(name=pattern_data["name"]).first()
            if existing:
                patterns_skipped += 1
                continue
            db.session.add(
                EpgExclusionPattern(
                    name=pattern_data["name"],
                    description=pattern_data.get("description", ""),
                    pattern_type=pattern_data["pattern_type"],
                    pattern=pattern_data["pattern"],
                    is_regex=pattern_data.get("is_regex", True),
                    hide_channel=pattern_data.get("hide_channel", False),
                    enabled=True,
                    priority=pattern_data.get("priority", 100),
                )
            )
            patterns_created += 1
        db.session.commit()
        EpgMatchRulesRouteService._clear_cache()
        return {
            "success": True,
            "patterns_created": patterns_created,
            "patterns_skipped": patterns_skipped,
            "message": (f"Created {patterns_created} exclusion patterns, skipped {patterns_skipped} existing"),
        }

    @staticmethod
    def get_match_types() -> Dict[str, Any]:
        return MATCH_TYPES_INFO
