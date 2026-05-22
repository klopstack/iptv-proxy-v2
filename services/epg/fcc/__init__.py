"""
FCC EPG domain — facility data and EPG matching for US broadcast channels.
"""

from services.epg.fcc.matching import (
    build_epg_lookup_indices,
    build_fcc_epg_indices,
    get_fcc_facility_for_channel,
    load_country_tags_for_channels,
    load_existing_mappings,
    load_fcc_facilities,
    lookup_fcc_callsign,
    match_by_fcc_callsign,
    match_by_fcc_network,
    preview_fcc_epg_matches,
)
from services.fcc_facility_service import FccFacilityService

__all__ = [
    "FccFacilityService",
    "preview_fcc_epg_matches",
    "build_fcc_epg_indices",
    "build_epg_lookup_indices",
    "get_fcc_facility_for_channel",
    "match_by_fcc_callsign",
    "match_by_fcc_network",
    "load_fcc_facilities",
    "lookup_fcc_callsign",
    "load_country_tags_for_channels",
    "load_existing_mappings",
]
