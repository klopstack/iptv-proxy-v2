"""Shared serializers for route responses and config export bundles."""

from services.serializers.credentials import serialize_credential
from services.serializers.epg_match import (
    serialize_epg_channel_name_mapping,
    serialize_epg_exclusion_pattern,
    serialize_epg_match_rule,
    serialize_epg_ruleset,
    serialize_ruleset,
    serialize_tag_rule,
)
from services.serializers.epg_sources import serialize_epg_source
from services.serializers.fcc import (
    serialize_callsign_suffix,
    serialize_country_suffix,
    serialize_country_tag,
    serialize_fcc_channel_pattern,
    serialize_fcc_location_pattern,
    serialize_fcc_network,
    serialize_fcc_strategy,
    serialize_quality_tag,
)

__all__ = [
    "serialize_credential",
    "serialize_epg_channel_name_mapping",
    "serialize_epg_exclusion_pattern",
    "serialize_epg_match_rule",
    "serialize_epg_ruleset",
    "serialize_epg_source",
    "serialize_callsign_suffix",
    "serialize_country_suffix",
    "serialize_country_tag",
    "serialize_fcc_channel_pattern",
    "serialize_fcc_location_pattern",
    "serialize_fcc_network",
    "serialize_fcc_strategy",
    "serialize_quality_tag",
    "serialize_ruleset",
    "serialize_tag_rule",
]
