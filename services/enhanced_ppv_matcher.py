"""Backward compatibility — use services.ppv.matching.enhanced instead."""

import warnings

warnings.warn(
    "Import from services.ppv.matching.enhanced instead of services.enhanced_ppv_matcher",
    DeprecationWarning,
    stacklevel=2,
)

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
