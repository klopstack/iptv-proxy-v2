"""
Text Processing Component

Handles all text normalization and word extraction with optimization:
- Pre-compiled regex patterns (module-level)
- Caching for repeated operations
- DRY consolidation of normalization logic
"""

import re
from typing import Dict, Optional, Set

# Pre-compiled regex patterns for maximum performance
_COMPILED_PATTERNS = {
    "start_timestamp": re.compile(r"start:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", re.IGNORECASE),
    "stop_timestamp": re.compile(r"stop:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", re.IGNORECASE),
    "multi_timezone": re.compile(
        r"\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+(?:uk|et|pt|ct|mt)"
        r"(?:\s*[/|]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+(?:uk|et|pt|ct|mt))+",
        re.IGNORECASE,
    ),
    "timezone_abbr": re.compile(r"\b(?:uk|et|pt|ct|mt|utc|gmt|est|pst|cst|mst)\b", re.IGNORECASE),
    "iso_date": re.compile(r"\d{4}[-/]\d{1,2}[-/]\d{1,2}"),
    "time_format": re.compile(r"\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:am|pm))?", re.IGNORECASE),
    "punctuation": re.compile(r"[^\w\s]"),
    "whitespace": re.compile(r"\s+"),
}

# Common words to ignore when tokenizing channel names
STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "in",
    "on",
    "at",
    "to",
    "for",
    "is",
    "it",
    "be",
    "as",
    "was",
    "with",
    "by",
    "from",
    "this",
    "that",
    "live",
    "event",
    "ppv",
    "hd",
    "sd",
    "4k",
    "uhd",
    "fhd",
    "us",
    "uk",
    "au",
    "ca",
    "de",
    "fr",
    "es",
    "channel",
    "stream",
    "play",
    "replay",
    "watch",
    "home",
    "away",
    "match",
    "game",
    "round",
    "session",
    "mat",
    "court",
    "field",
    "rink",
    "ring",
    "men",
    "mens",
    "women",
    "womens",
    "male",
    "female",
    "jan",
    "feb",
    "mar",
    "apr",
    "may",
    "jun",
    "jul",
    "aug",
    "sep",
    "oct",
    "nov",
    "dec",
    "am",
    "pm",
    "utc",
    "et",
    "pt",
    "ct",
    "mt",
    "start",
    "stop",
    "date",
    "time",
    # Network/provider names that cause false matches
    "espn",
    "fox",
    "nbc",
    "cbs",
    "abc",
    "tnt",
    "tbs",
    "btn",
    "sec",
    "paramount",
    "peacock",
    "stan",
    "bally",
    "sports",
    "network",
    "flo",
    "flsp",
    "flohoops",
    "flowrestling",
    "floracing",
    "floswimming",
    # Sport abbreviations
    "nfl",
    "nba",
    "nhl",
    "mlb",
    "mls",
    "ncaa",
    "ncaab",
    "ncaaf",
    "ufc",
    "mma",
    "wwe",
    "aew",
    "boxing",
    # Generic words
    "league",
    "premier",
    "championship",
    "cup",
    "series",
    "tour",
    "division",
    "conference",
    "playoff",
    "final",
    "finals",
    "offline",
    "online",
    "coming",
    "soon",
    "university",
    "college",
    "state",
}

# Minimum word length for significance
MIN_WORD_LENGTH = 4


class TextProcessor:
    """
    Handles text normalization and word extraction with caching.

    This consolidates all text processing logic that was previously
    duplicated across multiple methods (_normalize_text, _normalize_team_name).
    """

    def __init__(self):
        """Initialize with empty caches."""
        self._normalized_cache: Dict[str, str] = {}
        self._words_cache: Dict[str, Set[str]] = {}

    def normalize_text(self, text: str, cache_key: Optional[str] = None) -> str:
        """
        Normalize text for matching with optional caching.

        Applies optimized text cleaning:
        - Removes timestamps and metadata
        - Strips timezone indicators
        - Removes dates/times
        - Lowercases and removes punctuation
        - Normalizes whitespace

        Args:
            text: Text to normalize
            cache_key: Optional key for caching (use for repeated operations)

        Returns:
            Normalized text
        """
        # Check cache first
        if cache_key and cache_key in self._normalized_cache:
            return self._normalized_cache[cache_key]

        if not text:
            return ""

        # Apply pre-compiled patterns efficiently (ordered for best results)
        result = text
        for pattern in (
            _COMPILED_PATTERNS["start_timestamp"],
            _COMPILED_PATTERNS["stop_timestamp"],
            _COMPILED_PATTERNS["multi_timezone"],
            _COMPILED_PATTERNS["timezone_abbr"],
            _COMPILED_PATTERNS["iso_date"],
            _COMPILED_PATTERNS["time_format"],
        ):
            result = pattern.sub("", result)

        # Lowercase, remove punctuation, normalize whitespace
        result = result.lower()
        result = _COMPILED_PATTERNS["punctuation"].sub(" ", result)
        result = _COMPILED_PATTERNS["whitespace"].sub(" ", result).strip()

        # Cache if requested
        if cache_key:
            self._normalized_cache[cache_key] = result

        return result

    def extract_significant_words(self, text: str, cache_key: Optional[str] = None) -> Set[str]:
        """
        Extract significant words from text with optional caching.

        Filters out stop words and words shorter than MIN_WORD_LENGTH.

        Args:
            text: Text to extract words from
            cache_key: Optional key for caching

        Returns:
            Set of significant words
        """
        # Check cache first
        if cache_key and cache_key in self._words_cache:
            return self._words_cache[cache_key]

        # Normalize and split
        normalized = self.normalize_text(text)
        words = normalized.split()

        # Filter out stop words and short words
        significant = {w for w in words if len(w) >= MIN_WORD_LENGTH and w not in STOP_WORDS}

        # Cache if requested
        if cache_key:
            self._words_cache[cache_key] = significant

        return significant

    def clear_cache(self) -> None:
        """Clear all normalization caches."""
        self._normalized_cache.clear()
        self._words_cache.clear()

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for monitoring."""
        return {
            "normalized_cache_size": len(self._normalized_cache),
            "words_cache_size": len(self._words_cache),
        }
