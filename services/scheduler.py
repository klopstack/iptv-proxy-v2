"""
Background scheduler for periodic channel synchronization
"""

import logging
import threading
import time
from datetime import datetime, timezone

import requests

from models import Account, EpgSource
from services.epg_service import EpgService
from services.iptv_service import IPTVService
from services.sync_service import ChannelSyncService

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Scheduler for periodic channel sync"""

    def __init__(self, app, interval_hours=6):
        """
        Initialize scheduler

        Args:
            app: Flask app instance
            interval_hours: Hours between sync runs (default: 6)
        """
        self.app = app
        self.interval_hours = interval_hours
        self.interval_seconds = interval_hours * 3600
        self.running = False
        self.thread = None

    def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Scheduler already running")
            return

        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        logger.info(f"Sync scheduler started (interval: {self.interval_hours} hours)")

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        logger.info("Sync scheduler stopped")

    def _run(self):
        """Main scheduler loop"""
        # Wait a bit before first sync to let app start up
        time.sleep(60)

        while self.running:
            try:
                self._sync_all()
            except Exception as e:
                logger.error(f"Error in sync scheduler: {e}")

            # Sleep in small intervals so we can stop quickly
            for _ in range(int(self.interval_seconds)):
                if not self.running:
                    break
                time.sleep(1)

    def _sync_all(self):
        """Sync all enabled accounts and EPG sources"""
        with self.app.app_context():
            logger.info(f"Starting scheduled sync at {datetime.now(timezone.utc)}")

            # Sync channels for all enabled accounts
            accounts = Account.query.filter_by(enabled=True).all()
            for account in accounts:
                try:
                    logger.info(f"Syncing account: {account.name}")
                    stats = ChannelSyncService.sync_account(account.id)
                    logger.info(
                        f"Account {account.name} synced: "
                        f"{stats['channels_added']} added, "
                        f"{stats['channels_updated']} updated, "
                        f"{stats['channels_deactivated']} deactivated"
                    )
                except Exception as e:
                    logger.error(f"Error syncing account {account.name}: {e}")

            # Sync all enabled EPG sources
            self._sync_epg_sources()

            logger.info(f"Scheduled sync completed at {datetime.now(timezone.utc)}")

    def _sync_epg_sources(self):
        """Sync all enabled EPG sources"""
        sources = EpgSource.query.filter_by(enabled=True).all()
        logger.info(f"Syncing {len(sources)} EPG source(s)")

        for source in sources:
            try:
                logger.info(f"Syncing EPG source: {source.name} ({source.source_type})")
                stats = self._sync_single_epg_source(source)
                if stats:
                    logger.info(
                        f"EPG source {source.name} synced: "
                        f"{stats.get('channels_added', 0)} added, "
                        f"{stats.get('channels_updated', 0)} updated"
                    )
            except Exception as e:
                logger.error(f"Error syncing EPG source {source.name}: {e}")

    def _sync_single_epg_source(self, source: EpgSource):
        """
        Sync a single EPG source.

        Args:
            source: The EpgSource to sync

        Returns:
            Dict with sync stats or None if sync failed/skipped
        """
        if source.source_type == "provider":
            if not source.account:
                logger.warning(f"EPG source {source.name} has no associated account")
                return None

            account = source.account
            cred = account.get_primary_credential()
            if cred:
                service = IPTVService(
                    account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9"
                )
            else:
                service = IPTVService(
                    account.server, account.username, account.password, account.user_agent or "okhttp/3.14.9"
                )

            xml_content = service.get_xmltv()
            return EpgService.sync_epg_source(source, xml_content)

        elif source.source_type == "xmltv_url":
            if not source.url:
                logger.warning(f"EPG source {source.name} has no URL configured")
                return None

            response = requests.get(source.url, timeout=120)
            response.raise_for_status()
            return EpgService.sync_epg_source(source, response.content)

        elif source.source_type == "schedules_direct":
            # Schedules Direct sync is handled separately via the SD service
            logger.debug(f"Skipping Schedules Direct source {source.name} - handled separately")
            return None

        else:
            logger.warning(f"Unknown EPG source type: {source.source_type}")
            return None
