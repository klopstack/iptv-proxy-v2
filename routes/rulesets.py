"""
Ruleset and tag rule management routes
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import AccountRuleSet, RuleSet, TagRule, db
from schemas import (
    RuleSetCreateSchema,
    RuleSetUpdateSchema,
    TagRuleCreateSchema,
    TagRuleUpdateSchema,
    validate_request_data,
)
from services.cache_service import CacheService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Create blueprint
rulesets_bp = Blueprint("rulesets", __name__)

# Initialize cache service
cache_service = CacheService()


# ============================================================================
# API Routes - Ruleset CRUD
# ============================================================================


@rulesets_bp.route("/api/rulesets", methods=["GET"])
def get_rulesets():
    """Get all rulesets"""
    rulesets = RuleSet.query.all()
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
            }
            for rs in rulesets
        ]
    )


@rulesets_bp.route("/api/rulesets", methods=["POST"])
@validate_request_data(RuleSetCreateSchema)
def create_ruleset():
    """Create new ruleset"""
    data = request.validated_data

    ruleset = RuleSet(
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
                "rule_count": len(ruleset.rules),
            }
        ),
        201,
    )


@rulesets_bp.route("/api/rulesets/<int:ruleset_id>", methods=["GET"])
def get_ruleset(ruleset_id):
    """Get specific ruleset with its rules"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)

    return jsonify(
        {
            "id": ruleset.id,
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rules": [
                {
                    "id": r.id,
                    "name": r.name,
                    "pattern": r.pattern,
                    "pattern_type": r.pattern_type,
                    "tag_name": r.tag_name,
                    "source": r.source,
                    "remove_from_name": r.remove_from_name,
                    "replacement": r.replacement,
                    "priority": r.priority,
                    "enabled": r.enabled,
                }
                for r in sorted(ruleset.rules, key=lambda x: (x.priority, x.id))
            ],
        }
    )


@rulesets_bp.route("/api/rulesets/<int:ruleset_id>", methods=["PUT"])
@validate_request_data(RuleSetUpdateSchema)
def update_ruleset(ruleset_id):
    """Update ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)
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


@rulesets_bp.route("/api/rulesets/<int:ruleset_id>", methods=["DELETE"])
def delete_ruleset(ruleset_id):
    """Delete ruleset"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)

    # Remove associations with accounts
    AccountRuleSet.query.filter_by(ruleset_id=ruleset_id).delete()

    db.session.delete(ruleset)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


@rulesets_bp.route("/api/rulesets/create-default", methods=["POST"])
def create_default_ruleset():
    """Create default ruleset with common IPTV tag extraction rules"""
    try:
        ruleset = TagService.create_default_ruleset(db.session)
        cache_service.clear_all()

        return jsonify(
            {
                "success": True,
                "id": ruleset.id,
                "name": ruleset.name,
                "rule_count": len(ruleset.rules),
                "message": f"Created default ruleset with {len(ruleset.rules)} rules",
            }
        )
    except Exception as e:
        logger.error(f"Error creating default ruleset: {e}")
        return jsonify({"success": False, "error": str(e)}), 400


@rulesets_bp.route("/api/rulesets/<int:ruleset_id>/rules", methods=["GET"])
def get_ruleset_rules(ruleset_id):
    """Get all rules for a specific ruleset"""
    RuleSet.query.get_or_404(ruleset_id)  # Validate ruleset exists
    rules = TagRule.query.filter_by(ruleset_id=ruleset_id).order_by(TagRule.priority, TagRule.id).all()

    return jsonify(
        [
            {
                "id": r.id,
                "name": r.name,
                "pattern": r.pattern,
                "pattern_type": r.pattern_type,
                "tag_name": r.tag_name,
                "source": r.source,
                "remove_from_name": r.remove_from_name,
                "replacement": r.replacement,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    )


# ============================================================================
# API Routes - Tag Rules CRUD
# ============================================================================


@rulesets_bp.route("/api/tag-rules", methods=["GET"])
def get_tag_rules():
    """Get all tag extraction rules (optionally filtered by ruleset)"""
    ruleset_id = request.args.get("ruleset_id", type=int)

    query = TagRule.query
    if ruleset_id:
        query = query.filter_by(ruleset_id=ruleset_id)

    rules = query.order_by(TagRule.priority, TagRule.id).all()
    return jsonify(
        [
            {
                "id": r.id,
                "ruleset_id": r.ruleset_id,
                "name": r.name,
                "pattern": r.pattern,
                "pattern_type": r.pattern_type,
                "tag_name": r.tag_name,
                "source": r.source,
                "remove_from_name": r.remove_from_name,
                "replacement": r.replacement,
                "priority": r.priority,
                "enabled": r.enabled,
            }
            for r in rules
        ]
    )


@rulesets_bp.route("/api/tag-rules", methods=["POST"])
@validate_request_data(TagRuleCreateSchema)
def create_tag_rule():
    """Create new tag extraction rule"""
    data = request.validated_data

    # Verify ruleset exists (already validated by schema, but check existence)
    ruleset = db.session.get(RuleSet, data["ruleset_id"])
    if not ruleset:
        return jsonify({"error": f"RuleSet {data['ruleset_id']} not found"}), 404

    # Normalize tag_name for consistency (except special tags)
    tag_name = data["tag_name"]
    special_tags = {"__CLEANUP__", "__LOCATION__", "__CALLSIGN__", "__CAPTURE__"}
    if tag_name not in special_tags:
        normalized = TagService.normalize_tag_name(tag_name)
        if normalized:
            tag_name = normalized

    rule = TagRule(
        name=data["name"],
        pattern=data["pattern"],
        pattern_type=data["pattern_type"],
        tag_name=tag_name,
        source=data["source"],
        ruleset_id=data["ruleset_id"],
        remove_from_name=data.get("remove_from_name", True),
        replacement=data.get("replacement"),
        priority=data.get("priority", 100),
        enabled=data.get("enabled", True),
    )

    db.session.add(rule)
    db.session.commit()

    # Clear all account caches since tags affect all channels
    cache_service.clear_all()

    return (
        jsonify(
            {
                "id": rule.id,
                "name": rule.name,
                "pattern": rule.pattern,
                "pattern_type": rule.pattern_type,
                "tag_name": rule.tag_name,
                "source": rule.source,
                "remove_from_name": rule.remove_from_name,
                "replacement": rule.replacement,
                "priority": rule.priority,
                "enabled": rule.enabled,
            }
        ),
        201,
    )


@rulesets_bp.route("/api/tag-rules/<int:rule_id>", methods=["PUT"])
@validate_request_data(TagRuleUpdateSchema)
def update_tag_rule(rule_id):
    """Update tag extraction rule"""
    rule = TagRule.query.get_or_404(rule_id)
    data = request.validated_data

    # Normalize tag_name if provided (except special tags)
    if "tag_name" in data:
        tag_name = data["tag_name"]
        special_tags = {"__CLEANUP__", "__LOCATION__", "__CALLSIGN__", "__CAPTURE__"}
        if tag_name not in special_tags:
            normalized = TagService.normalize_tag_name(tag_name)
            if normalized:
                tag_name = normalized
        rule.tag_name = tag_name

    rule.name = data.get("name", rule.name)
    rule.pattern = data.get("pattern", rule.pattern)
    rule.pattern_type = data.get("pattern_type", rule.pattern_type)
    rule.source = data.get("source", rule.source)
    rule.remove_from_name = data.get("remove_from_name", rule.remove_from_name)
    if "replacement" in data:
        rule.replacement = data["replacement"]
    rule.priority = data.get("priority", rule.priority)
    rule.enabled = data.get("enabled", rule.enabled)

    db.session.commit()
    cache_service.clear_all()

    return jsonify(
        {
            "id": rule.id,
            "name": rule.name,
            "pattern": rule.pattern,
            "pattern_type": rule.pattern_type,
            "tag_name": rule.tag_name,
            "source": rule.source,
            "remove_from_name": rule.remove_from_name,
            "replacement": rule.replacement,
            "priority": rule.priority,
            "enabled": rule.enabled,
        }
    )


@rulesets_bp.route("/api/tag-rules/<int:rule_id>", methods=["DELETE"])
def delete_tag_rule(rule_id):
    """Delete tag extraction rule"""
    rule = TagRule.query.get_or_404(rule_id)

    db.session.delete(rule)
    db.session.commit()
    cache_service.clear_all()

    return "", 204


@rulesets_bp.route("/api/tag-rules/create-defaults", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating default ruleset")
def create_default_tag_rules():
    """Create default tag extraction ruleset"""
    ruleset = TagService.create_default_ruleset(db.session)
    cache_service.clear_all()

    return jsonify(
        {
            "success": True,
            "ruleset_id": ruleset.id,
            "ruleset_name": ruleset.name,
            "count": len(ruleset.rules),
            "message": f"Created default ruleset with {len(ruleset.rules)} rules",
        }
    )


# ============================================================================
# API Routes - Ruleset Export/Import
# ============================================================================


@rulesets_bp.route("/api/rulesets/<int:ruleset_id>/export", methods=["GET"])
def export_ruleset(ruleset_id):
    """Export a ruleset with all its rules as JSON for backup or sharing"""
    ruleset = RuleSet.query.get_or_404(ruleset_id)

    export_data = {
        "version": "1.0",
        "type": "iptv-proxy-ruleset",
        "ruleset": {
            "name": ruleset.name,
            "description": ruleset.description,
            "is_default": ruleset.is_default,
            "enabled": ruleset.enabled,
            "priority": ruleset.priority,
            "rules": [
                {
                    "name": r.name,
                    "pattern": r.pattern,
                    "pattern_type": r.pattern_type,
                    "tag_name": r.tag_name,
                    "source": r.source,
                    "remove_from_name": r.remove_from_name,
                    "replacement": r.replacement,
                    "priority": r.priority,
                    "enabled": r.enabled,
                }
                for r in sorted(ruleset.rules, key=lambda x: (x.priority, x.id))
            ],
        },
    }

    response = jsonify(export_data)
    response.headers["Content-Disposition"] = f'attachment; filename="{ruleset.name.replace(" ", "_")}_ruleset.json"'
    return response


@rulesets_bp.route("/api/rulesets/import", methods=["POST"])
@handle_errors(return_json=True, default_message="Error importing ruleset")
def import_ruleset():
    """Import a ruleset from JSON export data

    Request body should contain the exported JSON structure.
    Optionally include 'rename' field to use a different name.
    """
    data = request.json

    if not data:
        return jsonify({"error": "No JSON data provided"}), 400

    # Validate structure
    if data.get("type") != "iptv-proxy-ruleset":
        return jsonify({"error": "Invalid export format: missing or invalid 'type' field"}), 400

    ruleset_data = data.get("ruleset")
    if not ruleset_data:
        return jsonify({"error": "Invalid export format: missing 'ruleset' field"}), 400

    # Use provided rename or original name
    name = data.get("rename") or ruleset_data.get("name")
    if not name:
        return jsonify({"error": "Ruleset name is required"}), 400

    # Check if name already exists
    existing = RuleSet.query.filter_by(name=name).first()
    if existing:
        return (
            jsonify(
                {"error": f"Ruleset with name '{name}' already exists. Use 'rename' field to specify a different name."}
            ),
            409,
        )

    # Create the ruleset
    ruleset = RuleSet(
        name=name,
        description=ruleset_data.get("description", ""),
        is_default=ruleset_data.get("is_default", False),
        enabled=ruleset_data.get("enabled", True),
        priority=ruleset_data.get("priority", 100),
    )
    db.session.add(ruleset)
    db.session.flush()  # Get the ID

    # Create the rules
    rules_data = ruleset_data.get("rules", [])
    rules_created = 0
    for rule_data in rules_data:
        # Validate required fields
        required_fields = ["name", "pattern", "pattern_type", "tag_name", "source"]
        missing = [f for f in required_fields if not rule_data.get(f)]
        if missing:
            logger.warning(f"Skipping rule with missing fields: {missing}")
            continue

        # Validate pattern_type
        if rule_data["pattern_type"] not in ["prefix", "suffix", "contains", "regex"]:
            logger.warning(f"Skipping rule with invalid pattern_type: {rule_data['pattern_type']}")
            continue

        # Validate source
        if rule_data["source"] not in ["channel_name", "category_name", "both"]:
            logger.warning(f"Skipping rule with invalid source: {rule_data['source']}")
            continue

        rule = TagRule(
            ruleset_id=ruleset.id,
            name=rule_data["name"],
            pattern=rule_data["pattern"],
            pattern_type=rule_data["pattern_type"],
            tag_name=rule_data["tag_name"],
            source=rule_data["source"],
            remove_from_name=rule_data.get("remove_from_name", True),
            replacement=rule_data.get("replacement"),
            priority=rule_data.get("priority", 100),
            enabled=rule_data.get("enabled", True),
        )
        db.session.add(rule)
        rules_created += 1

    db.session.commit()
    cache_service.clear_all()

    return (
        jsonify(
            {
                "success": True,
                "id": ruleset.id,
                "name": ruleset.name,
                "rules_imported": rules_created,
                "rules_skipped": len(rules_data) - rules_created,
                "message": f"Successfully imported ruleset '{ruleset.name}' with {rules_created} rules",
            }
        ),
        201,
    )
