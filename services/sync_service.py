"""
Channel sync service for synchronizing channels from IPTV providers to local database
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from models import Account, Category, Channel, ChannelLink, ChannelTag, Tag, db
from services.iptv_service import IPTVService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Tag names that indicate east/west variants (used for auto-detection)
EAST_TAGS = {"EAST", "E", "ET", "EST", "EASTERN"}
WEST_TAGS = {"WEST", "W", "PT", "PST", "PACIFIC", "WESTERN"}


def get_iptv_service_for_account(account):
    """Create an IPTVService instance for an account using the best available credential."""
    cred = account.get_primary_credential()
    if cred:
        return IPTVService(account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9")
    # Fallback for legacy accounts
    return IPTVService(account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9")


class ChannelSyncService:
    """Service for synchronizing channels from IPTV providers"""

    @staticmethod
    def sync_account(account_id: int, _force: bool = False) -> Dict:
        """
        Sync channels and categories for a specific account

        Args:
            account_id: Account ID to sync
            _force: Force sync even if recently synced (reserved for future use)

        Returns:
            Dict with sync statistics
        """
        account = db.session.get(Account, account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

        if not account.enabled:
            return {"success": False, "error": "Account is disabled"}

        logger.info(f"Starting sync for account {account.name} (ID: {account_id})")

        stats = {
            "success": True,
            "account_id": account_id,
            "account_name": account.name,
            "categories_added": 0,
            "categories_updated": 0,
            "channels_added": 0,
            "channels_updated": 0,
            "channels_deactivated": 0,
            "errors": [],
        }

        try:
            iptv_service = get_iptv_service_for_account(account)

            # Sync categories first
            try:
                categories = iptv_service.get_live_categories()
                stats = ChannelSyncService._sync_categories(account_id, categories, stats)
            except Exception as e:
                logger.error(f"Error syncing categories for account {account_id}: {e}")
                stats["errors"].append(f"Categories sync error: {str(e)}")

            # Sync channels
            try:
                channels = iptv_service.get_live_streams()
                stats = ChannelSyncService._sync_channels(account_id, channels, stats)
            except Exception as e:
                logger.error(f"Error syncing channels for account {account_id}: {e}")
                stats["errors"].append(f"Channels sync error: {str(e)}")
                stats["success"] = False

            # Mark channels not seen in this sync as inactive
            if stats["success"]:
                cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=5)
                deactivated = Channel.query.filter(
                    Channel.account_id == account_id, Channel.is_active, Channel.last_seen < cutoff_time
                ).update({"is_active": False})
                db.session.commit()
                stats["channels_deactivated"] = deactivated

                # Compute filter visibility after sync
                try:
                    from services.filter_service import FilterService

                    filter_stats = FilterService.compute_visibility_for_account(account_id)
                    stats["channels_visible"] = filter_stats.get("channels_visible", 0)
                    stats["channels_hidden"] = filter_stats.get("channels_hidden", 0)
                    logger.info(
                        f"Filter visibility computed: {stats['channels_visible']} visible, {stats['channels_hidden']} hidden"
                    )
                except Exception as e:
                    logger.error(f"Error computing filter visibility after sync: {e}")
                    stats["errors"].append(f"Filter visibility error: {str(e)}")

            logger.info(
                f"Sync completed for account {account.name}: "
                f"{stats['channels_added']} added, {stats['channels_updated']} updated, "
                f"{stats['channels_deactivated']} deactivated"
            )

        except Exception as e:
            logger.error(f"Fatal error syncing account {account_id}: {e}")
            stats["success"] = False
            stats["errors"].append(f"Fatal error: {str(e)}")
            db.session.rollback()

        return stats

    @staticmethod
    def _sync_categories(account_id: int, categories: List[Dict], stats: Dict) -> Dict:
        """Sync categories for an account"""
        now = datetime.now(timezone.utc)

        # Build lookup of existing categories
        existing = {(cat.category_id): cat for cat in Category.query.filter_by(account_id=account_id).all()}

        for cat_data in categories:
            category_id = str(cat_data.get("category_id", ""))
            category_name = cat_data.get("category_name", "Unknown")

            if not category_id:
                continue

            if category_id in existing:
                # Update existing
                cat = existing[category_id]
                if cat.category_name != category_name:
                    cat.category_name = category_name
                    cat.updated_at = now
                    stats["categories_updated"] += 1
                cat.last_seen = now
                cat.is_active = True
            else:
                # Create new
                cat = Category(
                    account_id=account_id,
                    category_id=category_id,
                    category_name=category_name,
                    last_seen=now,
                    is_active=True,
                )
                db.session.add(cat)
                stats["categories_added"] += 1

        db.session.commit()
        return stats

    @staticmethod
    def _sync_channels(account_id: int, channels: List[Dict], stats: Dict) -> Dict:
        """Sync channels for an account"""
        now = datetime.now(timezone.utc)

        # Get account for tag rules
        account = db.session.get(Account, account_id)
        if not account:
            return stats

        # Get tag rules for name cleaning
        tag_rules = TagService.get_rules_for_account(account)

        # Build lookup of existing channels
        existing = {(chan.stream_id): chan for chan in Channel.query.filter_by(account_id=account_id).all()}

        # Build lookup of categories (both ID mapping and name mapping)
        categories = {cat.category_id: cat.id for cat in Category.query.filter_by(account_id=account_id).all()}

        category_names = {
            cat.category_id: cat.category_name for cat in Category.query.filter_by(account_id=account_id).all()
        }

        for chan_data in channels:
            stream_id = str(chan_data.get("stream_id", ""))
            name = chan_data.get("name", "Unknown")

            if not stream_id:
                continue

            # Get category ID and name
            category_id = None
            category_name = ""
            cat_id_str = str(chan_data.get("category_id", ""))
            if cat_id_str and cat_id_str in categories:
                category_id = categories[cat_id_str]
                category_name = category_names.get(cat_id_str, "")

            # Compute cleaned name using tag rules
            _, cleaned_name = TagService.extract_tags(name, category_name, tag_rules)

            if stream_id in existing:
                # Update existing
                chan = existing[stream_id]
                changed = False

                if chan.name != name:
                    chan.name = name
                    changed = True
                if chan.cleaned_name != cleaned_name:
                    chan.cleaned_name = cleaned_name
                    changed = True
                if chan.category_id != category_id:
                    chan.category_id = category_id
                    changed = True

                # Update other fields
                for field in [
                    "stream_type",
                    "stream_icon",
                    "epg_channel_id",
                    "added",
                    "custom_sid",
                    "tv_archive",
                    "direct_source",
                    "tv_archive_duration",
                ]:
                    new_value = chan_data.get(field)
                    if new_value and getattr(chan, field) != new_value:
                        setattr(chan, field, new_value)
                        changed = True

                if changed:
                    chan.updated_at = now
                    stats["channels_updated"] += 1

                chan.last_seen = now
                chan.is_active = True
            else:
                # Create new
                chan = Channel(
                    account_id=account_id,
                    stream_id=stream_id,
                    name=name,
                    cleaned_name=cleaned_name,
                    category_id=category_id,
                    stream_type=chan_data.get("stream_type"),
                    stream_icon=chan_data.get("stream_icon"),
                    epg_channel_id=chan_data.get("epg_channel_id"),
                    added=chan_data.get("added"),
                    custom_sid=chan_data.get("custom_sid"),
                    tv_archive=chan_data.get("tv_archive"),
                    direct_source=chan_data.get("direct_source"),
                    tv_archive_duration=chan_data.get("tv_archive_duration"),
                    last_seen=now,
                    is_active=True,
                )
                db.session.add(chan)
                stats["channels_added"] += 1

        db.session.commit()
        return stats

    @staticmethod
    def sync_all_accounts() -> List[Dict]:
        """
        Sync all enabled accounts

        Returns:
            List of sync statistics for each account
        """
        accounts = Account.query.filter_by(enabled=True).all()
        results = []

        for account in accounts:
            stats = ChannelSyncService.sync_account(account.id)
            results.append(stats)

        return results

    @staticmethod
    def get_sync_status(account_id: int) -> Dict:
        """Get sync status for an account"""
        total = Channel.query.filter_by(account_id=account_id).count()
        active = Channel.query.filter_by(account_id=account_id, is_active=True).count()
        inactive = total - active

        # Get last sync time (most recent channel update)
        last_sync = (
            db.session.query(Channel.last_seen)
            .filter_by(account_id=account_id)
            .order_by(Channel.last_seen.desc())
            .first()
        )

        return {
            "account_id": account_id,
            "total_channels": total,
            "active_channels": active,
            "inactive_channels": inactive,
            "last_sync": last_sync[0] if last_sync else None,
        }

    @staticmethod
    def detect_channel_links(account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Auto-detect east/west channel links based on tags and cleaned names.

        Channels with the same cleaned_name (base name) and opposite east/west
        tags are linked. West channels get a -3 hour time offset from east.

        Args:
            account_id: Optional account ID to limit detection to. If None, all accounts.

        Returns:
            Dict with detection statistics
        """
        stats: Dict[str, Any] = {
            "links_created": 0,
            "links_skipped": 0,  # Already exist
            "channels_processed": 0,
            "errors": [],
        }

        # Get all channels (optionally filtered by account)
        channel_query = Channel.query.filter_by(is_active=True)
        if account_id:
            channel_query = channel_query.filter_by(account_id=account_id)
        channels = channel_query.all()

        if not channels:
            return stats

        stats["channels_processed"] = len(channels)

        # Load tags for all channels
        channel_ids = [ch.id for ch in channels]
        channel_stream_ids = {ch.id: ch.stream_id for ch in channels}
        channel_account_ids = {ch.id: ch.account_id for ch in channels}

        # Build channel_id -> set of tag names
        channel_tags: Dict[int, Set[str]] = {ch.id: set() for ch in channels}

        # Batch load tags
        BATCH_SIZE = 500
        for i in range(0, len(channel_ids), BATCH_SIZE):
            batch_ids = channel_ids[i : i + BATCH_SIZE]
            # We need to join through stream_id and account_id
            for ch_id in batch_ids:
                stream_id = channel_stream_ids[ch_id]
                acc_id = channel_account_ids[ch_id]
                tag_rows = (
                    db.session.query(Tag.name)
                    .join(ChannelTag, Tag.id == ChannelTag.tag_id)
                    .filter(ChannelTag.account_id == acc_id, ChannelTag.stream_id == stream_id)
                    .all()
                )
                for (tag_name,) in tag_rows:
                    channel_tags[ch_id].add(tag_name.upper())

        # Group channels by account and cleaned_name
        # Structure: account_id -> cleaned_name -> list of (channel, variant)
        grouped: Dict[int, Dict[str, List[tuple]]] = {}

        for ch in channels:
            acc_id = ch.account_id
            base_name = (ch.cleaned_name or ch.name or "").lower().strip()

            if not base_name:
                continue

            tags = channel_tags.get(ch.id, set())
            variant = None
            if tags & EAST_TAGS:
                variant = "east"
            elif tags & WEST_TAGS:
                variant = "west"

            if acc_id not in grouped:
                grouped[acc_id] = {}
            if base_name not in grouped[acc_id]:
                grouped[acc_id][base_name] = []
            grouped[acc_id][base_name].append((ch, variant))

        # For each group with both east and west variants, create links
        for acc_id, names in grouped.items():
            for base_name, variants in names.items():
                east_channels = [ch for ch, v in variants if v == "east"]
                west_channels = [ch for ch, v in variants if v == "west"]
                none_channels = [ch for ch, v in variants if v is None]

                # If we have west but no explicit east, use the untagged channel as east
                if west_channels and not east_channels and none_channels:
                    east_channels = none_channels

                # Link each west channel to the first east channel
                if west_channels and east_channels:
                    east_ch = east_channels[0]
                    for west_ch in west_channels:
                        # Check if link already exists
                        existing = ChannelLink.query.filter_by(
                            channel_id=west_ch.id,
                            source_channel_id=east_ch.id,
                        ).first()

                        if existing:
                            stats["links_skipped"] += 1
                            continue

                        # Create new link with -3 hour offset (west = east - 3 hours)
                        link = ChannelLink(
                            channel_id=west_ch.id,
                            source_channel_id=east_ch.id,
                            time_offset_hours=-3,
                            link_type="time_shifted",
                            auto_detected=True,
                        )
                        db.session.add(link)
                        stats["links_created"] += 1
                        logger.info(f"Auto-detected link: {west_ch.name} -> {east_ch.name} (-3h)")

        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            stats["errors"].append(f"Database error: {str(e)}")
            logger.error(f"Error saving channel links: {e}")

        logger.info(
            f"Channel link detection complete: {stats['links_created']} created, "
            f"{stats['links_skipped']} skipped (existing)"
        )

        return stats
