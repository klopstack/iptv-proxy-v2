"""
PPV channel/category detection — used at sync and during enrichment filtering.
"""

import logging
import re
from typing import Optional

from models import Channel
from services.ppv.constants import GENERIC_CHANNEL_PATTERNS, PPV_CATEGORY_PATTERNS, PPV_PLACEHOLDER_PATTERNS

logger = logging.getLogger(__name__)

# Studio / analysis shows mis-parsed as vs events (e.g. "NHL Tonight @ Jun 10")
STUDIO_SHOW_PATTERNS = [
    re.compile(r"\bnhl\s+tonight\b", re.IGNORECASE),
    re.compile(r"\bnba\s+today\b", re.IGNORECASE),
    re.compile(r"\bnfl\s+today\b", re.IGNORECASE),
    re.compile(r"\bmlb\s+tonight\b", re.IGNORECASE),
    re.compile(r"\bjays\s+talk\s+plus\b", re.IGNORECASE),
    re.compile(r"\btalk\s+plus\b", re.IGNORECASE),
    re.compile(r"\bsport\s+news\b", re.IGNORECASE),
    re.compile(r"\bsports?\s+cent(?:er|re)\b", re.IGNORECASE),
    re.compile(r"\bhockey\s+central\b", re.IGNORECASE),
    re.compile(r"\bfirst\s+take\b", re.IGNORECASE),
    re.compile(r"\b(?:pre|post)[- ]?game\s+show\b", re.IGNORECASE),
    re.compile(r"\b(?:talk\s+show|sports?\s+magazine|sports?\s+analysis)\b", re.IGNORECASE),
]

_MONTH_ABBREVS = frozenset(
    {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}
)
_BOGUS_COMPETITOR_TOKENS = frozenset(
    {"tonight", "today", "news", "talk", "show", "plus", "sport", "sports", "ended"}
)


def is_studio_show_title(name: str) -> bool:
    """Return True for studio/analysis programs that are not calendar matchable."""
    if not name:
        return False
    for pattern in STUDIO_SHOW_PATTERNS:
        if pattern.search(name):
            return True
    return False


def is_bogus_extracted_competitors(competitors: tuple) -> bool:
    """
    Detect date-fragment pairs from @-style titles (e.g. Tonight vs Jun).

    Extraction sometimes treats "NHL Tonight @ Jun 10" as a two-team event.
    """
    if not competitors or len(competitors) != 2:
        return False
    left = (competitors[0] or "").strip().lower()
    right = (competitors[1] or "").strip().lower()
    if not left or not right:
        return False
    if right in _MONTH_ABBREVS and any(token in left.split() for token in _BOGUS_COMPETITOR_TOKENS):
        return True
    if left in _MONTH_ABBREVS and any(token in right.split() for token in _BOGUS_COMPETITOR_TOKENS):
        return True
    if right in _MONTH_ABBREVS and len(left.split()) <= 3 and not any(
        sep in left for sep in (" vs ", " at ", " v ")
    ):
        return True
    return False


def is_ppv_category(category_name: str) -> bool:
    """Return True if category name matches PPV patterns."""
    if not category_name:
        return False
    upper_name = category_name.upper()
    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, upper_name, re.IGNORECASE):
            return True
    return False


def is_ppv_channel(channel: Channel) -> bool:
    """Return True if channel's category indicates PPV."""
    if not channel.category:
        return False
    category_name = channel.category.category_name
    if is_ppv_category(category_name):
        logger.debug(
            "Channel '%s' identified as PPV (category='%s')",
            channel.name,
            category_name,
        )
        return True
    return False


def is_ppv_placeholder_name(name: str) -> bool:
    """Return True if channel name is a placeholder (no scheduled event)."""
    if not name:
        return True
    for pattern in PPV_PLACEHOLDER_PATTERNS:
        if re.search(pattern, name, re.IGNORECASE):
            return True
    return False


def is_generic_channel_name(name: str) -> bool:
    """Return True for numbered/generic PPV slots without event titles."""
    if not name:
        return True
    stripped = name.strip()
    for pattern in GENERIC_CHANNEL_PATTERNS:
        if pattern.match(stripped):
            return True
    return False


def get_ppv_event_title(channel: Channel) -> Optional[str]:
    """Extract event title from active PPV channel name, or None if placeholder."""
    if not channel.name or is_ppv_placeholder_name(channel.name):
        return None
    return channel.name.strip()
