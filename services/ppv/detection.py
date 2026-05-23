"""
PPV channel/category detection — used at sync and during enrichment filtering.
"""

import logging
import re
from typing import Optional

from models import Channel
from services.ppv.constants import GENERIC_CHANNEL_PATTERNS, PPV_CATEGORY_PATTERNS, PPV_PLACEHOLDER_PATTERNS

logger = logging.getLogger(__name__)


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
