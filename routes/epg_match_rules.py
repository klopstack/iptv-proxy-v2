"""
EPG Match Rules management routes

Provides API endpoints for managing EPG matching rulesets, rules, and exclusion patterns.
Similar to the tag rulesets system but for EPG channel matching configuration.
"""
import json
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import (
    Account,
    AccountEpgMatchRuleSet,
    EpgChannelNameMapping,
    EpgExclusionPattern,
    EpgMatchRule,
    EpgMatchRuleSet,
    db,
)
from schemas import (
    AccountEpgMatchRuleSetAssignSchema,
    EpgChannelNameMappingCreateSchema,
    EpgChannelNameMappingUpdateSchema,
    EpgExclusionPatternCreateSchema,
    EpgExclusionPatternUpdateSchema,
    EpgMatchRuleCreateSchema,
    EpgMatchRuleSetCreateSchema,
    EpgMatchRuleSetUpdateSchema,
    EpgMatchRuleUpdateSchema,
    validate_request_data,
)
from services.cache_service import CacheService
from services.epg_match_rules_service import clear_fcc_pattern_cache

logger = logging.getLogger(__name__)

# Create blueprint
epg_match_rules_bp = Blueprint("epg_match_rules", __name__)

# Initialize cache service
cache_service = CacheService()


# ============================================================================
# Helper Functions
# ============================================================================


def _serialize_epg_match_rule(rule: EpgMatchRule) -> dict:
    """Serialize an EPG match rule to JSON-compatible dict"""
    return {
        "id": rule.id,
        "ruleset_id": rule.ruleset_id,
        "name": rule.name,
        "description": rule.description,
        "match_type": rule.match_type,
        "source": rule.source,
        "pattern": rule.pattern,
        "action": rule.action,
        "min_confidence": rule.min_confidence,
        "required_tags": json.loads(rule.required_tags) if rule.required_tags else None,
        "excluded_tags": json.loads(rule.excluded_tags) if rule.excluded_tags else None,
        "fallback_epg_id": rule.fallback_epg_id,
        "category_pattern": rule.category_pattern,
        "category_exclude_pattern": rule.category_exclude_pattern,
        "country_codes": json.loads(rule.country_codes) if rule.country_codes else None,
        "epg_source_ids": json.loads(rule.epg_source_ids) if rule.epg_source_ids else None,
        "time_offset_hours": rule.time_offset_hours,
        "priority": rule.priority,
        "enabled": rule.enabled,
        "stop_on_match": rule.stop_on_match,
    }


def _serialize_exclusion_pattern(pattern: EpgExclusionPattern) -> dict:
    """Serialize an EPG exclusion pattern to JSON-compatible dict"""
    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "pattern_type": pattern.pattern_type,
        "pattern": pattern.pattern,
        "is_regex": pattern.is_regex,
        "hide_channel": pattern.hide_channel,
        "enabled": pattern.enabled,
        "priority": pattern.priority,
    }


def _serialize_channel_name_mapping(mapping: EpgChannelNameMapping) -> dict:
    """Serialize an EPG channel name mapping to JSON-compatible dict"""
    return {
        "id": mapping.id,
        "name": mapping.name,
        "description": mapping.description,
        "old_name": mapping.old_name,
        "new_name": mapping.new_name,
        "match_type": mapping.match_type,
        "case_sensitive": mapping.case_sensitive,
        "priority": mapping.priority,
        "enabled": mapping.enabled,
        "created_at": mapping.created_at.isoformat() if mapping.created_at else None,
        "updated_at": mapping.updated_at.isoformat() if mapping.updated_at else None,
    }


# ============================================================================
# API Routes - EPG Match Rulesets
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/rulesets", methods=["GET"])
def get_epg_match_rulesets():
    """Get all EPG match rulesets with assigned accounts"""
    rulesets = EpgMatchRuleSet.query.order_by(EpgMatchRuleSet.priority, EpgMatchRuleSet.name).all()

    # Get all account assignments in one query
    assignments = (
        db.session.query(AccountEpgMatchRuleSet.ruleset_id, Account.id, Account.name)
        .join(Account, Account.id == AccountEpgMatchRuleSet.account_id)
        .all()
    )

    # Build a map of ruleset_id -> list of assigned accounts
    ruleset_accounts = {}
    for ruleset_id, account_id, account_name in assignments:
        if ruleset_id not in ruleset_accounts:
            ruleset_accounts[ruleset_id] = []
        ruleset_accounts[ruleset_id].append({"id": account_id, "name": account_name})

    return jsonify(
        [
            {
                "id": rs.id,
                "name": rs.name,
                "description": rs.description,
                "is_default": rs.is_default,
                "enabled": rs.enabled,
                "priority": rs.priority,
                "rule_count": len(rs.rules),
                "assigned_accounts": ruleset_accounts.get(rs.id, []),
            }
            for rs in rulesets
        ]
    )


@epg_match_rules_bp.route("/api/epg-match-rules/rulesets", methods=["POST"])
@validate_request_data(EpgMatchRuleSetCreateSchema)
def create_epg_match_ruleset():
    """Create a new EPG match ruleset"""
    data = request.validated_data

    # Check for duplicate name
    existing = EpgMatchRuleSet.query.filter_by(name=data["name"]).first()
    if existing:
        return jsonify({"error": f"Ruleset with name '{data['name']}' already exists"}), 409

    ruleset = EpgMatchRuleSet(
        name=data["name"],
        description=data.get("description", ""),
        is_default=data.get("is_default", False),
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(ruleset)
    db.session.commit()
    cache_service.clear_all()

    return (
        jsonify(
            {
                "id": ruleset.id,
                "name": ruleset.name,
                "description": ruleset.description,
                "is_default": ruleset.is_default,
                "enabled": ruleset.enabled,
                "priority": ruleset.priority,
                "rule_count": 0,
            }
        ),
        201,
    )


@epg_match_rules_bp.route("/api/epg-match-rules/rulesets/<int:ruleset_id>", methods=["GET"])
def get_epg_match_ruleset(ruleset_id):
    """Get a specific EPG match ruleset with its rules"""
    ruleset = EpgMatchRuleSet.query.get_or_404(ruleset_id)

    return jsonify(
        {
            "id": ruleset.id,
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rules": [_serialize_epg_match_rule(r) for r in sorted(ruleset.rules, key=lambda x: (x.priority, x.id))],
        }
    )


@epg_match_rules_bp.route("/api/epg-match-rules/rulesets/<int:ruleset_id>", methods=["PUT"])
@validate_request_data(EpgMatchRuleSetUpdateSchema)
def update_epg_match_ruleset(ruleset_id):
    """Update an EPG match ruleset"""
    ruleset = EpgMatchRuleSet.query.get_or_404(ruleset_id)
    data = request.validated_data

    ruleset.name = data.get("name", ruleset.name)
    ruleset.description = data.get("description", ruleset.description)
    ruleset.is_default = data.get("is_default", ruleset.is_default)
    ruleset.enabled = data.get("enabled", ruleset.enabled)
    ruleset.priority = data.get("priority", ruleset.priority)

    db.session.commit()
    cache_service.clear_all()

    return jsonify(
        {
            "id": ruleset.id,
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rule_count": len(ruleset.rules),
        }
    )


@epg_match_rules_bp.route("/api/epg-match-rules/rulesets/<int:ruleset_id>", methods=["DELETE"])
def delete_epg_match_ruleset(ruleset_id):
    """Delete an EPG match ruleset"""
    ruleset = EpgMatchRuleSet.query.get_or_404(ruleset_id)

    # Remove account associations
    AccountEpgMatchRuleSet.query.filter_by(ruleset_id=ruleset_id).delete()

    db.session.delete(ruleset)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


@epg_match_rules_bp.route("/api/epg-match-rules/rulesets/<int:ruleset_id>/duplicate", methods=["POST"])
def duplicate_epg_match_ruleset(ruleset_id):
    """Duplicate an EPG match ruleset with all its rules"""
    source = EpgMatchRuleSet.query.get_or_404(ruleset_id)

    # Generate unique name
    base_name = f"{source.name} (Copy)"
    counter = 1
    new_name = base_name
    while EpgMatchRuleSet.query.filter_by(name=new_name).first():
        counter += 1
        new_name = f"{base_name} {counter}"

    # Create new ruleset
    new_ruleset = EpgMatchRuleSet(
        name=new_name,
        description=source.description,
        is_default=False,  # Never duplicate as default
        enabled=source.enabled,
        priority=source.priority + 10,
    )
    db.session.add(new_ruleset)
    db.session.flush()  # Get the new ID

    # Duplicate all rules
    for rule in source.rules:
        new_rule = EpgMatchRule(
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
        db.session.add(new_rule)

    db.session.commit()
    cache_service.clear_all()

    return (
        jsonify(
            {
                "id": new_ruleset.id,
                "name": new_ruleset.name,
                "rule_count": len(source.rules),
                "message": f"Duplicated ruleset with {len(source.rules)} rules",
            }
        ),
        201,
    )


# ============================================================================
# API Routes - EPG Match Rules
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/rules", methods=["GET"])
def get_epg_match_rules():
    """Get all EPG match rules, optionally filtered by ruleset"""
    ruleset_id = request.args.get("ruleset_id", type=int)

    query = EpgMatchRule.query
    if ruleset_id:
        query = query.filter_by(ruleset_id=ruleset_id)

    rules = query.order_by(EpgMatchRule.priority, EpgMatchRule.id).all()

    return jsonify([_serialize_epg_match_rule(r) for r in rules])


@epg_match_rules_bp.route("/api/epg-match-rules/rules", methods=["POST"])
@validate_request_data(EpgMatchRuleCreateSchema)
def create_epg_match_rule():
    """Create a new EPG match rule"""
    data = request.validated_data

    # Verify ruleset exists
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
    cache_service.clear_all()

    return jsonify(_serialize_epg_match_rule(rule)), 201


@epg_match_rules_bp.route("/api/epg-match-rules/rules/<int:rule_id>", methods=["GET"])
def get_epg_match_rule(rule_id):
    """Get a specific EPG match rule"""
    rule = EpgMatchRule.query.get_or_404(rule_id)
    return jsonify(_serialize_epg_match_rule(rule))


@epg_match_rules_bp.route("/api/epg-match-rules/rules/<int:rule_id>", methods=["PUT"])
@validate_request_data(EpgMatchRuleUpdateSchema)
def update_epg_match_rule(rule_id):
    """Update an EPG match rule"""
    rule = EpgMatchRule.query.get_or_404(rule_id)
    data = request.validated_data

    if "name" in data:
        rule.name = data["name"]
    if "description" in data:
        rule.description = data["description"]
    if "match_type" in data:
        rule.match_type = data["match_type"]
    if "source" in data:
        rule.source = data["source"]
    if "pattern" in data:
        rule.pattern = data["pattern"]
    if "action" in data:
        rule.action = data["action"]
    if "min_confidence" in data:
        rule.min_confidence = data["min_confidence"]
    if "required_tags" in data:
        rule.required_tags = json.dumps(data["required_tags"]) if data["required_tags"] else None
    if "excluded_tags" in data:
        rule.excluded_tags = json.dumps(data["excluded_tags"]) if data["excluded_tags"] else None
    if "fallback_epg_id" in data:
        rule.fallback_epg_id = data["fallback_epg_id"]
    if "category_pattern" in data:
        rule.category_pattern = data["category_pattern"]
    if "category_exclude_pattern" in data:
        rule.category_exclude_pattern = data["category_exclude_pattern"]
    if "country_codes" in data:
        rule.country_codes = json.dumps(data["country_codes"]) if data["country_codes"] else None
    if "epg_source_ids" in data:
        rule.epg_source_ids = json.dumps(data["epg_source_ids"]) if data["epg_source_ids"] else None
    if "time_offset_hours" in data:
        rule.time_offset_hours = data["time_offset_hours"]
    if "priority" in data:
        rule.priority = data["priority"]
    if "enabled" in data:
        rule.enabled = data["enabled"]
    if "stop_on_match" in data:
        rule.stop_on_match = data["stop_on_match"]

    db.session.commit()
    cache_service.clear_all()

    return jsonify(_serialize_epg_match_rule(rule))


@epg_match_rules_bp.route("/api/epg-match-rules/rules/<int:rule_id>", methods=["DELETE"])
def delete_epg_match_rule(rule_id):
    """Delete an EPG match rule"""
    rule = EpgMatchRule.query.get_or_404(rule_id)

    db.session.delete(rule)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


# ============================================================================
# API Routes - EPG Exclusion Patterns
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/exclusions", methods=["GET"])
def get_epg_exclusion_patterns():
    """Get all EPG exclusion patterns"""
    patterns = EpgExclusionPattern.query.order_by(EpgExclusionPattern.priority, EpgExclusionPattern.name).all()

    return jsonify([_serialize_exclusion_pattern(p) for p in patterns])


@epg_match_rules_bp.route("/api/epg-match-rules/exclusions", methods=["POST"])
@validate_request_data(EpgExclusionPatternCreateSchema)
def create_epg_exclusion_pattern():
    """Create a new EPG exclusion pattern"""
    data = request.validated_data

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
    cache_service.clear_all()

    return jsonify(_serialize_exclusion_pattern(pattern)), 201


@epg_match_rules_bp.route("/api/epg-match-rules/exclusions/<int:pattern_id>", methods=["GET"])
def get_epg_exclusion_pattern(pattern_id):
    """Get a specific EPG exclusion pattern"""
    pattern = EpgExclusionPattern.query.get_or_404(pattern_id)
    return jsonify(_serialize_exclusion_pattern(pattern))


@epg_match_rules_bp.route("/api/epg-match-rules/exclusions/<int:pattern_id>", methods=["PUT"])
@validate_request_data(EpgExclusionPatternUpdateSchema)
def update_epg_exclusion_pattern(pattern_id):
    """Update an EPG exclusion pattern"""
    pattern = EpgExclusionPattern.query.get_or_404(pattern_id)
    data = request.validated_data

    if "name" in data:
        pattern.name = data["name"]
    if "description" in data:
        pattern.description = data["description"]
    if "pattern_type" in data:
        pattern.pattern_type = data["pattern_type"]
    if "pattern" in data:
        pattern.pattern = data["pattern"]
    if "is_regex" in data:
        pattern.is_regex = data["is_regex"]
    if "hide_channel" in data:
        pattern.hide_channel = data["hide_channel"]
    if "enabled" in data:
        pattern.enabled = data["enabled"]
    if "priority" in data:
        pattern.priority = data["priority"]

    db.session.commit()
    cache_service.clear_all()

    return jsonify(_serialize_exclusion_pattern(pattern))


@epg_match_rules_bp.route("/api/epg-match-rules/exclusions/<int:pattern_id>", methods=["DELETE"])
def delete_epg_exclusion_pattern(pattern_id):
    """Delete an EPG exclusion pattern"""
    pattern = EpgExclusionPattern.query.get_or_404(pattern_id)

    db.session.delete(pattern)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


# ============================================================================
# API Routes - EPG Channel Name Mappings
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/name-mappings", methods=["GET"])
def get_epg_channel_name_mappings():
    """Get all EPG channel name mappings"""
    mappings = EpgChannelNameMapping.query.order_by(EpgChannelNameMapping.priority, EpgChannelNameMapping.name).all()

    return jsonify([_serialize_channel_name_mapping(m) for m in mappings])


@epg_match_rules_bp.route("/api/epg-match-rules/name-mappings", methods=["POST"])
@validate_request_data(EpgChannelNameMappingCreateSchema)
def create_epg_channel_name_mapping():
    """Create a new EPG channel name mapping"""
    data = request.validated_data

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
    cache_service.clear_all()
    clear_fcc_pattern_cache()

    return jsonify(_serialize_channel_name_mapping(mapping)), 201


@epg_match_rules_bp.route("/api/epg-match-rules/name-mappings/<int:mapping_id>", methods=["GET"])
def get_epg_channel_name_mapping(mapping_id):
    """Get a specific EPG channel name mapping"""
    mapping = EpgChannelNameMapping.query.get_or_404(mapping_id)
    return jsonify(_serialize_channel_name_mapping(mapping))


@epg_match_rules_bp.route("/api/epg-match-rules/name-mappings/<int:mapping_id>", methods=["PUT"])
@validate_request_data(EpgChannelNameMappingUpdateSchema)
def update_epg_channel_name_mapping(mapping_id):
    """Update an EPG channel name mapping"""
    mapping = EpgChannelNameMapping.query.get_or_404(mapping_id)
    data = request.validated_data

    if "name" in data:
        mapping.name = data["name"]
    if "description" in data:
        mapping.description = data["description"]
    if "old_name" in data:
        mapping.old_name = data["old_name"]
    if "new_name" in data:
        mapping.new_name = data["new_name"]
    if "match_type" in data:
        mapping.match_type = data["match_type"]
    if "case_sensitive" in data:
        mapping.case_sensitive = data["case_sensitive"]
    if "priority" in data:
        mapping.priority = data["priority"]
    if "enabled" in data:
        mapping.enabled = data["enabled"]

    db.session.commit()
    cache_service.clear_all()
    clear_fcc_pattern_cache()

    return jsonify(_serialize_channel_name_mapping(mapping))


@epg_match_rules_bp.route("/api/epg-match-rules/name-mappings/<int:mapping_id>", methods=["DELETE"])
def delete_epg_channel_name_mapping(mapping_id):
    """Delete an EPG channel name mapping"""
    mapping = EpgChannelNameMapping.query.get_or_404(mapping_id)

    db.session.delete(mapping)
    db.session.commit()
    cache_service.clear_all()
    clear_fcc_pattern_cache()

    return "", 204


@epg_match_rules_bp.route("/api/epg-match-rules/name-mappings/preview", methods=["POST"])
def preview_channel_name_mapping():
    """
    Preview how a channel name mapping would transform channel names.

    Request body:
        old_name: The pattern to match
        new_name: The replacement text
        match_type: 'exact', 'contains', 'prefix', 'suffix', or 'regex'
        case_sensitive: Whether matching is case-sensitive
        account_id: Optional account to filter by

    Returns:
        List of channels that would match, with their transformed names
    """
    import re

    from models import Channel

    data = request.get_json() or {}
    old_name = data.get("old_name", "")
    new_name = data.get("new_name", "")
    match_type = data.get("match_type", "contains")
    case_sensitive = data.get("case_sensitive", False)
    account_id = data.get("account_id")

    if not old_name:
        return jsonify({"matches": [], "total_count": 0, "error": "old_name is required"})

    # Validate regex if needed
    if match_type == "regex":
        try:
            re.compile(old_name)
        except re.error as e:
            return jsonify({"matches": [], "total_count": 0, "error": f"Invalid regex: {e}"})

    matches = []

    try:
        # Build query
        query = Channel.query.filter(Channel.is_active == True)  # noqa: E712
        if account_id:
            query = query.filter(Channel.account_id == account_id)

        # Get channels and test the mapping
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
                        # Case-insensitive replacement
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
                except re.error:
                    pass

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
        logger.exception(f"Error previewing channel name mapping: {e}")
        return jsonify({"matches": [], "total_count": 0, "error": str(e)}), 500

    return jsonify(
        {
            "matches": matches,
            "total_count": len(matches),
            "truncated": len(matches) >= 100,
        }
    )


# ============================================================================
# API Routes - Preview/Test Patterns
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/exclusions/preview", methods=["POST"])
def preview_exclusion_pattern():
    """
    Preview which channels would match an exclusion pattern.

    Request body:
        pattern_type: 'category_name', 'channel_name', or 'tag'
        pattern: The pattern string to test
        is_regex: Whether to treat pattern as regex
        account_id: Optional account to filter by

    Returns:
        List of matching channels (limited to 100)
    """
    import re

    from models import Category, Channel, ChannelTag, Tag

    data = request.get_json() or {}
    pattern_type = data.get("pattern_type", "channel_name")
    pattern = data.get("pattern", "")
    is_regex = data.get("is_regex", True)
    account_id = data.get("account_id")

    if not pattern:
        return jsonify({"matches": [], "total_count": 0, "error": "Pattern is required"})

    # Validate regex if needed
    if is_regex:
        try:
            re.compile(pattern)
        except re.error as e:
            return jsonify({"matches": [], "total_count": 0, "error": f"Invalid regex: {e}"})

    matches = []
    total_count = 0

    try:
        if pattern_type == "tag":
            # For tag patterns, find channels with matching tags
            tag_pattern = pattern.upper()

            # Get matching tags
            if is_regex:
                matching_tags = Tag.query.filter(Tag.name.op("REGEXP")(tag_pattern)).all()
                # SQLite may not have REGEXP, fallback to Python filtering
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

                # Build query for channels with these tags
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

                # Get total count
                total_count = query.distinct().count()

                # Get sample of matches
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
            # Match against category names
            query = (
                db.session.query(Channel, Category.category_name)
                .join(Category, Channel.category_id == Category.id)
                .filter(Channel.is_active)
            )

            if account_id:
                query = query.filter(Channel.account_id == account_id)

            # Get all categories and filter
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
            # Match against channel names
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
        logger.error(f"Error previewing exclusion pattern: {e}")
        return jsonify({"matches": [], "total_count": 0, "error": str(e)})

    return jsonify({"matches": matches, "total_count": total_count, "showing": len(matches)})


@epg_match_rules_bp.route("/api/epg-match-rules/rules/preview", methods=["POST"])
def preview_rule_pattern():
    """
    Preview which channels would match a rule's pattern.

    Request body:
        match_type: The match type (e.g., 'regex', 'category_pattern')
        source: 'channel_name', 'cleaned_name', 'category_name'
        pattern: The pattern string to test
        category_pattern: Optional category filter
        category_exclude_pattern: Optional category exclusion
        account_id: Optional account to filter by

    Returns:
        List of matching channels (limited to 100)
    """
    import re

    from models import Category, Channel

    data = request.get_json() or {}
    match_type = data.get("match_type", "regex")
    source = data.get("source", "channel_name")
    pattern = data.get("pattern", "")
    category_pattern = data.get("category_pattern")
    category_exclude_pattern = data.get("category_exclude_pattern")
    account_id = data.get("account_id")

    # Validate the pattern if it's a regex type
    if match_type in ("regex", "category_pattern") and pattern:
        try:
            re.compile(pattern)
        except re.error as e:
            return jsonify({"matches": [], "total_count": 0, "error": f"Invalid regex pattern: {e}"})

    if category_pattern:
        try:
            re.compile(category_pattern)
        except re.error as e:
            return jsonify({"matches": [], "total_count": 0, "error": f"Invalid category pattern: {e}"})

    if category_exclude_pattern:
        try:
            re.compile(category_exclude_pattern)
        except re.error as e:
            return jsonify({"matches": [], "total_count": 0, "error": f"Invalid category exclude pattern: {e}"})

    matches = []
    total_count = 0

    try:
        # Build base query
        query = (
            db.session.query(Channel, Category.category_name)
            .outerjoin(Category, Channel.category_id == Category.id)
            .filter(Channel.is_active)
        )

        if account_id:
            query = query.filter(Channel.account_id == account_id)

        results = query.all()

        # Filter by category pattern if specified
        if category_pattern:
            try:
                cat_regex = re.compile(category_pattern, re.IGNORECASE)
                results = [(c, cat) for c, cat in results if cat and cat_regex.search(cat)]
            except re.error:
                pass

        # Filter by category exclude pattern if specified
        if category_exclude_pattern:
            try:
                cat_excl_regex = re.compile(category_exclude_pattern, re.IGNORECASE)
                results = [(c, cat) for c, cat in results if not (cat and cat_excl_regex.search(cat))]
            except re.error:
                pass

        # Apply the main pattern based on source
        if pattern:
            filtered = []

            for channel, category_name in results:
                # Get the source value
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

                # Apply pattern matching
                if match_type == "regex":
                    try:
                        if re.search(pattern, source_value, re.IGNORECASE):
                            filtered.append((channel, category_name))
                    except re.error:
                        pass
                elif match_type == "exact_name":
                    # Normalize and compare
                    normalized = re.sub(r"[^a-z0-9]", "", source_value.lower())
                    pattern_normalized = re.sub(r"[^a-z0-9]", "", pattern.lower())
                    if normalized == pattern_normalized:
                        filtered.append((channel, category_name))
                elif match_type == "fuzzy_name":
                    # Simple contains check for preview
                    if pattern.lower() in source_value.lower():
                        filtered.append((channel, category_name))
                else:
                    # For other match types, just show all that pass category filters
                    filtered.append((channel, category_name))

            results = filtered
        else:
            # No pattern, show all that pass category filters
            pass

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
        logger.error(f"Error previewing rule pattern: {e}")
        return jsonify({"matches": [], "total_count": 0, "error": str(e)})

    return jsonify({"matches": matches, "total_count": total_count, "showing": len(matches)})


# ============================================================================
# API Routes - Account Ruleset Assignments
# ============================================================================


@epg_match_rules_bp.route("/api/accounts/<int:account_id>/epg-match-rulesets", methods=["GET"])
def get_account_epg_match_rulesets(account_id):
    """Get EPG match rulesets assigned to an account"""
    Account.query.get_or_404(account_id)

    assignments = (
        db.session.query(AccountEpgMatchRuleSet, EpgMatchRuleSet)
        .join(EpgMatchRuleSet, EpgMatchRuleSet.id == AccountEpgMatchRuleSet.ruleset_id)
        .filter(AccountEpgMatchRuleSet.account_id == account_id)
        .order_by(AccountEpgMatchRuleSet.priority)
        .all()
    )

    return jsonify(
        [
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
    )


@epg_match_rules_bp.route("/api/accounts/<int:account_id>/epg-match-rulesets", methods=["POST"])
@validate_request_data(AccountEpgMatchRuleSetAssignSchema)
def assign_epg_match_ruleset_to_account(account_id):
    """Assign an EPG match ruleset to an account"""
    Account.query.get_or_404(account_id)
    data = request.validated_data

    ruleset = EpgMatchRuleSet.query.get_or_404(data["ruleset_id"])

    # Check if already assigned
    existing = AccountEpgMatchRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset.id).first()

    if existing:
        # Update priority
        existing.priority = data.get("priority", 100)
    else:
        assignment = AccountEpgMatchRuleSet(
            account_id=account_id,
            ruleset_id=ruleset.id,
            priority=data.get("priority", 100),
        )
        db.session.add(assignment)

    db.session.commit()
    cache_service.clear_all()

    return (
        jsonify(
            {
                "success": True,
                "message": f"Assigned ruleset '{ruleset.name}' to account",
            }
        ),
        201,
    )


@epg_match_rules_bp.route("/api/accounts/<int:account_id>/epg-match-rulesets/<int:ruleset_id>", methods=["DELETE"])
def unassign_epg_match_ruleset_from_account(account_id, ruleset_id):
    """Remove an EPG match ruleset assignment from an account"""
    Account.query.get_or_404(account_id)

    assignment = AccountEpgMatchRuleSet.query.filter_by(account_id=account_id, ruleset_id=ruleset_id).first_or_404()

    db.session.delete(assignment)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


# ============================================================================
# API Routes - Default Ruleset Creation
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/create-default", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating default EPG match ruleset")
def create_default_epg_match_ruleset():
    """Create a default EPG match ruleset with common matching rules"""

    # Check if default already exists
    existing = EpgMatchRuleSet.query.filter_by(name="Default EPG Matching").first()
    if existing:
        return (
            jsonify(
                {
                    "success": False,
                    "error": "Default EPG match ruleset already exists",
                    "id": existing.id,
                }
            ),
            400,
        )

    # Create the ruleset
    ruleset = EpgMatchRuleSet(
        name="Default EPG Matching",
        description="Standard EPG matching rules for IPTV channels",
        is_default=True,
        enabled=True,
        priority=100,
    )
    db.session.add(ruleset)
    db.session.flush()

    # Define default rules
    default_rules = [
        # 1. Provider-assigned EPG ID (highest priority)
        {
            "name": "Provider EPG ID",
            "description": "Match using provider-assigned EPG channel ID",
            "match_type": "provider_id",
            "priority": 10,
        },
        # 2. Callsign tag matching
        {
            "name": "Callsign Tag Match",
            "description": "Match using channel's callsign tags (e.g., KABC, WNBC)",
            "match_type": "callsign_tag",
            "priority": 20,
        },
        # 3. FCC database lookup
        {
            "name": "FCC Database Lookup",
            "description": "Look up callsign from FCC data using location and network tags",
            "match_type": "fcc_lookup",
            "priority": 30,
        },
        # 4. Callsign from name
        {
            "name": "Callsign from Name",
            "description": "Extract callsign from cleaned channel name",
            "match_type": "callsign_name",
            "priority": 40,
        },
        # 5. Exact name match
        {
            "name": "Exact Name Match",
            "description": "Match on exact normalized channel name",
            "match_type": "exact_name",
            "source": "cleaned_name",
            "priority": 50,
        },
        # 6. Fuzzy name match
        {
            "name": "Fuzzy Name Match",
            "description": "Fuzzy matching on channel name (75% threshold)",
            "match_type": "fuzzy_name",
            "source": "cleaned_name",
            "min_confidence": 0.75,
            "priority": 60,
        },
        # 7. Network fallback
        {
            "name": "Network Fallback",
            "description": "Use generic network EPG when no local match found",
            "match_type": "network_fallback",
            "priority": 100,
        },
    ]

    for rule_data in default_rules:
        rule = EpgMatchRule(
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
        db.session.add(rule)

    db.session.commit()
    cache_service.clear_all()

    return jsonify(
        {
            "success": True,
            "id": ruleset.id,
            "name": ruleset.name,
            "rule_count": len(default_rules),
            "message": f"Created default EPG match ruleset with {len(default_rules)} rules",
        }
    )


@epg_match_rules_bp.route("/api/epg-match-rules/create-default-exclusions", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating default exclusion patterns")
def create_default_exclusion_patterns():
    """Create default exclusion patterns for PPV and event channels"""

    patterns_created = 0
    patterns_skipped = 0

    # Default exclusion patterns
    default_patterns = [
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

    for pattern_data in default_patterns:
        # Check if pattern with same name exists
        existing = EpgExclusionPattern.query.filter_by(name=pattern_data["name"]).first()
        if existing:
            patterns_skipped += 1
            continue

        pattern = EpgExclusionPattern(
            name=pattern_data["name"],
            description=pattern_data.get("description", ""),
            pattern_type=pattern_data["pattern_type"],
            pattern=pattern_data["pattern"],
            is_regex=pattern_data.get("is_regex", True),
            hide_channel=pattern_data.get("hide_channel", False),
            enabled=True,
            priority=pattern_data.get("priority", 100),
        )
        db.session.add(pattern)
        patterns_created += 1

    db.session.commit()
    cache_service.clear_all()

    return jsonify(
        {
            "success": True,
            "patterns_created": patterns_created,
            "patterns_skipped": patterns_skipped,
            "message": f"Created {patterns_created} exclusion patterns, skipped {patterns_skipped} existing",
        }
    )


# ============================================================================
# API Routes - Match Type Info
# ============================================================================


@epg_match_rules_bp.route("/api/epg-match-rules/match-types", methods=["GET"])
def get_match_types():
    """Get available match types with descriptions"""
    return jsonify(
        {
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
    )
