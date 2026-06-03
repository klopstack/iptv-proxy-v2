"""
Channel sync service for synchronizing channels from IPTV providers to local database
"""

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import delete, select, update

from models import Account, Category, Channel, ChannelLink, ChannelTag, Settings, Tag, db
from services.iptv_service import get_iptv_service_for_account
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Tag names that indicate east/west variants (used for auto-detection)
EAST_TAGS = {"EAST", "E", "ET", "EST", "EASTERN"}
WEST_TAGS = {"WEST", "W", "PT", "PST", "PACIFIC", "WESTERN"}

# Stale sync locks older than this are cleared on startup
STALE_SYNC_LOCK_MINUTES = 30


def recover_stale_sync_locks(max_age_minutes: int = STALE_SYNC_LOCK_MINUTES) -> int:
    """
    Reset sync locks held longer than max_age_minutes (e.g. after worker crash).

    Returns:
        Number of accounts recovered.
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=max_age_minutes)
    stale = Account.query.filter(
        Account.sync_in_progress.is_(True),
        db.or_(
            db.and_(Account.sync_started_at.isnot(None), Account.sync_started_at < cutoff),
            db.and_(Account.sync_started_at.is_(None), Account.updated_at < cutoff),
        ),
    ).all()

    for account in stale:
        logger.warning(
            "Recovering stale sync lock for account %s (id=%s, started=%s)",
            account.name,
            account.id,
            account.sync_started_at,
        )
        account.sync_in_progress = False
        account.sync_started_at = None

    if stale:
        db.session.commit()

    return len(stale)


@contextmanager
def sync_lock(account_id: int):
    """
    Context manager for acquiring/releasing sync lock on an account.
    Prevents concurrent syncs of the same account across multiple workers.

    Uses an atomic UPDATE to claim the lock (safe across gunicorn workers).

    Args:
        account_id: Account ID to lock

    Raises:
        ValueError: If sync is already in progress for this account

    Yields:
        Account: The locked account instance
    """
    account = db.session.get(Account, account_id)
    if not account:
        raise ValueError(f"Account {account_id} not found")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    result = db.session.execute(
        update(Account)
        .where(Account.id == account_id, Account.sync_in_progress.is_(False))
        .values(sync_in_progress=True, sync_started_at=now)
    )
    db.session.commit()

    if (getattr(result, "rowcount", 0) or 0) == 0:
        account = db.session.get(Account, account_id)
        raise ValueError(f"Sync already in progress for account {account.name if account else account_id}")

    account = db.session.get(Account, account_id)
    account_name = account.name if account else str(account_id)
    logger.info(f"Acquired sync lock for account {account_name} (ID: {account_id})")

    try:
        yield account
    finally:
        try:
            account = db.session.get(Account, account_id)
            if account:
                account.sync_in_progress = False
                account.sync_started_at = None
                db.session.commit()
                logger.info(f"Released sync lock for account {account.name} (ID: {account_id})")
        except Exception as e:
            logger.error(f"Error releasing sync lock for account {account_id}: {e}")
            db.session.rollback()


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
        # Check account exists and is enabled before acquiring lock
        account = db.session.get(Account, account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

        if not account.enabled:
            return {"success": False, "error": "Account is disabled"}

        # Acquire sync lock to prevent concurrent syncs
        try:
            with sync_lock(account_id):
                return ChannelSyncService._do_sync(account_id)
        except ValueError as e:
            # Lock acquisition failed - sync already in progress
            logger.warning(f"Failed to acquire sync lock for account {account_id}: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _do_sync(account_id: int) -> Dict:
        """
        Internal method that performs the actual sync work.
        Should only be called from sync_account() which manages the lock.
        """
        account = db.session.get(Account, account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

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
            "ppv_requeue_ids": [],
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

                stats["channel_tags_pruned"] = ChannelSyncService.prune_inactive_channel_tags(account_id)

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

                requeue_ids = stats.get("ppv_requeue_ids") or []
                if requeue_ids:
                    try:
                        from flask import current_app, has_app_context

                        from services.ppv.enrichment import get_calendar_enrichment_service

                        if has_app_context():
                            channels = Channel.query.filter(Channel.id.in_(requeue_ids)).all()
                            if channels:
                                logger.info(
                                    "Re-enriching %s PPV channel(s) after name/event change",
                                    len(channels),
                                )
                                enrich_stats = get_calendar_enrichment_service(
                                    current_app._get_current_object()  # type: ignore[attr-defined]
                                ).enrich_channels(channels)
                                stats["ppv_enrichment"] = enrich_stats
                    except Exception as e:
                        logger.error("PPV re-enrichment after sync failed: %s", e)
                        stats["errors"].append(f"PPV re-enrichment error: {str(e)}")

                if Settings.get("stream_fallback_auto_detect", "true") != "false":
                    try:
                        backup_stats = ChannelSyncService.detect_backup_pairs(account_id)
                        stats["backup_pair_detection"] = backup_stats
                    except Exception as e:
                        logger.error("Backup pair detection after sync failed: %s", e)
                        stats["errors"].append(f"Backup pair detection error: {str(e)}")

                try:
                    from services.icon_prefetch import prefetch_account_channel_icons

                    stats["icon_prefetch"] = prefetch_account_channel_icons(account_id)
                except Exception as e:
                    logger.error("Icon prefetch after sync failed: %s", e)
                    stats["errors"].append(f"Icon prefetch error: {str(e)}")

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
    def detect_backup_pairs(account_id: Optional[int] = None) -> Dict[str, Any]:
        """Auto-detect primary/backup stream pairs for proxy failover."""
        from services.backup_pair_detection import detect_backup_pairs

        return detect_backup_pairs(account_id)

    @staticmethod
    def prune_inactive_channel_tags(account_id: int) -> int:
        """
        Remove channel_tags rows for streams that are no longer active.

        ChannelTag rows are keyed by (account_id, stream_id), not channel PK,
        so tags can linger after a stream is deactivated.
        """
        inactive_stream_ids = list(
            db.session.scalars(
                select(Channel.stream_id).where(
                    Channel.account_id == account_id,
                    Channel.is_active.is_(False),
                )
            ).all()
        )
        if not inactive_stream_ids:
            return 0

        result = db.session.execute(
            delete(ChannelTag).where(
                ChannelTag.account_id == account_id,
                ChannelTag.stream_id.in_(inactive_stream_ids),
            )
        )
        db.session.commit()
        deleted = getattr(result, "rowcount", 0) or 0
        if deleted:
            logger.info(
                "Pruned %s channel_tag row(s) for inactive streams on account %s",
                deleted,
                account_id,
            )
        return deleted

    @staticmethod
    def _sync_categories(account_id: int, categories: List[Dict], stats: Dict) -> Dict:
        """Sync categories for an account"""
        now = datetime.now(timezone.utc)

        # Get account for tag rules
        account = db.session.get(Account, account_id)
        if not account:
            return stats

        # Get tag rules for name cleaning
        tag_rules = TagService.get_rules_for_account(account)

        # Build lookup of existing categories
        existing = {(cat.category_id): cat for cat in Category.query.filter_by(account_id=account_id).all()}

        for cat_data in categories:
            category_id = str(cat_data.get("category_id", ""))
            category_name = cat_data.get("category_name", "Unknown")

            if not category_id:
                continue

            # Check if this is a PPV category
            from services.epg.ppv import is_ppv_category

            is_ppv = is_ppv_category(category_name)

            # Compute cleaned name using tag rules
            # We pass empty string for channel_name since we're only processing the category
            _, _, cleaned_category_name, _ = TagService.extract_tags("", category_name, tag_rules)

            if category_id in existing:
                # Update existing
                cat = existing[category_id]
                changed = False
                if cat.category_name != category_name:
                    cat.category_name = category_name
                    changed = True
                if cat.cleaned_name != cleaned_category_name:
                    cat.cleaned_name = cleaned_category_name
                    changed = True
                if changed:
                    cat.updated_at = now
                    stats["categories_updated"] += 1
                cat.last_seen = now
                cat.is_active = True
                cat.is_ppv = is_ppv
            else:
                # Create new
                cat = Category(
                    account_id=account_id,
                    category_id=category_id,
                    category_name=category_name,
                    cleaned_name=cleaned_category_name,
                    last_seen=now,
                    is_active=True,
                    is_ppv=is_ppv,
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

            # Determine if this is a PPV channel based on category
            from services.epg.ppv import is_ppv_category

            is_ppv = is_ppv_category(category_name) if category_name else False

            # Compute cleaned name using tag rules
            _, cleaned_name, _, _ = TagService.extract_tags(name, category_name, tag_rules)

            if stream_id in existing:
                # Update existing
                chan = existing[stream_id]
                changed = False

                if chan.name != name:
                    if chan.is_ppv:
                        logger.info(
                            f"PPV channel name changed from '{chan.name}' to '{name}' - "
                            f"resetting enrichment and enqueueing for re-enrichment"
                        )
                        from services.ppv.cleanup import reset_channel_ppv_state

                        reset_channel_ppv_state(chan.id)
                        chan.ppv_enrichment_status = "queued"
                        chan.ppv_enrichment_queue_id = f"sync_{now.timestamp()}"
                        chan.ppv_enrichment_attempts = 0
                        chan.ppv_enrichment_error = None
                        chan.ppv_enrichment_last_attempt = None
                        chan.thesportsdb_id = None
                        stats.setdefault("ppv_requeue_ids", []).append(chan.id)

                    chan.name = name
                    changed = True
                if chan.cleaned_name != cleaned_name:
                    chan.cleaned_name = cleaned_name
                    changed = True
                if chan.category_id != category_id:
                    chan.category_id = category_id
                    changed = True
                if chan.is_ppv != is_ppv:
                    chan.is_ppv = is_ppv
                    if is_ppv:
                        from services.ppv.cleanup import reset_channel_ppv_state

                        reset_channel_ppv_state(chan.id)
                        chan.ppv_enrichment_status = "queued"
                        stats.setdefault("ppv_requeue_ids", []).append(chan.id)
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
                # Create new - check once more to avoid race condition
                chan = Channel.query.filter_by(account_id=account_id, stream_id=stream_id).first()
                if chan:
                    # Channel was just created by another process, update it instead
                    chan.name = name
                    chan.cleaned_name = cleaned_name
                    chan.category_id = category_id
                    chan.is_ppv = is_ppv
                    chan.last_seen = now
                    chan.is_active = True
                    stats["channels_updated"] += 1
                else:
                    chan = Channel(
                        account_id=account_id,
                        stream_id=stream_id,
                        name=name,
                        cleaned_name=cleaned_name,
                        category_id=category_id,
                        is_ppv=is_ppv,
                        ppv_enrichment_status="queued" if is_ppv else None,
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
