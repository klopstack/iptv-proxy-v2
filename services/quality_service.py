"""
Quality Service - Handles channel quality ranking and duplicate collapsing.

This service provides functionality to:
1. Rank channels by quality based on their tags (4K, UHD, RAW, 60FPS, HD, etc.)
2. Collapse duplicate channels that differ only by format/quality
3. Keep the highest quality version when collapsing duplicates
"""

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Quality ranking - higher score = higher quality
# Based on common IPTV quality indicators
# Scores are additive for combined tags (e.g., RAW+60FPS scores higher than just 60FPS)
QUALITY_RANKS = {
    # Resolution-based (primary quality indicators)
    "4K": 100,
    "UHD": 90,
    "2160P": 90,
    "FHD": 50,
    "1080P": 50,
    "HD": 40,
    "720P": 30,
    "SD": 10,
    "480P": 10,
    # Encoding quality (additive bonuses)
    "RAW": 35,  # Raw uncompressed - significant quality boost
    "HEVC": 15,  # Better compression
    "H265": 15,
    "H264": 10,
    # Frame rate (additive bonuses)
    "60FPS": 25,
    "50FPS": 22,
    "30FPS": 12,
    "25FPS": 10,
    "24FPS": 8,
    # Audio quality
    "DOLBY": 5,
    "ATMOS": 5,
    "5.1": 3,
    "STEREO": 1,
    # Bitrate indicators (when tagged)
    "HQ": 10,  # High quality
    "LQ": -10,  # Low quality penalty
}


class QualityService:
    """Service for ranking and collapsing duplicate channels by quality"""

    @staticmethod
    def get_quality_score(tags: List[str]) -> int:
        """
        Calculate a quality score based on channel tags.

        Higher score = higher quality. Scores are ADDITIVE - a channel with
        both RAW and 60FPS will score higher than one with just 60FPS.

        Args:
            tags: List of tag names for the channel

        Returns:
            Quality score (sum of all matching quality tags)
        """
        if not tags:
            return 0

        score = 0
        for tag in tags:
            tag_upper = tag.upper()
            if tag_upper in QUALITY_RANKS:
                score += QUALITY_RANKS[tag_upper]

        return score

    @staticmethod
    def get_quality_tags(tags: List[str]) -> List[str]:
        """
        Extract quality-related tags from a list of tags.

        Args:
            tags: List of tag names

        Returns:
            List of quality-related tags only
        """
        quality_tags = []
        for tag in tags:
            if tag.upper() in QUALITY_RANKS:
                quality_tags.append(tag)
        return quality_tags

    @staticmethod
    def collapse_duplicates(
        channels: List[Dict[str, Any]],
        key_field: str = "cleaned_name",
        tags_field: str = "tags",
    ) -> List[Dict[str, Any]]:
        """
        Collapse duplicate channels, keeping the highest quality version.

        Channels are grouped by their cleaned name (or other key field),
        and only the highest quality version of each unique channel is kept.

        Args:
            channels: List of channel dictionaries
            key_field: Field to use for grouping duplicates (default: cleaned_name)
            tags_field: Field containing the channel's tags (default: tags)

        Returns:
            List of channels with duplicates collapsed
        """
        if not channels:
            return []

        # Group channels by their key (cleaned_name)
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for channel in channels:
            key = channel.get(key_field) or channel.get("name", "")
            if not key:
                # If no cleaned_name, use original name
                key = channel.get("name", "unknown")

            key_normalized = key.strip().lower()
            if key_normalized not in groups:
                groups[key_normalized] = []
            groups[key_normalized].append(channel)

        # Select best channel from each group
        result = []
        for key, group in groups.items():
            if len(group) == 1:
                # No duplicates, keep as-is
                best = group[0]
                best["duplicate_count"] = 0
                best["collapsed_from"] = None
            else:
                # Multiple versions - pick the best quality one
                best = max(
                    group,
                    key=lambda ch: QualityService.get_quality_score(ch.get(tags_field, [])),
                )
                # Add metadata about collapsed duplicates
                best["duplicate_count"] = len(group) - 1
                best["collapsed_from"] = [
                    {
                        "stream_id": ch.get("stream_id"),
                        "name": ch.get("name"),
                        "tags": ch.get(tags_field, []),
                        "quality_score": QualityService.get_quality_score(ch.get(tags_field, [])),
                    }
                    for ch in group
                    if ch.get("stream_id") != best.get("stream_id")
                ]

            result.append(best)

        logger.debug(
            f"Collapsed {len(channels)} channels into {len(result)} unique channels "
            f"({len(channels) - len(result)} duplicates removed)"
        )

        return result

    @staticmethod
    def sort_by_quality(channels: List[Dict[str, Any]], tags_field: str = "tags") -> List[Dict[str, Any]]:
        """
        Sort channels by quality score (highest first).

        Args:
            channels: List of channel dictionaries
            tags_field: Field containing the channel's tags

        Returns:
            Sorted list of channels
        """
        return sorted(
            channels,
            key=lambda ch: QualityService.get_quality_score(ch.get(tags_field, [])),
            reverse=True,
        )

    @staticmethod
    def get_duplicates_info(
        channels: List[Dict[str, Any]],
        key_field: str = "cleaned_name",
        tags_field: str = "tags",
    ) -> Dict[str, Any]:
        """
        Analyze channels for duplicates without collapsing.

        Args:
            channels: List of channel dictionaries
            key_field: Field to use for grouping duplicates
            tags_field: Field containing the channel's tags

        Returns:
            Dictionary with duplicate analysis:
            - total_channels: Total input channels
            - unique_channels: Number of unique channels
            - duplicate_count: Number of duplicate channels
            - duplicate_groups: Groups of duplicates with their quality scores
        """
        if not channels:
            return {
                "total_channels": 0,
                "unique_channels": 0,
                "duplicate_count": 0,
                "duplicate_groups": [],
            }

        # Group channels by their key
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for channel in channels:
            key = channel.get(key_field) or channel.get("name", "")
            if not key:
                key = channel.get("name", "unknown")

            key_normalized = key.strip().lower()
            if key_normalized not in groups:
                groups[key_normalized] = []
            groups[key_normalized].append(channel)

        # Find groups with duplicates
        duplicate_groups = []
        for key, group in groups.items():
            if len(group) > 1:
                # Sort by quality
                sorted_group = sorted(
                    group,
                    key=lambda ch: QualityService.get_quality_score(ch.get(tags_field, [])),
                    reverse=True,
                )
                duplicate_groups.append(
                    {
                        "cleaned_name": key,
                        "count": len(group),
                        "channels": [
                            {
                                "stream_id": ch.get("stream_id"),
                                "name": ch.get("name"),
                                "tags": ch.get(tags_field, []),
                                "quality_score": QualityService.get_quality_score(ch.get(tags_field, [])),
                                "is_best": ch == sorted_group[0],
                            }
                            for ch in sorted_group
                        ],
                    }
                )

        return {
            "total_channels": len(channels),
            "unique_channels": len(groups),
            "duplicate_count": len(channels) - len(groups),
            "duplicate_groups": duplicate_groups,
        }
