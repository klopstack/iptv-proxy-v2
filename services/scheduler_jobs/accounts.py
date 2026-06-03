"""IPTV account channel sync job."""

import logging
from datetime import datetime, timezone
from typing import Callable

from models import Account, db
from services.sync_service import ChannelSyncService
from services.tag_service import TagService

logger = logging.getLogger(__name__)


def run_account_sync(*, touch_heartbeat: Callable[[], None]) -> bool:
    accounts = Account.query.filter_by(enabled=True).all()
    logger.info("Syncing %s enabled account(s)", len(accounts))
    all_ok = True

    for account in accounts:
        try:
            touch_heartbeat()
            logger.info("Syncing account: %s", account.name)
            stats = ChannelSyncService.sync_account(account.id)
            success = bool(stats.get("success"))
            if not success:
                all_ok = False
            logger.info(
                "Account %s synced: %s added, %s updated, %s deactivated, success=%s",
                account.name,
                stats.get("channels_added", 0),
                stats.get("channels_updated", 0),
                stats.get("channels_deactivated", 0),
                success,
            )
            _process_account_tags(account)
            account.last_sync = datetime.now(timezone.utc)
            account.last_sync_status = "success" if success else "error"
            db.session.commit()
        except Exception as e:
            all_ok = False
            logger.error("Error syncing account %s: %s", account.name, e)
            try:
                account.last_sync = datetime.now(timezone.utc)
                account.last_sync_status = "error"
                db.session.commit()
            except Exception:
                db.session.rollback()

    return all_ok


def _process_account_tags(account) -> None:
    try:
        logger.info("Processing tags for account: %s", account.name)
        stats = TagService.process_account_tags(account.id)
        if stats.get("success"):
            logger.info(
                "Account %s tags processed: %s created, %s updated, %s removed",
                account.name,
                stats.get("tags_created", 0),
                stats.get("tags_updated", 0),
                stats.get("tags_removed", 0),
            )
        else:
            logger.warning("Tag processing for %s: %s", account.name, stats.get("error", "Unknown error"))
    except Exception as e:
        logger.error("Error processing tags for account %s: %s", account.name, e)
