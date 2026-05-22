"""Backward compatibility — use services.ppv.matching.enhanced instead."""

from services.ppv.matching.enhanced import (  # noqa: F401
    ChannelCategory,
    EnhancedMatchResult,
    EnhancedPPVMatcher,
    get_enhanced_ppv_matcher,
)

__all__ = [
    "ChannelCategory",
    "EnhancedMatchResult",
    "EnhancedPPVMatcher",
    "get_enhanced_ppv_matcher",
]
