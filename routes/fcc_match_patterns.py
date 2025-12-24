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
import json
import logging

from flask import Blueprint, jsonify, render_template, request

from models import (
    CallsignSuffix,
    CountryTag,
    EpgCountrySuffix,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    QualityTag,
    db,
)
from services.cache_service import CacheService
from services.epg_match_rules_service import clear_fcc_pattern_cache

logger = logging.getLogger(__name__)

# Create blueprint
fcc_match_patterns_bp = Blueprint("fcc_match_patterns", __name__)

# Initialize cache service
cache_service = CacheService()


# ============================================================================
# Web UI Routes
# ============================================================================


@fcc_match_patterns_bp.route("/fcc-match-patterns")
def fcc_match_patterns():
    """Render the FCC match patterns management page"""
    return render_template("fcc_match_patterns.html")


@fcc_match_patterns_bp.route("/configurable-patterns")
def configurable_patterns():
    """Render the configurable patterns management page"""
    return render_template("configurable_patterns.html")


# ============================================================================
# Helper Functions
# ============================================================================


def _clear_pattern_cache():
    """Clear FCC pattern caches after modifications"""
    clear_fcc_pattern_cache()


def _serialize_network(network: FccMatchNetwork) -> dict:
    """Serialize a network pattern to JSON-compatible dict"""
    return {
        "id": network.id,
        "name": network.name,
        "display_name": network.display_name,
        "description": network.description,
        "fcc_affiliation_pattern": network.fcc_affiliation_pattern,
        "tag_patterns": json.loads(network.tag_patterns) if network.tag_patterns else [],
        "enabled": network.enabled,
        "priority": network.priority,
    }


def _serialize_channel_pattern(pattern: FccMatchChannelPattern) -> dict:
    """Serialize a channel number pattern to JSON-compatible dict"""
    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "pattern": pattern.pattern,
        "pattern_type": pattern.pattern_type,
        "capture_group": pattern.capture_group,
        "networks": json.loads(pattern.networks) if pattern.networks else None,
        "enabled": pattern.enabled,
        "priority": pattern.priority,
    }


def _serialize_location_pattern(pattern: FccMatchLocationPattern) -> dict:
    """Serialize a location pattern to JSON-compatible dict"""
    return {
        "id": pattern.id,
        "name": pattern.name,
        "description": pattern.description,
        "pattern": pattern.pattern,
        "pattern_type": pattern.pattern_type,
        "extract_city": pattern.extract_city,
        "extract_state": pattern.extract_state,
        "city_group": pattern.city_group,
        "state_group": pattern.state_group,
        "enabled": pattern.enabled,
        "priority": pattern.priority,
    }


def _serialize_strategy(strategy: FccMatchStrategy) -> dict:
    """Serialize a match strategy to JSON-compatible dict"""
    return {
        "id": strategy.id,
        "name": strategy.name,
        "description": strategy.description,
        "strategy_type": strategy.strategy_type,
        "require_network": strategy.require_network,
        "require_channel_number": strategy.require_channel_number,
        "require_state": strategy.require_state,
        "require_city": strategy.require_city,
        "match_nielsen_dma": strategy.match_nielsen_dma,
        "match_community_city": strategy.match_community_city,
        "match_community_state": strategy.match_community_state,
        "enabled": strategy.enabled,
        "priority": strategy.priority,
    }


# ============================================================================
# API Routes - Networks
# ============================================================================


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/networks", methods=["GET"])
def get_networks():
    """Get all network patterns"""
    networks = FccMatchNetwork.query.order_by(FccMatchNetwork.priority, FccMatchNetwork.name).all()
    return jsonify([_serialize_network(n) for n in networks])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/networks", methods=["POST"])
def create_network():
    """Create a new network pattern"""
    data = request.get_json()

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("fcc_affiliation_pattern"):
        return jsonify({"error": "FCC affiliation pattern is required"}), 400

    # Check for duplicate
    existing = FccMatchNetwork.query.filter_by(name=data["name"]).first()
    if existing:
        return jsonify({"error": f"Network '{data['name']}' already exists"}), 409

    network = FccMatchNetwork(
        name=data["name"],
        display_name=data.get("display_name"),
        description=data.get("description"),
        fcc_affiliation_pattern=data["fcc_affiliation_pattern"],
        tag_patterns=json.dumps(data.get("tag_patterns", [])) if data.get("tag_patterns") else None,
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(network)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_network(network)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/networks/<int:network_id>", methods=["GET"])
def get_network(network_id):
    """Get a specific network pattern"""
    network = FccMatchNetwork.query.get_or_404(network_id)
    return jsonify(_serialize_network(network))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/networks/<int:network_id>", methods=["PUT"])
def update_network(network_id):
    """Update a network pattern"""
    network = FccMatchNetwork.query.get_or_404(network_id)
    data = request.get_json()

    network.name = data.get("name", network.name)
    network.display_name = data.get("display_name", network.display_name)
    network.description = data.get("description", network.description)
    network.fcc_affiliation_pattern = data.get("fcc_affiliation_pattern", network.fcc_affiliation_pattern)
    if "tag_patterns" in data:
        network.tag_patterns = json.dumps(data["tag_patterns"]) if data["tag_patterns"] else None
    network.enabled = data.get("enabled", network.enabled)
    network.priority = data.get("priority", network.priority)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_network(network))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/networks/<int:network_id>", methods=["DELETE"])
def delete_network(network_id):
    """Delete a network pattern"""
    network = FccMatchNetwork.query.get_or_404(network_id)
    db.session.delete(network)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Channel Patterns
# ============================================================================


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/channel-patterns", methods=["GET"])
def get_channel_patterns():
    """Get all channel number extraction patterns"""
    patterns = FccMatchChannelPattern.query.order_by(FccMatchChannelPattern.priority, FccMatchChannelPattern.name).all()
    return jsonify([_serialize_channel_pattern(p) for p in patterns])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/channel-patterns", methods=["POST"])
def create_channel_pattern():
    """Create a new channel number extraction pattern"""
    data = request.get_json()

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("pattern"):
        return jsonify({"error": "Pattern is required"}), 400

    pattern = FccMatchChannelPattern(
        name=data["name"],
        description=data.get("description"),
        pattern=data["pattern"],
        pattern_type=data.get("pattern_type", "regex"),
        capture_group=data.get("capture_group", 1),
        networks=json.dumps(data.get("networks")) if data.get("networks") else None,
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(pattern)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_channel_pattern(pattern)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/channel-patterns/<int:pattern_id>", methods=["GET"])
def get_channel_pattern(pattern_id):
    """Get a specific channel number extraction pattern"""
    pattern = FccMatchChannelPattern.query.get_or_404(pattern_id)
    return jsonify(_serialize_channel_pattern(pattern))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/channel-patterns/<int:pattern_id>", methods=["PUT"])
def update_channel_pattern(pattern_id):
    """Update a channel number extraction pattern"""
    pattern = FccMatchChannelPattern.query.get_or_404(pattern_id)
    data = request.get_json()

    pattern.name = data.get("name", pattern.name)
    pattern.description = data.get("description", pattern.description)
    pattern.pattern = data.get("pattern", pattern.pattern)
    pattern.pattern_type = data.get("pattern_type", pattern.pattern_type)
    pattern.capture_group = data.get("capture_group", pattern.capture_group)
    if "networks" in data:
        pattern.networks = json.dumps(data["networks"]) if data["networks"] else None
    pattern.enabled = data.get("enabled", pattern.enabled)
    pattern.priority = data.get("priority", pattern.priority)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_channel_pattern(pattern))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/channel-patterns/<int:pattern_id>", methods=["DELETE"])
def delete_channel_pattern(pattern_id):
    """Delete a channel number extraction pattern"""
    pattern = FccMatchChannelPattern.query.get_or_404(pattern_id)
    db.session.delete(pattern)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Location Patterns
# ============================================================================


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/location-patterns", methods=["GET"])
def get_location_patterns():
    """Get all location parsing patterns"""
    patterns = FccMatchLocationPattern.query.order_by(
        FccMatchLocationPattern.priority, FccMatchLocationPattern.name
    ).all()
    return jsonify([_serialize_location_pattern(p) for p in patterns])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/location-patterns", methods=["POST"])
def create_location_pattern():
    """Create a new location parsing pattern"""
    data = request.get_json()

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("pattern"):
        return jsonify({"error": "Pattern is required"}), 400

    pattern = FccMatchLocationPattern(
        name=data["name"],
        description=data.get("description"),
        pattern=data["pattern"],
        pattern_type=data.get("pattern_type", "regex"),
        extract_city=data.get("extract_city", True),
        extract_state=data.get("extract_state", True),
        city_group=data.get("city_group", 1),
        state_group=data.get("state_group", 2),
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(pattern)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_location_pattern(pattern)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/location-patterns/<int:pattern_id>", methods=["GET"])
def get_location_pattern(pattern_id):
    """Get a specific location parsing pattern"""
    pattern = FccMatchLocationPattern.query.get_or_404(pattern_id)
    return jsonify(_serialize_location_pattern(pattern))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/location-patterns/<int:pattern_id>", methods=["PUT"])
def update_location_pattern(pattern_id):
    """Update a location parsing pattern"""
    pattern = FccMatchLocationPattern.query.get_or_404(pattern_id)
    data = request.get_json()

    pattern.name = data.get("name", pattern.name)
    pattern.description = data.get("description", pattern.description)
    pattern.pattern = data.get("pattern", pattern.pattern)
    pattern.pattern_type = data.get("pattern_type", pattern.pattern_type)
    pattern.extract_city = data.get("extract_city", pattern.extract_city)
    pattern.extract_state = data.get("extract_state", pattern.extract_state)
    pattern.city_group = data.get("city_group", pattern.city_group)
    pattern.state_group = data.get("state_group", pattern.state_group)
    pattern.enabled = data.get("enabled", pattern.enabled)
    pattern.priority = data.get("priority", pattern.priority)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_location_pattern(pattern))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/location-patterns/<int:pattern_id>", methods=["DELETE"])
def delete_location_pattern(pattern_id):
    """Delete a location parsing pattern"""
    pattern = FccMatchLocationPattern.query.get_or_404(pattern_id)
    db.session.delete(pattern)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Strategies
# ============================================================================


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/strategies", methods=["GET"])
def get_strategies():
    """Get all match strategies"""
    strategies = FccMatchStrategy.query.order_by(FccMatchStrategy.priority, FccMatchStrategy.name).all()
    return jsonify([_serialize_strategy(s) for s in strategies])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/strategies", methods=["POST"])
def create_strategy():
    """Create a new match strategy"""
    data = request.get_json()

    if not data.get("name"):
        return jsonify({"error": "Name is required"}), 400
    if not data.get("strategy_type"):
        return jsonify({"error": "Strategy type is required"}), 400

    strategy = FccMatchStrategy(
        name=data["name"],
        description=data.get("description"),
        strategy_type=data["strategy_type"],
        require_network=data.get("require_network", True),
        require_channel_number=data.get("require_channel_number", False),
        require_state=data.get("require_state", False),
        require_city=data.get("require_city", False),
        match_nielsen_dma=data.get("match_nielsen_dma", True),
        match_community_city=data.get("match_community_city", True),
        match_community_state=data.get("match_community_state", True),
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(strategy)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_strategy(strategy)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/strategies/<int:strategy_id>", methods=["GET"])
def get_strategy(strategy_id):
    """Get a specific match strategy"""
    strategy = FccMatchStrategy.query.get_or_404(strategy_id)
    return jsonify(_serialize_strategy(strategy))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/strategies/<int:strategy_id>", methods=["PUT"])
def update_strategy(strategy_id):
    """Update a match strategy"""
    strategy = FccMatchStrategy.query.get_or_404(strategy_id)
    data = request.get_json()

    strategy.name = data.get("name", strategy.name)
    strategy.description = data.get("description", strategy.description)
    strategy.strategy_type = data.get("strategy_type", strategy.strategy_type)
    strategy.require_network = data.get("require_network", strategy.require_network)
    strategy.require_channel_number = data.get("require_channel_number", strategy.require_channel_number)
    strategy.require_state = data.get("require_state", strategy.require_state)
    strategy.require_city = data.get("require_city", strategy.require_city)
    strategy.match_nielsen_dma = data.get("match_nielsen_dma", strategy.match_nielsen_dma)
    strategy.match_community_city = data.get("match_community_city", strategy.match_community_city)
    strategy.match_community_state = data.get("match_community_state", strategy.match_community_state)
    strategy.enabled = data.get("enabled", strategy.enabled)
    strategy.priority = data.get("priority", strategy.priority)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_strategy(strategy))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/strategies/<int:strategy_id>", methods=["DELETE"])
def delete_strategy(strategy_id):
    """Delete a match strategy"""
    strategy = FccMatchStrategy.query.get_or_404(strategy_id)
    db.session.delete(strategy)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Testing
# ============================================================================


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/test", methods=["POST"])
def test_fcc_patterns():
    """Test FCC matching patterns against sample channel data"""
    data = request.get_json()

    channel_name = data.get("channel_name", "")
    tags = set(data.get("tags", []))

    from services.epg_match_rules_service import EpgMatchRulesService

    # Test channel number extraction
    channel_number = EpgMatchRulesService._extract_channel_number(channel_name)

    # Test location parsing for each tag
    location_results = []
    for tag in tags:
        city, state = EpgMatchRulesService._parse_location_tag(tag)
        if city or state:
            location_results.append({"tag": tag, "city": city, "state": state})

    # Simulate FCC lookup
    class MockChannel:
        def __init__(self, name):
            self.name = name

    mock_channel = MockChannel(channel_name)
    callsign = EpgMatchRulesService._lookup_fcc_callsign(mock_channel, tags)

    return jsonify(
        {
            "channel_name": channel_name,
            "tags": list(tags),
            "extracted_channel_number": channel_number,
            "location_parsing": location_results,
            "fcc_callsign": callsign,
        }
    )


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/reset-defaults", methods=["POST"])
def reset_defaults():
    """Reset all FCC match patterns to defaults (re-run migration)"""
    import importlib.util
    import os
    import sqlite3
    from pathlib import Path

    # Get database path
    db_url = os.environ.get("DATABASE_URL", "sqlite:///iptv_proxy.db")
    if db_url.startswith("sqlite:///"):
        db_path = db_url.replace("sqlite:///", "")
    else:
        return jsonify({"error": "Only SQLite databases supported"}), 400

    try:
        # Delete existing data using SQLAlchemy
        FccMatchNetwork.query.delete()
        FccMatchChannelPattern.query.delete()
        FccMatchLocationPattern.query.delete()
        FccMatchStrategy.query.delete()
        db.session.commit()

        # Drop the tables so migration will recreate them with defaults
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS fcc_match_networks")
        cursor.execute("DROP TABLE IF EXISTS fcc_match_channel_patterns")
        cursor.execute("DROP TABLE IF EXISTS fcc_match_location_patterns")
        cursor.execute("DROP TABLE IF EXISTS fcc_match_strategies")
        conn.commit()
        conn.close()

        # Find and load the FCC match patterns migration
        migration_dir = Path(__file__).parent.parent / "migrations"
        migration_file = None

        for f in sorted(migration_dir.glob("*.py")):
            if "fcc_match_patterns" in f.name and f.name != "__init__.py":
                migration_file = f
                break

        if not migration_file:
            return jsonify({"error": "Migration file not found"}), 404

        # Load and execute the migration module
        spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if not hasattr(module, "migrate"):
            return jsonify({"error": "Migration has no migrate() function"}), 500

        success, message = module.migrate(db_path)

        if success:
            cache_service.clear_all()
            _clear_pattern_cache()
            return jsonify({"message": "Defaults restored successfully"})
        else:
            return jsonify({"error": message}), 500

    except Exception as e:
        logger.error(f"Error resetting defaults: {e}")
        db.session.rollback()
        return jsonify({"error": str(e)}), 500


# ============================================================================
# API Routes - EPG Country Suffixes
# ============================================================================


def _serialize_country_suffix(suffix: EpgCountrySuffix) -> dict:
    """Serialize a country suffix to JSON-compatible dict"""
    return {
        "id": suffix.id,
        "country_code": suffix.country_code,
        "country_name": suffix.country_name,
        "epg_suffixes": json.loads(suffix.epg_suffixes) if suffix.epg_suffixes else [],
        "enabled": suffix.enabled,
        "priority": suffix.priority,
        "created_at": suffix.created_at.isoformat() if suffix.created_at else None,
        "updated_at": suffix.updated_at.isoformat() if suffix.updated_at else None,
    }


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-suffixes", methods=["GET"])
def get_country_suffixes():
    """Get all EPG country suffix mappings"""
    suffixes = EpgCountrySuffix.query.order_by(EpgCountrySuffix.priority, EpgCountrySuffix.country_code).all()
    return jsonify([_serialize_country_suffix(s) for s in suffixes])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-suffixes", methods=["POST"])
def create_country_suffix():
    """Create a new country suffix mapping"""
    data = request.get_json()

    suffix = EpgCountrySuffix(
        country_code=data["country_code"].upper(),
        country_name=data.get("country_name"),
        epg_suffixes=json.dumps(data.get("epg_suffixes", [])),
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(suffix)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_country_suffix(suffix)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-suffixes/<int:suffix_id>", methods=["GET"])
def get_country_suffix(suffix_id):
    """Get a specific country suffix mapping"""
    suffix = EpgCountrySuffix.query.get_or_404(suffix_id)
    return jsonify(_serialize_country_suffix(suffix))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-suffixes/<int:suffix_id>", methods=["PUT"])
def update_country_suffix(suffix_id):
    """Update a country suffix mapping"""
    suffix = EpgCountrySuffix.query.get_or_404(suffix_id)
    data = request.get_json()

    suffix.country_code = data.get("country_code", suffix.country_code).upper()
    suffix.country_name = data.get("country_name", suffix.country_name)
    if "epg_suffixes" in data:
        suffix.epg_suffixes = json.dumps(data["epg_suffixes"])
    suffix.enabled = data.get("enabled", suffix.enabled)
    suffix.priority = data.get("priority", suffix.priority)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_country_suffix(suffix))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-suffixes/<int:suffix_id>", methods=["DELETE"])
def delete_country_suffix(suffix_id):
    """Delete a country suffix mapping"""
    suffix = EpgCountrySuffix.query.get_or_404(suffix_id)
    db.session.delete(suffix)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Quality Tags
# ============================================================================


def _serialize_quality_tag(tag: QualityTag) -> dict:
    """Serialize a quality tag to JSON-compatible dict"""
    return {
        "id": tag.id,
        "tag_name": tag.tag_name,
        "display_name": tag.display_name,
        "category": tag.category,
        "quality_score": tag.quality_score,
        "exclude_from_location": tag.exclude_from_location,
        "enabled": tag.enabled,
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
        "updated_at": tag.updated_at.isoformat() if tag.updated_at else None,
    }


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/quality-tags", methods=["GET"])
def get_quality_tags():
    """Get all quality tags"""
    tags = QualityTag.query.order_by(QualityTag.category, QualityTag.quality_score.desc()).all()
    return jsonify([_serialize_quality_tag(t) for t in tags])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/quality-tags", methods=["POST"])
def create_quality_tag():
    """Create a new quality tag"""
    data = request.get_json()

    tag = QualityTag(
        tag_name=data["tag_name"].upper(),
        display_name=data.get("display_name"),
        category=data.get("category"),
        quality_score=data.get("quality_score", 0),
        exclude_from_location=data.get("exclude_from_location", True),
        enabled=data.get("enabled", True),
    )

    db.session.add(tag)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_quality_tag(tag)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/quality-tags/<int:tag_id>", methods=["GET"])
def get_quality_tag(tag_id):
    """Get a specific quality tag"""
    tag = QualityTag.query.get_or_404(tag_id)
    return jsonify(_serialize_quality_tag(tag))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/quality-tags/<int:tag_id>", methods=["PUT"])
def update_quality_tag(tag_id):
    """Update a quality tag"""
    tag = QualityTag.query.get_or_404(tag_id)
    data = request.get_json()

    tag.tag_name = data.get("tag_name", tag.tag_name).upper()
    tag.display_name = data.get("display_name", tag.display_name)
    tag.category = data.get("category", tag.category)
    tag.quality_score = data.get("quality_score", tag.quality_score)
    tag.exclude_from_location = data.get("exclude_from_location", tag.exclude_from_location)
    tag.enabled = data.get("enabled", tag.enabled)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_quality_tag(tag))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/quality-tags/<int:tag_id>", methods=["DELETE"])
def delete_quality_tag(tag_id):
    """Delete a quality tag"""
    tag = QualityTag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Country Tags
# ============================================================================


def _serialize_country_tag(tag: CountryTag) -> dict:
    """Serialize a country tag to JSON-compatible dict"""
    return {
        "id": tag.id,
        "tag_name": tag.tag_name,
        "country_name": tag.country_name,
        "iso_code": tag.iso_code,
        "exclude_from_location": tag.exclude_from_location,
        "enabled": tag.enabled,
        "created_at": tag.created_at.isoformat() if tag.created_at else None,
        "updated_at": tag.updated_at.isoformat() if tag.updated_at else None,
    }


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-tags", methods=["GET"])
def get_country_tags():
    """Get all country tags"""
    tags = CountryTag.query.order_by(CountryTag.tag_name).all()
    return jsonify([_serialize_country_tag(t) for t in tags])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-tags", methods=["POST"])
def create_country_tag():
    """Create a new country tag"""
    data = request.get_json()

    tag = CountryTag(
        tag_name=data["tag_name"].upper(),
        country_name=data.get("country_name"),
        iso_code=data.get("iso_code"),
        exclude_from_location=data.get("exclude_from_location", True),
        enabled=data.get("enabled", True),
    )

    db.session.add(tag)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_country_tag(tag)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-tags/<int:tag_id>", methods=["GET"])
def get_country_tag(tag_id):
    """Get a specific country tag"""
    tag = CountryTag.query.get_or_404(tag_id)
    return jsonify(_serialize_country_tag(tag))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-tags/<int:tag_id>", methods=["PUT"])
def update_country_tag(tag_id):
    """Update a country tag"""
    tag = CountryTag.query.get_or_404(tag_id)
    data = request.get_json()

    tag.tag_name = data.get("tag_name", tag.tag_name).upper()
    tag.country_name = data.get("country_name", tag.country_name)
    tag.iso_code = data.get("iso_code", tag.iso_code)
    tag.exclude_from_location = data.get("exclude_from_location", tag.exclude_from_location)
    tag.enabled = data.get("enabled", tag.enabled)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_country_tag(tag))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/country-tags/<int:tag_id>", methods=["DELETE"])
def delete_country_tag(tag_id):
    """Delete a country tag"""
    tag = CountryTag.query.get_or_404(tag_id)
    db.session.delete(tag)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204


# ============================================================================
# API Routes - Callsign Suffixes
# ============================================================================


def _serialize_callsign_suffix(suffix: CallsignSuffix) -> dict:
    """Serialize a callsign suffix to JSON-compatible dict"""
    return {
        "id": suffix.id,
        "suffix": suffix.suffix,
        "description": suffix.description,
        "try_on_miss": suffix.try_on_miss,
        "strip_on_normalize": suffix.strip_on_normalize,
        "enabled": suffix.enabled,
        "priority": suffix.priority,
        "created_at": suffix.created_at.isoformat() if suffix.created_at else None,
        "updated_at": suffix.updated_at.isoformat() if suffix.updated_at else None,
    }


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/callsign-suffixes", methods=["GET"])
def get_callsign_suffixes():
    """Get all callsign suffixes"""
    suffixes = CallsignSuffix.query.order_by(CallsignSuffix.priority, CallsignSuffix.suffix).all()
    return jsonify([_serialize_callsign_suffix(s) for s in suffixes])


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/callsign-suffixes", methods=["POST"])
def create_callsign_suffix():
    """Create a new callsign suffix"""
    data = request.get_json()

    suffix = CallsignSuffix(
        suffix=data["suffix"].upper(),
        description=data.get("description"),
        try_on_miss=data.get("try_on_miss", True),
        strip_on_normalize=data.get("strip_on_normalize", True),
        enabled=data.get("enabled", True),
        priority=data.get("priority", 100),
    )

    db.session.add(suffix)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_callsign_suffix(suffix)), 201


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/callsign-suffixes/<int:suffix_id>", methods=["GET"])
def get_callsign_suffix(suffix_id):
    """Get a specific callsign suffix"""
    suffix = CallsignSuffix.query.get_or_404(suffix_id)
    return jsonify(_serialize_callsign_suffix(suffix))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/callsign-suffixes/<int:suffix_id>", methods=["PUT"])
def update_callsign_suffix(suffix_id):
    """Update a callsign suffix"""
    suffix = CallsignSuffix.query.get_or_404(suffix_id)
    data = request.get_json()

    suffix.suffix = data.get("suffix", suffix.suffix).upper()
    suffix.description = data.get("description", suffix.description)
    suffix.try_on_miss = data.get("try_on_miss", suffix.try_on_miss)
    suffix.strip_on_normalize = data.get("strip_on_normalize", suffix.strip_on_normalize)
    suffix.enabled = data.get("enabled", suffix.enabled)
    suffix.priority = data.get("priority", suffix.priority)

    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()

    return jsonify(_serialize_callsign_suffix(suffix))


@fcc_match_patterns_bp.route("/api/fcc-match-patterns/callsign-suffixes/<int:suffix_id>", methods=["DELETE"])
def delete_callsign_suffix(suffix_id):
    """Delete a callsign suffix"""
    suffix = CallsignSuffix.query.get_or_404(suffix_id)
    db.session.delete(suffix)
    db.session.commit()
    cache_service.clear_all()
    _clear_pattern_cache()
    return "", 204
