"""
EPG Service Module

This package provides EPG (Electronic Program Guide) functionality:
- XMLTV parsing and generation
- Channel-to-EPG matching
- FCC database integration for US broadcast channels
- PPV channel detection and handling
- EPG coverage statistics
- EPG XML caching
- Program data storage and retrieval

Submodules:
    - constants: EPG-related constants (PPV patterns, broadcast networks)
    - utils: Utility functions (XMLTV parsing helpers, normalization)
    - parsing: XMLTV parsing and EPG source syncing
    - matching: Channel-to-EPG matching algorithms
    - generation: EPG XML generation for channels
    - ppv: PPV channel detection and EPG generation
    - coverage: EPG coverage statistics
    - fcc: FCC database integration for US broadcast channels
    - cache: EPG XML filesystem cache
    - programs: EPG program storage and retrieval

Usage:
    # Import specific modules
    from services.epg.generation import generate_epg_for_channels
    from services.epg.matching import EpgMatcher
    from services.epg.parsing import parse_xmltv
    from services.epg.fcc import preview_fcc_epg_matches
    from services.epg.ppv import is_ppv_channel
    from services.epg.cache import load_from_cache, save_to_cache
    from services.epg.programs import get_current_program, search_programs_by_title

    # Import constants
    from services.epg.constants import PPV_CATEGORY_PATTERNS
"""
# Import submodules for direct access
from services.epg import cache, constants, coverage, fcc, generation, matching, parsing, ppv, programs, utils

# Re-export commonly used constants for convenience
from services.epg.constants import (
    EAST_TAGS,
    MAJOR_BROADCAST_NETWORKS,
    NETWORK_FALLBACK_EPG_IDS,
    PPV_CATEGORY_PATTERNS,
    PPV_PLACEHOLDER_PATTERNS,
    STRIP_WORDS,
    WEST_TAGS,
)

__all__ = [
    # Submodules
    "cache",
    "constants",
    "utils",
    "parsing",
    "matching",
    "generation",
    "ppv",
    "coverage",
    "fcc",
    "programs",
    # Constants (re-exported for convenience)
    "MAJOR_BROADCAST_NETWORKS",
    "NETWORK_FALLBACK_EPG_IDS",
    "PPV_CATEGORY_PATTERNS",
    "PPV_PLACEHOLDER_PATTERNS",
    "EAST_TAGS",
    "WEST_TAGS",
    "STRIP_WORDS",
]
