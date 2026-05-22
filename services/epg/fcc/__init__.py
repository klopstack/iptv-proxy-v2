"""
FCC EPG domain — facility data and EPG matching for US broadcast channels.
"""

from services.epg.fcc.matching import (
    build_fcc_epg_indices,
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
    "lookup_fcc_callsign",
    "match_by_fcc_callsign",
    "match_by_fcc_network",
    "build_fcc_epg_indices",
    "load_fcc_facilities",
]
