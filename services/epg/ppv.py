"""
EPG PPV detection helpers.

Legacy visibility/EPG generation removed — use services.ppv.visibility and services.ppv.epg.
"""
import logging
import re
from typing import Optional

from models import Channel
from services.epg.constants import PPV_CATEGORY_PATTERNS, PPV_PLACEHOLDER_PATTERNS

logger = logging.getLogger(__name__)


def is_ppv_channel(channel: Channel) -> bool:
    """Determine if a channel is PPV based on category name patterns."""
    if not channel.category:
        return False
    category_name = channel.category.category_name.upper()
    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, category_name, re.IGNORECASE):
            logger.debug(
                "Channel '%s' identified as PPV (category='%s')",
                channel.name,
                channel.category.category_name,
            )
            return True
    return False


def is_ppv_category(category_name: str) -> bool:
    """Determine if a category name indicates PPV."""
    if not category_name:
        return False
    upper_name = category_name.upper()
    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, upper_name, re.IGNORECASE):
            return True
    return False


def is_ppv_placeholder_name(name: str) -> bool:
    """Return True if channel name is a PPV placeholder (no event scheduled)."""
    if not name:
        return True
    normalized = name.strip().upper()
    for pattern in PPV_PLACEHOLDER_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            return True
    return False


def get_ppv_event_title(channel: Channel) -> Optional[str]:
    """Extract event title from active PPV channel name, or None if placeholder."""
    if not channel.name or is_ppv_placeholder_name(channel.name):
        return None
    return channel.name.strip()
