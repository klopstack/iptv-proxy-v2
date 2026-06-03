"""
EPG Match Rules management routes

Provides API endpoints for managing EPG matching rulesets, rules, and exclusion patterns.
Similar to the tag rulesets system but for EPG channel matching configuration.
"""
import logging

from flask import Blueprint, jsonify, request

from error_handling import handle_errors
from models import EpgChannelNameMapping, EpgExclusionPattern, EpgMatchRule, EpgMatchRuleSet
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
from services.epg.match_rules.route_service import EpgMatchRulesRouteService
from services.serializers.epg_match import (
    serialize_epg_channel_name_mapping,
    serialize_epg_exclusion_pattern,
    serialize_epg_match_rule,
)

logger = logging.getLogger(__name__)

epg_match_rules_bp = Blueprint("epg_match_rules", __name__, url_prefix="/api/epg-match-rules")
account_epg_match_rules_bp = Blueprint("account_epg_match_rules", __name__)


# ============================================================================
# API Routes - EPG Match Rulesets
# ============================================================================


@epg_match_rules_bp.route("/rulesets", methods=["GET"])
def get_epg_match_rulesets():
    """Get all EPG match rulesets with assigned accounts"""
    return jsonify(EpgMatchRulesRouteService.list_rulesets())


@epg_match_rules_bp.route("/rulesets", methods=["POST"])
@validate_request_data(EpgMatchRuleSetCreateSchema)
def create_epg_match_ruleset():
    """Create a new EPG match ruleset"""
    payload, error, status = EpgMatchRulesRouteService.create_ruleset(request.validated_data)
    if error:
        return jsonify({"error": error}), status
    return jsonify(payload), status


@epg_match_rules_bp.route("/rulesets/<int:ruleset_id>", methods=["GET"])
def get_epg_match_ruleset(ruleset_id):
    """Get a specific EPG match ruleset with its rules"""
    ruleset = EpgMatchRuleSet.query.get_or_404(ruleset_id)
    return jsonify(EpgMatchRulesRouteService.get_ruleset_detail(ruleset))


@epg_match_rules_bp.route("/rulesets/<int:ruleset_id>", methods=["PUT"])
@validate_request_data(EpgMatchRuleSetUpdateSchema)
def update_epg_match_ruleset(ruleset_id):
    """Update an EPG match ruleset"""
    ruleset = EpgMatchRuleSet.query.get_or_404(ruleset_id)
    return jsonify(EpgMatchRulesRouteService.update_ruleset(ruleset, request.validated_data))


@epg_match_rules_bp.route("/rulesets/<int:ruleset_id>", methods=["DELETE"])
def delete_epg_match_ruleset(ruleset_id):
    """Delete an EPG match ruleset"""
    EpgMatchRulesRouteService.delete_ruleset(ruleset_id)
    return "", 204


@epg_match_rules_bp.route("/rulesets/<int:ruleset_id>/duplicate", methods=["POST"])
def duplicate_epg_match_ruleset(ruleset_id):
    """Duplicate an EPG match ruleset with all its rules"""
    payload, status = EpgMatchRulesRouteService.duplicate_ruleset(ruleset_id)
    return jsonify(payload), status


# ============================================================================
# API Routes - EPG Match Rules
# ============================================================================


@epg_match_rules_bp.route("/rules", methods=["GET"])
def get_epg_match_rules():
    """Get all EPG match rules, optionally filtered by ruleset"""
    ruleset_id = request.args.get("ruleset_id", type=int)
    return jsonify(EpgMatchRulesRouteService.list_rules(ruleset_id))


@epg_match_rules_bp.route("/rules", methods=["POST"])
@validate_request_data(EpgMatchRuleCreateSchema)
def create_epg_match_rule():
    """Create a new EPG match rule"""
    return jsonify(EpgMatchRulesRouteService.create_rule(request.validated_data)), 201


@epg_match_rules_bp.route("/rules/<int:rule_id>", methods=["GET"])
def get_epg_match_rule(rule_id):
    """Get a specific EPG match rule"""
    rule = EpgMatchRule.query.get_or_404(rule_id)
    return jsonify(serialize_epg_match_rule(rule))


@epg_match_rules_bp.route("/rules/<int:rule_id>", methods=["PUT"])
@validate_request_data(EpgMatchRuleUpdateSchema)
def update_epg_match_rule(rule_id):
    """Update an EPG match rule"""
    rule = EpgMatchRule.query.get_or_404(rule_id)
    return jsonify(EpgMatchRulesRouteService.update_rule(rule, request.validated_data))


@epg_match_rules_bp.route("/rules/<int:rule_id>", methods=["DELETE"])
def delete_epg_match_rule(rule_id):
    """Delete an EPG match rule"""
    EpgMatchRulesRouteService.delete_rule(EpgMatchRule.query.get_or_404(rule_id))
    return "", 204


# ============================================================================
# API Routes - EPG Exclusion Patterns
# ============================================================================


@epg_match_rules_bp.route("/exclusions", methods=["GET"])
def get_epg_exclusion_patterns():
    """Get all EPG exclusion patterns"""
    return jsonify(EpgMatchRulesRouteService.list_exclusion_patterns())


@epg_match_rules_bp.route("/exclusions", methods=["POST"])
@validate_request_data(EpgExclusionPatternCreateSchema)
def create_epg_exclusion_pattern():
    """Create a new EPG exclusion pattern"""
    return jsonify(EpgMatchRulesRouteService.create_exclusion_pattern(request.validated_data)), 201


@epg_match_rules_bp.route("/exclusions/<int:pattern_id>", methods=["GET"])
def get_epg_exclusion_pattern(pattern_id):
    """Get a specific EPG exclusion pattern"""
    pattern = EpgExclusionPattern.query.get_or_404(pattern_id)
    return jsonify(serialize_epg_exclusion_pattern(pattern))


@epg_match_rules_bp.route("/exclusions/<int:pattern_id>", methods=["PUT"])
@validate_request_data(EpgExclusionPatternUpdateSchema)
def update_epg_exclusion_pattern(pattern_id):
    """Update an EPG exclusion pattern"""
    pattern = EpgExclusionPattern.query.get_or_404(pattern_id)
    return jsonify(EpgMatchRulesRouteService.update_exclusion_pattern(pattern, request.validated_data))


@epg_match_rules_bp.route("/exclusions/<int:pattern_id>", methods=["DELETE"])
def delete_epg_exclusion_pattern(pattern_id):
    """Delete an EPG exclusion pattern"""
    EpgMatchRulesRouteService.delete_exclusion_pattern(EpgExclusionPattern.query.get_or_404(pattern_id))
    return "", 204


# ============================================================================
# API Routes - EPG Channel Name Mappings
# ============================================================================


@epg_match_rules_bp.route("/name-mappings", methods=["GET"])
def get_epg_channel_name_mappings():
    """Get all EPG channel name mappings"""
    return jsonify(EpgMatchRulesRouteService.list_name_mappings())


@epg_match_rules_bp.route("/name-mappings", methods=["POST"])
@validate_request_data(EpgChannelNameMappingCreateSchema)
def create_epg_channel_name_mapping():
    """Create a new EPG channel name mapping"""
    return jsonify(EpgMatchRulesRouteService.create_name_mapping(request.validated_data)), 201


@epg_match_rules_bp.route("/name-mappings/<int:mapping_id>", methods=["GET"])
def get_epg_channel_name_mapping(mapping_id):
    """Get a specific EPG channel name mapping"""
    mapping = EpgChannelNameMapping.query.get_or_404(mapping_id)
    return jsonify(serialize_epg_channel_name_mapping(mapping))


@epg_match_rules_bp.route("/name-mappings/<int:mapping_id>", methods=["PUT"])
@validate_request_data(EpgChannelNameMappingUpdateSchema)
def update_epg_channel_name_mapping(mapping_id):
    """Update an EPG channel name mapping"""
    mapping = EpgChannelNameMapping.query.get_or_404(mapping_id)
    return jsonify(EpgMatchRulesRouteService.update_name_mapping(mapping, request.validated_data))


@epg_match_rules_bp.route("/name-mappings/<int:mapping_id>", methods=["DELETE"])
def delete_epg_channel_name_mapping(mapping_id):
    """Delete an EPG channel name mapping"""
    EpgMatchRulesRouteService.delete_name_mapping(EpgChannelNameMapping.query.get_or_404(mapping_id))
    return "", 204


@epg_match_rules_bp.route("/name-mappings/preview", methods=["POST"])
def preview_channel_name_mapping():
    """Preview how a channel name mapping would transform channel names."""
    payload, status = EpgMatchRulesRouteService.preview_channel_name_mapping(request.get_json() or {})
    return jsonify(payload), status


# ============================================================================
# API Routes - Preview/Test Patterns
# ============================================================================


@epg_match_rules_bp.route("/exclusions/preview", methods=["POST"])
def preview_exclusion_pattern():
    """Preview which channels would match an exclusion pattern."""
    return jsonify(EpgMatchRulesRouteService.preview_exclusion_pattern(request.get_json() or {}))


@epg_match_rules_bp.route("/rules/preview", methods=["POST"])
def preview_rule_pattern():
    """Preview which channels would match a rule's pattern."""
    return jsonify(EpgMatchRulesRouteService.preview_rule_pattern(request.get_json() or {}))


# ============================================================================
# API Routes - Account Ruleset Assignments
# ============================================================================


@account_epg_match_rules_bp.route("/api/accounts/<int:account_id>/epg-match-rulesets", methods=["GET"])
def get_account_epg_match_rulesets(account_id):
    """Get EPG match rulesets assigned to an account"""
    return jsonify(EpgMatchRulesRouteService.list_account_rulesets(account_id))


@account_epg_match_rules_bp.route("/api/accounts/<int:account_id>/epg-match-rulesets", methods=["POST"])
@validate_request_data(AccountEpgMatchRuleSetAssignSchema)
def assign_epg_match_ruleset_to_account(account_id):
    """Assign an EPG match ruleset to an account"""
    return jsonify(EpgMatchRulesRouteService.assign_ruleset_to_account(account_id, request.validated_data)), 201


@account_epg_match_rules_bp.route(
    "/api/accounts/<int:account_id>/epg-match-rulesets/<int:ruleset_id>", methods=["DELETE"]
)
def unassign_epg_match_ruleset_from_account(account_id, ruleset_id):
    """Remove an EPG match ruleset assignment from an account"""
    EpgMatchRulesRouteService.unassign_ruleset_from_account(account_id, ruleset_id)
    return "", 204


# ============================================================================
# API Routes - Default Ruleset Creation
# ============================================================================


@epg_match_rules_bp.route("/create-default", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating default EPG match ruleset")
def create_default_epg_match_ruleset():
    """Create a default EPG match ruleset with common matching rules"""
    payload, status = EpgMatchRulesRouteService.create_default_epg_match_ruleset()
    return jsonify(payload), status


@epg_match_rules_bp.route("/create-default-exclusions", methods=["POST"])
@handle_errors(return_json=True, default_message="Error creating default exclusion patterns")
def create_default_exclusion_patterns():
    """Create default exclusion patterns for PPV and event channels"""
    return jsonify(EpgMatchRulesRouteService.create_default_exclusion_patterns())


# ============================================================================
# API Routes - Match Type Info
# ============================================================================


@epg_match_rules_bp.route("/match-types", methods=["GET"])
def get_match_types():
    """Get available match types with descriptions"""
    return jsonify(EpgMatchRulesRouteService.get_match_types())
