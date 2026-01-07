"""
Quality Service - Handles channel quality ranking and duplicate collapsing.

This service provides functionality to:
1. Rank channels by quality based on their tags (4K, UHD, RAW, 60FPS, HD, etc.)
2. Collapse duplicate channels that differ only by format/quality
3. Detect duplicates by EPG mapping (channels mapped to same EPG source)
4. Factor in health check data when selecting best duplicate
5. Keep the highest quality version when collapsing duplicates
"""

import logging
from typing import Any, Dict, List, Optional

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

        Duplicate detection considers:
        1. Matching cleaned names (primary detection)
        2. Same EPG channel mapping (alternative detection for edge cases)
        3. Quality scoring based on tags + health status

        Args:
            channels: List of channel dictionaries
            key_field: Field to use for grouping duplicates (default: cleaned_name)
            tags_field: Field containing the channel's tags (default: tags)

        Returns:
            List of channels with duplicates collapsed
        """
        if not channels:
            return []

        # Group channels by their key (cleaned_name) and EPG mapping
        groups: Dict[str, List[Dict[str, Any]]] = {}
        epg_groups: Dict[Optional[int], List[Dict[str, Any]]] = {}

        for channel in channels:
            # Primary grouping by cleaned_name
            key = channel.get(key_field) or channel.get("name", "")
            if not key:
                key = channel.get("name", "unknown")

            key_normalized = key.strip().lower()
            if key_normalized not in groups:
                groups[key_normalized] = []
            groups[key_normalized].append(channel)

            # Secondary grouping by EPG mapping
            epg_mapping = QualityService.get_epg_mapping_info(channel)
            if epg_mapping:
                epg_id = epg_mapping.get("epg_channel_id")
                if epg_id not in epg_groups:
                    epg_groups[epg_id] = []
                epg_groups[epg_id].append(channel)

        # Select best channel from each group
        result = []
        collapsed_stream_ids = set()

        for key, group in groups.items():
            if len(group) == 1:
                # No duplicates, keep as-is
                best = group[0]
                best["duplicate_count"] = 0
                best["collapsed_from"] = None
                result.append(best)
                logger.debug(f"Channel '{key}' has no duplicates, keeping: stream_id={best.get('stream_id')}")
            else:
                # Multiple versions - pick the best quality one
                best = max(
                    group,
                    key=lambda ch: QualityService.get_quality_score_with_health(
                        ch.get(tags_field, []),
                        ch.get("health_status"),
                    ),
                )

                # Log duplicate collapse decision
                logger.info(
                    f"Collapsing {len(group)} duplicates for '{key}': "
                    f"keeping stream_id={best.get('stream_id')} "
                    f"(quality_score={QualityService.get_quality_score_with_health(best.get(tags_field, []), best.get('health_status'))})"
                )

                for ch in group:
                    if ch.get("stream_id") != best.get("stream_id"):
                        reason = "matched cleaned_name"
                        epg_mapping = QualityService.get_epg_mapping_info(ch)
                        if epg_mapping:
                            reason += f", EPG: {epg_mapping.get('epg_channel_id')}"
                        logger.debug(
                            f"  Discarding duplicate stream_id={ch.get('stream_id')} ({reason}), "
                            f"quality_score={QualityService.get_quality_score_with_health(ch.get(tags_field, []), ch.get('health_status'))}"
                        )
                        collapsed_stream_ids.add(ch.get("stream_id"))

                # Add metadata about collapsed duplicates
                best["duplicate_count"] = len(group) - 1
                best["collapsed_from"] = [
                    {
                        "stream_id": ch.get("stream_id"),
                        "name": ch.get("name"),
                        "tags": ch.get(tags_field, []),
                        "quality_score": QualityService.get_quality_score(ch.get(tags_field, [])),
                        "health_status": ch.get("health_status"),
                        "health_score": QualityService.get_health_score(ch.get("health_status")),
                    }
                    for ch in group
                    if ch.get("stream_id") != best.get("stream_id")
                ]
                result.append(best)

        logger.info(
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

    @staticmethod
    def get_health_score(health_status: Optional[Dict[str, Any]]) -> int:
        """
        Calculate a quality score based on channel health status.

        Healthy channels score higher than degraded/down channels.

        Args:
            health_status: Health status dict with 'status' and check stats

        Returns:
            Health score (0-50 points)
        """
        if not health_status:
            return 0

        status = health_status.get("status", "unknown")
        successful_checks = health_status.get("successful_checks", 0)
        total_checks = health_status.get("total_checks", 0)

        # Base score by status
        status_scores = {
            "healthy": 50,
            "degraded": 25,
            "unknown": 10,
            "down": -50,
            "ignored": 0,
        }
        base_score = status_scores.get(status, 0)

        # Bonus for success rate (up to 10 additional points)
        if total_checks > 0:
            success_rate = successful_checks / total_checks
            base_score += int(success_rate * 10)

        return base_score

    @staticmethod
    def get_epg_mapping_info(channel_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract EPG mapping information from channel dict.

        Looks for epg_mappings list or individual mapping fields.

        Args:
            channel_dict: Channel dictionary

        Returns:
            EPG mapping info dict or None
        """
        # Check for explicit mappings list
        epg_mappings = channel_dict.get("epg_mappings", [])
        if epg_mappings:
            # Return first mapping (or could aggregate if multiple)
            first_mapping = epg_mappings[0]
            return {
                "epg_channel_id": first_mapping.get("epg_channel_id"),
                "mapping_type": first_mapping.get("mapping_type"),
                "confidence": first_mapping.get("confidence", 1.0),
            }

        # Check for single mapping fields
        if "epg_channel_id" in channel_dict:
            return {
                "epg_channel_id": channel_dict.get("epg_channel_id"),
                "mapping_type": channel_dict.get("mapping_type", "unknown"),
                "confidence": channel_dict.get("confidence", 1.0),
            }

        return None

    @staticmethod
    def get_quality_score_with_health(
        tags: List[str],
        health_status: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Calculate combined quality score based on tags and health status.

        This is the primary scoring function for duplicate selection.

        Args:
            tags: List of quality tags
            health_status: Optional health status dict

        Returns:
            Combined quality score
        """
        tag_score = QualityService.get_quality_score(tags)
        health_score = QualityService.get_health_score(health_status)
        return tag_score + health_score
