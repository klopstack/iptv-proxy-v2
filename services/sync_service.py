"""
Channel sync service for synchronizing channels from IPTV providers to local database
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from models import Account, Category, Channel, db
from services.iptv_service import IPTVService

logger = logging.getLogger(__name__)


class ChannelSyncService:
    """Service for synchronizing channels from IPTV providers"""

    @staticmethod
    def sync_account(account_id: int, force: bool = False) -> Dict:
        """
        Sync channels and categories for a specific account

        Args:
            account_id: Account ID to sync
            force: Force sync even if recently synced

        Returns:
            Dict with sync statistics
        """
        account = Account.query.get(account_id)
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
            iptv_service = IPTVService(account.server, account.username, account.password)

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
                cutoff_time = datetime.utcnow() - timedelta(minutes=5)
                deactivated = Channel.query.filter(
                    Channel.account_id == account_id, Channel.is_active == True, Channel.last_seen < cutoff_time
                ).update({"is_active": False})
                db.session.commit()
                stats["channels_deactivated"] = deactivated

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
        now = datetime.utcnow()

        # Build lookup of existing categories
        existing = {
            (cat.category_id): cat
            for cat in Category.query.filter_by(account_id=account_id).all()
        }

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
        now = datetime.utcnow()

        # Build lookup of existing channels
        existing = {
            (chan.stream_id): chan
            for chan in Channel.query.filter_by(account_id=account_id).all()
        }

        # Build lookup of categories
        categories = {
            cat.category_id: cat.id
            for cat in Category.query.filter_by(account_id=account_id).all()
        }

        for chan_data in channels:
            stream_id = str(chan_data.get("stream_id", ""))
            name = chan_data.get("name", "Unknown")

            if not stream_id:
                continue

            # Get category ID
            category_id = None
            cat_id_str = str(chan_data.get("category_id", ""))
            if cat_id_str and cat_id_str in categories:
                category_id = categories[cat_id_str]

            if stream_id in existing:
                # Update existing
                chan = existing[stream_id]
                changed = False

                if chan.name != name:
                    chan.name = name
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
