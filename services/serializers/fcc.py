"""Serializers for FCC match pattern entities."""

from typing import Any

from models import FccMatchChannelPattern, FccMatchLocationPattern, FccMatchNetwork, FccMatchStrategy
from services.serializers._json import safe_json_loads


def serialize_fcc_network(network: FccMatchNetwork, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an FCC network pattern."""
    data = {
        "name": network.name,
        "display_name": network.display_name,
        "description": network.description,
        "fcc_affiliation_pattern": network.fcc_affiliation_pattern,
        "tag_patterns": safe_json_loads(network.tag_patterns, default=[]),
        "enabled": network.enabled,
        "priority": network.priority,
    }
    if include_id:
        data["id"] = network.id
    return data


def serialize_fcc_channel_pattern(pattern: FccMatchChannelPattern, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an FCC channel number pattern."""
    data = {
        "name": pattern.name,
        "description": pattern.description,
        "pattern": pattern.pattern,
        "pattern_type": pattern.pattern_type,
        "capture_group": pattern.capture_group,
        "networks": safe_json_loads(pattern.networks),
        "enabled": pattern.enabled,
        "priority": pattern.priority,
    }
    if include_id:
        data["id"] = pattern.id
    return data


def serialize_fcc_location_pattern(pattern: FccMatchLocationPattern, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an FCC location tag pattern."""
    data = {
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
    if include_id:
        data["id"] = pattern.id
    return data


def serialize_fcc_strategy(strategy: FccMatchStrategy, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an FCC match strategy."""
    data = {
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
    if include_id:
        data["id"] = strategy.id
    return data
