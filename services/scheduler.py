"""
Background scheduler for periodic channel synchronization
"""

import logging
import threading
import time
from datetime import datetime

from models import Account, db
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
        """Sync all enabled accounts"""
        with self.app.app_context():
            logger.info(f"Starting scheduled sync at {datetime.utcnow()}")

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

            logger.info(f"Scheduled sync completed at {datetime.utcnow()}")
