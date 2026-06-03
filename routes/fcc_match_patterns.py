"""
FCC Match Patterns management routes

Provides API endpoints for managing FCC matching patterns including:
- Network patterns (ABC, NBC, CBS, etc.)
- Channel number extraction patterns
- Location tag parsing patterns
- Match strategies
- Country/EPG suffix mappings
- Quality tags
- Country tags
- Callsign suffixes
"""

from flask import Blueprint, jsonify, render_template, request

from routes.crud_helpers import register_json_crud_routes
from services.fcc_match_patterns_service import FccMatchPatternsService

fcc_match_patterns_bp = Blueprint("fcc_match_patterns", __name__)
_service = FccMatchPatternsService


@fcc_match_patterns_bp.route("/fcc-match-patterns")
def fcc_match_patterns():
    """Render the FCC match patterns management page"""
    return render_template("fcc_match_patterns.html")


@fcc_match_patterns_bp.route("/configurable-patterns")
def configurable_patterns():
    """Render the configurable patterns management page"""
    return render_template("configurable_patterns.html")


register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/networks",
    id_param="network_id",
    list_fn=_service.list_networks,
    get_fn=_service.get_network,
    create_fn=_service.create_network,
    update_fn=_service.update_network,
    delete_fn=_service.delete_network,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/channel-patterns",
    id_param="pattern_id",
    list_fn=_service.list_channel_patterns,
    get_fn=_service.get_channel_pattern,
    create_fn=_service.create_channel_pattern,
    update_fn=_service.update_channel_pattern,
    delete_fn=_service.delete_channel_pattern,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/location-patterns",
    id_param="pattern_id",
    list_fn=_service.list_location_patterns,
    get_fn=_service.get_location_pattern,
    create_fn=_service.create_location_pattern,
    update_fn=_service.update_location_pattern,
    delete_fn=_service.delete_location_pattern,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/strategies",
    id_param="strategy_id",
    list_fn=_service.list_strategies,
    get_fn=_service.get_strategy,
    create_fn=_service.create_strategy,
    update_fn=_service.update_strategy,
    delete_fn=_service.delete_strategy,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/country-suffixes",
    id_param="suffix_id",
    list_fn=_service.list_country_suffixes,
    get_fn=_service.get_country_suffix,
    create_fn=_service.create_country_suffix,
    update_fn=_service.update_country_suffix,
    delete_fn=_service.delete_country_suffix,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/quality-tags",
    id_param="tag_id",
    list_fn=_service.list_quality_tags,
    get_fn=_service.get_quality_tag,
    create_fn=_service.create_quality_tag,
    update_fn=_service.update_quality_tag,
    delete_fn=_service.delete_quality_tag,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/country-tags",
    id_param="tag_id",
    list_fn=_service.list_country_tags,
    get_fn=_service.get_country_tag,
    create_fn=_service.create_country_tag,
    update_fn=_service.update_country_tag,
    delete_fn=_service.delete_country_tag,
)

register_json_crud_routes(
    fcc_match_patterns_bp,
    base_path="/api/fcc-match-patterns/callsign-suffixes",
    id_param="suffix_id",
    list_fn=_service.list_callsign_suffixes,
    get_fn=_service.get_callsign_suffix,
    create_fn=_service.create_callsign_suffix,
    update_fn=_service.update_callsign_suffix,
    delete_fn=_service.delete_callsign_suffix,
)


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/test", methods=["POST"])
def test_fcc_patterns():
    """Test FCC matching patterns against sample channel data"""
    return jsonify(_service.test_patterns(request.get_json() or {}))
