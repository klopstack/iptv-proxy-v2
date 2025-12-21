"""
Filter service for computing and caching filter results
"""

import logging
import re
from typing import Dict, List

from models import Account, Channel, ChannelTag, Filter, Tag, db

logger = logging.getLogger(__name__)


class FilterService:
    """Service for applying filters and caching results"""

    @staticmethod
    def compute_visibility_for_account(account_id: int) -> Dict:
        """
        Compute and store filter results for all channels in an account

        Sets the is_visible column on each channel based on whether it passes
        all enabled filters for the account.

        Args:
            account_id: Account ID to process

        Returns:
            Dict with statistics
        """
        account = db.session.get(Account, account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

        logger.info(f"Computing filter visibility for account {account.name} (ID: {account_id})")

        stats = {
            "success": True,
            "account_id": account_id,
            "account_name": account.name,
            "channels_processed": 0,
            "channels_visible": 0,
            "channels_hidden": 0,
        }

        try:
            # Get all active channels for this account
            channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()

            # Get enabled filters
            filters = Filter.query.filter_by(account_id=account_id, enabled=True).all()

            # If no filters, all channels are visible
            if not filters:
                Channel.query.filter_by(account_id=account_id, is_active=True).update({"is_visible": True})
                db.session.commit()
                stats["channels_processed"] = len(channels)
                stats["channels_visible"] = len(channels)
                logger.info(f"No filters for account {account.name}, all {len(channels)} channels visible")
                return stats

            # Load channel tags if we have tag filters
            has_tag_filters = any(f.filter_type == "tag" for f in filters)
            channel_tag_map: dict = {}

            if has_tag_filters:
                # Load tags for all channels in batches
                stream_ids = [ch.stream_id for ch in channels]
                batch_size = 1000

                for i in range(0, len(stream_ids), batch_size):
                    batch = stream_ids[i : i + batch_size]
                    tags_query = (
                        db.session.query(ChannelTag.stream_id, Tag.name)
                        .join(Tag)
                        .filter(ChannelTag.account_id == account_id, ChannelTag.stream_id.in_(batch))
                        .all()
                    )

                    for stream_id, tag_name in tags_query:
                        if stream_id not in channel_tag_map:
                            channel_tag_map[stream_id] = []
                        channel_tag_map[stream_id].append(tag_name)

            # Apply filters to each channel
            for channel in channels:
                category_name = channel.category.category_name if channel.category else ""
                channel_tags = channel_tag_map.get(channel.stream_id, [])

                is_visible = FilterService._channel_passes_filters(channel, category_name, channel_tags, filters)

                if channel.is_visible != is_visible:
                    channel.is_visible = is_visible

                stats["channels_processed"] += 1
                if is_visible:
                    stats["channels_visible"] += 1
                else:
                    stats["channels_hidden"] += 1

            db.session.commit()

            logger.info(
                f"Filter visibility computed for account {account.name}: "
                f"{stats['channels_visible']} visible, {stats['channels_hidden']} hidden"
            )

        except Exception as e:
            logger.error(f"Error computing filter visibility for account {account_id}: {e}")
            stats["success"] = False
            stats["error"] = str(e)
            db.session.rollback()

        return stats

    @staticmethod
    def _channel_passes_filters(channel: Channel, category_name: str, tags: List[str], filters: List[Filter]) -> bool:
        """
        Check if a channel passes all enabled filters

        Args:
            channel: Channel object
            category_name: Category name for the channel
            tags: List of tag names for the channel
            filters: List of Filter objects to apply

        Returns:
            True if channel passes all filters, False otherwise
        """
        for f in filters:
            if f.filter_type == "category":
                if f.filter_action == "whitelist":
                    if category_name != f.filter_value:
                        return False
                elif f.filter_action == "blacklist":
                    if category_name == f.filter_value:
                        return False

            elif f.filter_type == "channel_name":
                if f.filter_action == "whitelist":
                    if f.filter_value.lower() not in channel.name.lower():
                        return False
                elif f.filter_action == "blacklist":
                    if f.filter_value.lower() in channel.name.lower():
                        return False

            elif f.filter_type == "regex":
                try:
                    pattern = re.compile(f.filter_value, re.IGNORECASE)
                    if f.filter_action == "whitelist":
                        if not pattern.search(channel.name):
                            return False
                    elif f.filter_action == "blacklist":
                        if pattern.search(channel.name):
                            return False
                except re.error:
                    logger.warning(f"Invalid regex pattern in filter {f.id}: {f.filter_value}")
                    continue

            elif f.filter_type == "tag":
                # Tag filters: channel must have at least one matching tag
                tag_match = False
                for tag in tags:
                    if tag.upper() == f.filter_value.upper():
                        tag_match = True
                        break

                if f.filter_action == "whitelist":
                    if not tag_match:
                        return False
                elif f.filter_action == "blacklist":
                    if tag_match:
                        return False

        return True

    @staticmethod
    def invalidate_account(account_id: int) -> None:
        """
        Mark all channels in an account as needing recomputation

        This is called when filters or tags change.

        Args:
            account_id: Account ID to invalidate
        """
        logger.info(f"Invalidating filter cache for account {account_id}")
        # We'll recompute immediately rather than just marking stale
        FilterService.compute_visibility_for_account(account_id)
