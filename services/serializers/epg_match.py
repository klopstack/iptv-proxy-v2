"""Serializers for EPG match rules, rulesets, and related config entities."""

from typing import Any, Callable

from models import EpgChannelNameMapping, EpgExclusionPattern, EpgMatchRule, EpgMatchRuleSet, RuleSet, TagRule
from services.datetime_utils import serialize_utc_iso
from services.serializers._json import safe_json_loads

_RULE_SORT_KEY: Callable[[EpgMatchRule], tuple] = lambda rule: (rule.priority, rule.id)
_TAG_RULE_SORT_KEY: Callable[[TagRule], tuple] = lambda rule: (rule.priority, rule.id)


def serialize_epg_match_rule(
    rule: EpgMatchRule,
    *,
    include_id: bool = True,
    include_ruleset_id: bool = True,
) -> dict[str, Any]:
    """Serialize an EPG match rule."""
    data = {
        "name": rule.name,
        "description": rule.description,
        "match_type": rule.match_type,
        "source": rule.source,
        "pattern": rule.pattern,
        "action": rule.action,
        "min_confidence": rule.min_confidence,
        "required_tags": safe_json_loads(rule.required_tags),
        "excluded_tags": safe_json_loads(rule.excluded_tags),
        "fallback_epg_id": rule.fallback_epg_id,
        "category_pattern": rule.category_pattern,
        "category_exclude_pattern": rule.category_exclude_pattern,
        "country_codes": safe_json_loads(rule.country_codes),
        "epg_source_ids": safe_json_loads(rule.epg_source_ids),
        "time_offset_hours": rule.time_offset_hours,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "stop_on_match": rule.stop_on_match,
    }
    if include_id:
        data["id"] = rule.id
    if include_ruleset_id:
        data["ruleset_id"] = rule.ruleset_id
    return data


def serialize_epg_exclusion_pattern(pattern: EpgExclusionPattern, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an EPG exclusion pattern."""
    data = {
        "name": pattern.name,
        "description": pattern.description,
        "pattern_type": pattern.pattern_type,
        "pattern": pattern.pattern,
        "is_regex": pattern.is_regex,
        "hide_channel": pattern.hide_channel,
        "enabled": pattern.enabled,
        "priority": pattern.priority,
    }
    if include_id:
        data["id"] = pattern.id
    return data


def serialize_epg_channel_name_mapping(mapping: EpgChannelNameMapping, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an EPG channel name mapping."""
    data = {
        "name": mapping.name,
        "description": mapping.description,
        "old_name": mapping.old_name,
        "new_name": mapping.new_name,
        "match_type": mapping.match_type,
        "case_sensitive": mapping.case_sensitive,
        "priority": mapping.priority,
        "enabled": mapping.enabled,
    }
    if include_id:
        data["id"] = mapping.id
        data["created_at"] = serialize_utc_iso(mapping.created_at)
        data["updated_at"] = serialize_utc_iso(mapping.updated_at)
    return data


def serialize_tag_rule(rule: TagRule, *, include_id: bool = False) -> dict[str, Any]:
    """Serialize a tag rule (export bundles omit database ids)."""
    data = {
        "name": rule.name,
        "pattern": rule.pattern,
        "pattern_type": rule.pattern_type,
        "tag_name": rule.tag_name,
        "source": rule.source,
        "remove_from_name": rule.remove_from_name,
        "replacement": rule.replacement,
        "set_is_ppv": rule.set_is_ppv,
        "priority": rule.priority,
        "enabled": rule.enabled,
    }
    if include_id:
        data["id"] = rule.id
    return data


def serialize_ruleset(ruleset: RuleSet, *, include_rules: bool = True) -> dict[str, Any]:
    """Serialize a tag ruleset for config export."""
    data = {
        "name": ruleset.name,
        "description": ruleset.description,
        "is_default": ruleset.is_default,
        "enabled": ruleset.enabled,
        "priority": ruleset.priority,
    }
    if include_rules:
        data["rules"] = [serialize_tag_rule(rule) for rule in sorted(ruleset.rules, key=_TAG_RULE_SORT_KEY)]
    return data


def serialize_epg_ruleset(ruleset: EpgMatchRuleSet, *, include_rules: bool = True) -> dict[str, Any]:
    """Serialize an EPG match ruleset for config export."""
    data = {
        "name": ruleset.name,
        "description": ruleset.description,
        "is_default": ruleset.is_default,
        "enabled": ruleset.enabled,
        "priority": ruleset.priority,
    }
    if include_rules:
        data["rules"] = [
            serialize_epg_match_rule(rule, include_id=False, include_ruleset_id=False)
            for rule in sorted(ruleset.rules, key=_RULE_SORT_KEY)
        ]
    return data
