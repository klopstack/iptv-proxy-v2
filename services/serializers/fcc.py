"""Serializers for FCC match pattern entities."""

from typing import Any

from models import (
    CallsignSuffix,
    CountryTag,
    EpgCountrySuffix,
    FccMatchChannelPattern,
    FccMatchLocationPattern,
    FccMatchNetwork,
    FccMatchStrategy,
    QualityTag,
)
from services.datetime_utils import serialize_utc_iso
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


def serialize_country_suffix(suffix: EpgCountrySuffix, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize an EPG country suffix mapping."""
    data = {
        "country_code": suffix.country_code,
        "country_name": suffix.country_name,
        "epg_suffixes": safe_json_loads(suffix.epg_suffixes, default=[]),
        "enabled": suffix.enabled,
        "priority": suffix.priority,
        "created_at": serialize_utc_iso(suffix.created_at),
        "updated_at": serialize_utc_iso(suffix.updated_at),
    }
    if include_id:
        data["id"] = suffix.id
    return data


def serialize_quality_tag(tag: QualityTag, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize a quality tag."""
    data = {
        "tag_name": tag.tag_name,
        "display_name": tag.display_name,
        "category": tag.category,
        "quality_score": tag.quality_score,
        "exclude_from_location": tag.exclude_from_location,
        "enabled": tag.enabled,
        "created_at": serialize_utc_iso(tag.created_at),
        "updated_at": serialize_utc_iso(tag.updated_at),
    }
    if include_id:
        data["id"] = tag.id
    return data


def serialize_country_tag(tag: CountryTag, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize a country tag."""
    data = {
        "tag_name": tag.tag_name,
        "country_name": tag.country_name,
        "iso_code": tag.iso_code,
        "exclude_from_location": tag.exclude_from_location,
        "enabled": tag.enabled,
        "created_at": serialize_utc_iso(tag.created_at),
        "updated_at": serialize_utc_iso(tag.updated_at),
    }
    if include_id:
        data["id"] = tag.id
    return data


def serialize_callsign_suffix(suffix: CallsignSuffix, *, include_id: bool = True) -> dict[str, Any]:
    """Serialize a callsign suffix."""
    data = {
        "suffix": suffix.suffix,
        "description": suffix.description,
        "try_on_miss": suffix.try_on_miss,
        "strip_on_normalize": suffix.strip_on_normalize,
        "enabled": suffix.enabled,
        "priority": suffix.priority,
        "created_at": serialize_utc_iso(suffix.created_at),
        "updated_at": serialize_utc_iso(suffix.updated_at),
    }
    if include_id:
        data["id"] = suffix.id
    return data
