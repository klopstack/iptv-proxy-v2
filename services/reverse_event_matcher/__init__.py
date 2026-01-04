"""
Reverse Event Matcher Package

Matches PPV channel names to known sports events using reverse lookup.
Components are decomposed for maintainability and performance.

This package provides a refactored architecture:
- Phase 1: TextProcessor - Text normalization and word extraction
- Phase 2: DateExtractor - Date parsing from channel names
- Phase 3: EventIndex - Fast event lookups by team/league/words
- Phase 4: MatchStrategy - Multiple matching algorithms
- Phase 5: MatchFilter - Confidence scoring and date filtering
- Phase 6: ReverseEventMatcher - Main orchestrator (backward compatible)

**BACKWARD COMPATIBILITY:**
The original monolithic implementation has been refactored into modular components.
All original public APIs are maintained for backward compatibility.
"""

from .match_filter import DateFilter
from .match_strategy import HIGH_CONFIDENCE, LOW_CONFIDENCE, MEDIUM_CONFIDENCE, MIN_TEAM_NAME_LENGTH
from .match_strategy import MatchResult as EventMatch  # Alias for backward compatibility

# Import main orchestrator and supporting classes
from .orchestrator import ReverseEventMatcher
from .text_processor import MIN_WORD_LENGTH, STOP_WORDS

# Singleton instance (for backward compatibility with get_reverse_matcher)
_reverse_matcher_instance = None


def get_reverse_matcher() -> ReverseEventMatcher:
    """
    Get singleton instance of ReverseEventMatcher.

    This function maintains backward compatibility with code that uses
    get_reverse_matcher() instead of instantiating ReverseEventMatcher directly.

    Returns:
        ReverseEventMatcher: Singleton instance
    """
    global _reverse_matcher_instance
    if _reverse_matcher_instance is None:
        _reverse_matcher_instance = ReverseEventMatcher()
    return _reverse_matcher_instance


# Export public API
__all__ = [
    # Main class
    "ReverseEventMatcher",
    "get_reverse_matcher",
    # Supporting classes/enums
    "DateFilter",
    "EventMatch",  # Alias for MatchResult
    # Constants
    "HIGH_CONFIDENCE",
    "MEDIUM_CONFIDENCE",
    "LOW_CONFIDENCE",
    "MIN_TEAM_NAME_LENGTH",
    "MIN_WORD_LENGTH",
    "STOP_WORDS",
]
