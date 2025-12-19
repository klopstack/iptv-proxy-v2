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

    rule = TagRule(
        name=data["name"],
        pattern=data["pattern"],
        pattern_type=data["pattern_type"],
        tag_name=data["tag_name"],
        source=data["source"],
        ruleset_id=data["ruleset_id"],
        remove_from_name=data.get("remove_from_name", True),
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

    rule.name = data.get("name", rule.name)
    rule.pattern = data.get("pattern", rule.pattern)
    rule.pattern_type = data.get("pattern_type", rule.pattern_type)
    rule.tag_name = data.get("tag_name", rule.tag_name)
    rule.source = data.get("source", rule.source)
    rule.remove_from_name = data.get("remove_from_name", rule.remove_from_name)
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
