"""Channel exclusion logic for EPG matching."""
import logging
import re
from typing import List, Optional, Set, Tuple

from models import Channel
from services.epg.match_rules.normalization import NormalizationMixin
from services.epg.match_rules.patterns import CachedExclusionPattern, PatternMixin

logger = logging.getLogger(__name__)


class ExclusionMixin:
    @staticmethod
    def should_exclude_channel(
        channel: Channel,
        exclusion_patterns: Optional[List[CachedExclusionPattern]] = None,
        channel_tags: Optional[Set[str]] = None,
    ) -> Tuple[bool, Optional[str], bool]:
        """
        Check if a channel should be excluded from EPG matching.

        Args:
            channel: The channel to check
            exclusion_patterns: Pre-loaded patterns (optional, loads if not provided)
            channel_tags: Pre-loaded channel tags (optional)

        Returns:
            Tuple of (should_exclude, pattern_name, should_hide_channel)
        """
        if exclusion_patterns is None:
            exclusion_patterns = PatternMixin.get_enabled_exclusion_patterns()

        for pattern in exclusion_patterns:
            matched = False

            if pattern.pattern_type == CachedExclusionPattern.TYPE_CATEGORY_NAME:
                if channel.category and channel.category.category_name:
                    if pattern.is_regex:
                        try:
                            if re.search(pattern.pattern, channel.category.category_name, re.IGNORECASE):
                                matched = True
                        except re.error:
                            logger.warning(f"Invalid regex in exclusion pattern {pattern.id}: {pattern.pattern}")
                    else:
                        if pattern.pattern.lower() in channel.category.category_name.lower():
                            matched = True

            elif pattern.pattern_type == CachedExclusionPattern.TYPE_CHANNEL_NAME:
                if channel.name:
                    if pattern.is_regex:
                        try:
                            if re.search(pattern.pattern, channel.name, re.IGNORECASE):
                                matched = True
                        except re.error:
                            logger.warning(f"Invalid regex in exclusion pattern {pattern.id}: {pattern.pattern}")
                    else:
                        if pattern.pattern.lower() in channel.name.lower():
                            matched = True

            elif pattern.pattern_type == CachedExclusionPattern.TYPE_TAG:
                if channel_tags is None:
                    # Load tags for this channel
                    channel_tags = NormalizationMixin._get_channel_tags(channel.account_id, channel.stream_id)
                if pattern.pattern.upper() in channel_tags:
                    matched = True

            if matched:
                logger.debug(
                    f"Channel '{channel.name}' excluded by pattern '{pattern.name}' " f"(hide={pattern.hide_channel})"
                )
                return True, pattern.name, pattern.hide_channel

        return False, None, False
