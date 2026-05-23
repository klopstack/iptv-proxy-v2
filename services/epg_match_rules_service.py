"""Backward-compatible re-exports for EPG match rules service.

Prefer: from services.epg.match_rules import EpgMatchRulesService
"""
from models import EpgMatchRule  # noqa: F401 — exposed by legacy monolith via models import
from services.epg.match_rules import (
    CachedChannelNameMapping,
    CachedChannelPattern,
    CachedExclusionPattern,
    CachedFccNetwork,
    CachedFccStrategy,
    CachedLocationPattern,
    EpgMatchRulesService,
    clear_fcc_pattern_cache,
)

__all__ = [
    "EpgMatchRulesService",
    "EpgMatchRule",
    "clear_fcc_pattern_cache",
    "CachedFccNetwork",
    "CachedChannelNameMapping",
    "CachedChannelPattern",
    "CachedLocationPattern",
    "CachedFccStrategy",
    "CachedExclusionPattern",
]
