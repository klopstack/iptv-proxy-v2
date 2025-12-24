"""
Background scheduler for periodic channel synchronization
"""

import logging
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from models import Account, EpgSource, SyncMetadata
from services.epg_service import EpgService, normalize_xmltv_url
from services.iptv_service import IPTVService
from services.sync_service import ChannelSyncService
from services.tag_service import TagService

logger = logging.getLogger(__name__)

# Default sync intervals (in hours)
DEFAULT_ACCOUNT_INTERVAL_HOURS = 6
DEFAULT_EPG_INTERVAL_HOURS = 12
DEFAULT_FCC_INTERVAL_HOURS = 168  # Weekly

# Metadata keys for persistent sync state
SYNC_KEY_LAST_ACCOUNT_SYNC = "last_account_sync"
SYNC_KEY_LAST_EPG_SYNC = "last_epg_sync"
SYNC_KEY_LAST_FCC_SYNC = "last_fcc_sync"

# Metadata keys for interval settings (persisted)
SYNC_KEY_ACCOUNT_INTERVAL = "account_sync_interval_hours"
SYNC_KEY_EPG_INTERVAL = "epg_sync_interval_hours"
SYNC_KEY_FCC_INTERVAL = "fcc_sync_interval_hours"


class SyncScheduler:
    """Scheduler for periodic channel sync with persistent timing and separate intervals"""

    def __init__(self, app, interval_hours=6):
        """
        Initialize scheduler

        Args:
            app: Flask app instance
            interval_hours: Default hours between sync runs (default: 6)
                           This is used as fallback if no specific intervals are set
        """
        self.app = app
        # Legacy compatibility - this will be the account sync interval
        self.interval_hours = interval_hours
        self.interval_seconds = interval_hours * 3600
        self.running = False
        self.thread = None
        # Check every minute for work to do
        self._check_interval = 60

        # Load persisted intervals or use defaults
        with self.app.app_context():
            self._account_interval_hours = self._load_interval(SYNC_KEY_ACCOUNT_INTERVAL, interval_hours)
            self._epg_interval_hours = self._load_interval(SYNC_KEY_EPG_INTERVAL, DEFAULT_EPG_INTERVAL_HOURS)
            self._fcc_interval_hours = self._load_interval(SYNC_KEY_FCC_INTERVAL, DEFAULT_FCC_INTERVAL_HOURS)

    def _load_interval(self, key: str, default: int) -> int:
        """Load an interval setting from persistent storage"""
        try:
            value = SyncMetadata.get(key)
            if value:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
        except Exception:
            # Table might not exist yet (e.g., during testing)
            pass
        return default

    def _save_interval(self, key: str, value: int):
        """Save an interval setting to persistent storage"""
        with self.app.app_context():
            SyncMetadata.set(key, str(value))

    @property
    def account_interval_hours(self) -> int:
        """Get IPTV account sync interval in hours"""
        return self._account_interval_hours

    @account_interval_hours.setter
    def account_interval_hours(self, value: int):
        """Set IPTV account sync interval in hours"""
        self._account_interval_hours = value
        self._save_interval(SYNC_KEY_ACCOUNT_INTERVAL, value)
        # Keep legacy property in sync
        self.interval_hours = value
        self.interval_seconds = value * 3600

    @property
    def epg_interval_hours(self) -> int:
        """Get EPG source sync interval in hours"""
        return self._epg_interval_hours

    @epg_interval_hours.setter
    def epg_interval_hours(self, value: int):
        """Set EPG source sync interval in hours"""
        self._epg_interval_hours = value
        self._save_interval(SYNC_KEY_EPG_INTERVAL, value)

    @property
    def fcc_interval_hours(self) -> int:
        """Get FCC data sync interval in hours"""
        return self._fcc_interval_hours

    @fcc_interval_hours.setter
    def fcc_interval_hours(self, value: int):
        """Set FCC data sync interval in hours"""
        self._fcc_interval_hours = value
        self._save_interval(SYNC_KEY_FCC_INTERVAL, value)

    def get_status(self) -> dict:
        """Get detailed scheduler status including all sync types"""
        with self.app.app_context():
            now = datetime.now(timezone.utc)

            def get_sync_info(key: str, interval_hours: int) -> dict:
                """Get info about a specific sync type"""
                last_sync = self._get_last_sync_time(key)
                if last_sync:
                    # Handle timezone-naive datetimes
                    if last_sync.tzinfo is None:
                        last_sync = last_sync.replace(tzinfo=timezone.utc)
                    next_sync = last_sync + timedelta(hours=interval_hours)
                    overdue = now >= next_sync
                else:
                    next_sync = None
                    overdue = True

                return {
                    "interval_hours": interval_hours,
                    "last_sync": last_sync.isoformat() if last_sync else None,
                    "next_sync": next_sync.isoformat() if next_sync else None,
                    "overdue": overdue,
                }

            return {
                "running": self.running,
                # Legacy compatibility
                "interval_hours": self.interval_hours,
                "interval_seconds": self.interval_seconds,
                # Detailed sync info
                "syncs": {
                    "accounts": get_sync_info(SYNC_KEY_LAST_ACCOUNT_SYNC, self._account_interval_hours),
                    "epg": get_sync_info(SYNC_KEY_LAST_EPG_SYNC, self._epg_interval_hours),
                    "fcc": get_sync_info(SYNC_KEY_LAST_FCC_SYNC, self._fcc_interval_hours),
                },
            }

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

    def _get_last_sync_time(self, key: str) -> Optional[datetime]:
        """Get the last sync time from persistent storage"""
        with self.app.app_context():
            value = SyncMetadata.get(key)
            if value:
                try:
                    return datetime.fromisoformat(value)
                except (ValueError, TypeError):
                    return None
            return None

    def _set_last_sync_time(self, key: str, when: Optional[datetime] = None):
        """Set the last sync time in persistent storage"""
        if when is None:
            when = datetime.now(timezone.utc)
        with self.app.app_context():
            SyncMetadata.set(key, when.isoformat())

    def _needs_sync(self, key: str, interval_hours: int) -> bool:
        """Check if a sync is needed based on last sync time"""
        last_sync = self._get_last_sync_time(key)
        if last_sync is None:
            return True

        # Handle timezone-naive datetimes
        if last_sync.tzinfo is None:
            last_sync = last_sync.replace(tzinfo=timezone.utc)

        next_sync = last_sync + timedelta(hours=interval_hours)
        return datetime.now(timezone.utc) >= next_sync

    def _run(self):
        """Main scheduler loop - checks periodically if sync is needed"""
        # Wait a bit before first check to let app start up
        time.sleep(30)

        while self.running:
            try:
                self._check_and_sync()
            except Exception as e:
                logger.error(f"Error in sync scheduler: {e}")
                # Ensure we rollback any failed transaction
                try:
                    from models import db

                    with self.app.app_context():
                        db.session.rollback()
                except Exception:
                    pass

            # Sleep in small intervals so we can stop quickly
            for _ in range(self._check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def _check_and_sync(self):
        """Check if any syncs are due and run them"""
        with self.app.app_context():
            # Check if account/channel sync is needed
            if self._needs_sync(SYNC_KEY_LAST_ACCOUNT_SYNC, self._account_interval_hours):
                logger.info(f"Account sync due (interval: {self._account_interval_hours} hours)")
                self._sync_accounts()
                self._set_last_sync_time(SYNC_KEY_LAST_ACCOUNT_SYNC)

            # Check if EPG sync is needed (uses its own interval)
            if self._needs_sync(SYNC_KEY_LAST_EPG_SYNC, self._epg_interval_hours):
                logger.info(f"EPG sync due (interval: {self._epg_interval_hours} hours)")
                self._sync_epg_sources()
                self._set_last_sync_time(SYNC_KEY_LAST_EPG_SYNC)

            # Check if FCC sync is needed (configurable, default weekly)
            if self._needs_sync(SYNC_KEY_LAST_FCC_SYNC, self._fcc_interval_hours):
                logger.info(f"FCC sync due (interval: {self._fcc_interval_hours} hours)")
                self._sync_fcc_data()
                self._set_last_sync_time(SYNC_KEY_LAST_FCC_SYNC)

            # Run channel health scanning (runs continuously when idle)
            self._scan_channel_health()

    def _sync_accounts(self):
        """Sync all enabled accounts and process their tags"""
        from models import db

        accounts = Account.query.filter_by(enabled=True).all()
        logger.info(f"Syncing {len(accounts)} enabled account(s)")

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

                # Process tag extraction for this account
                self._process_account_tags(account)

                # Update account's last sync time
                account.last_sync = datetime.now(timezone.utc)
                account.last_sync_status = "success"
                db.session.commit()

            except Exception as e:
                logger.error(f"Error syncing account {account.name}: {e}")
                # Update account's sync status to error
                try:
                    account.last_sync = datetime.now(timezone.utc)
                    account.last_sync_status = "error"
                    db.session.commit()
                except Exception:
                    db.session.rollback()

    def _process_account_tags(self, account):
        """Process tag extraction for an account after channel sync"""
        try:
            logger.info(f"Processing tags for account: {account.name}")
            stats = TagService.process_account_tags(account.id)
            if stats.get("success"):
                logger.info(
                    f"Account {account.name} tags processed: "
                    f"{stats.get('tags_created', 0)} created, "
                    f"{stats.get('tags_updated', 0)} updated, "
                    f"{stats.get('tags_removed', 0)} removed"
                )
            else:
                logger.warning(f"Tag processing for {account.name}: {stats.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error processing tags for account {account.name}: {e}")

    def _scan_channel_health(self):
        """
        Scan channel health for all enabled accounts.

        This runs continuously when idle, checking channels for:
        - Connection failures
        - Black screens
        - Invalid streams

        Respects connection limits and reserves connections for client requests.
        """
        try:
            from models import ChannelHealthConfig
            from services.channel_health_service import ChannelHealthService

            # Check if scanning is enabled
            if not ChannelHealthConfig.get_bool("scanning_enabled", False):
                return

            # Get all enabled accounts
            accounts = Account.query.filter_by(enabled=True).all()

            for account in accounts:
                try:
                    # Check available connections
                    available = ChannelHealthService.get_available_scan_connections(account.id)
                    if available <= 0:
                        logger.debug(f"No connections available for health scanning account {account.name}")
                        continue

                    # Scan a batch of channels
                    result = ChannelHealthService.scan_channels(account.id, max_channels=5)

                    if result.get("scanned", 0) > 0:
                        logger.info(
                            f"Health scan for {account.name}: "
                            f"{result.get('scanned', 0)} scanned, "
                            f"{result.get('healthy', 0)} healthy, "
                            f"{result.get('failed', 0)} failed"
                        )

                except Exception as e:
                    logger.error(f"Error scanning health for account {account.name}: {e}")

        except Exception as e:
            logger.error(f"Error in channel health scanning: {e}")

    def _sync_fcc_data(self):
        """Sync FCC facility data (runs weekly)"""
        try:
            from services.fcc_facility_service import FccFacilityService

            logger.info("Starting weekly FCC facility data sync")
            result = FccFacilityService.full_sync()
            if result.get("success"):
                stats = result.get("stats", {})
                logger.info(
                    f"FCC data synced: {stats.get('added', 0)} added, "
                    f"{stats.get('updated', 0)} updated, {stats.get('total', 0)} total"
                )
            else:
                logger.warning(f"FCC sync issue: {result.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"Error syncing FCC data: {e}")

    def _apply_fcc_enrichment(self, account):
        """Apply FCC-based tag enrichment to an account"""
        try:
            from services.fcc_facility_service import FccFacilityService

            logger.info(f"Applying FCC enrichment for account: {account.name}")
            options = {
                "add_location_tags": True,
                "add_network_tags": True,
                "add_callsign_tags": True,
            }
            result = FccFacilityService.apply_channel_enrichment(account.id, options)
            if result.get("success"):
                logger.info(
                    f"FCC enrichment for {account.name}: "
                    f"{result.get('channels_enriched', 0)} channels enriched, "
                    f"{result.get('tags_added', 0)} tags added"
                )
            else:
                logger.warning(f"FCC enrichment issue for {account.name}: {result.get('error', 'Unknown')}")
        except Exception as e:
            logger.error(f"Error applying FCC enrichment for account {account.name}: {e}")

    def _sync_epg_sources(self):
        """Sync all enabled EPG sources"""
        from services.epg_service import update_ppv_channel_visibility

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

                    # Update PPV visibility for provider sources
                    if source.source_type == "provider" and source.account:
                        try:
                            ppv_stats = update_ppv_channel_visibility(source.account.id)
                            logger.info(
                                f"PPV visibility updated for {source.account.name}: "
                                f"{ppv_stats['events_detected']} events detected, "
                                f"{ppv_stats['channels_shown']} shown, "
                                f"{ppv_stats['channels_hidden']} hidden"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update PPV visibility: {e}")

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

            # Normalize URL (e.g., convert GitHub blob URLs to raw URLs)
            url = normalize_xmltv_url(source.url)
            if url != source.url:
                logger.info(f"Normalized XMLTV URL: {source.url} -> {url}")

            # Use 10 minute timeout for large XMLTV files from rate-limited servers
            response = requests.get(url, timeout=600)
            response.raise_for_status()
            return EpgService.sync_epg_source(source, response.content)

        elif source.source_type == "schedules_direct":
            # Schedules Direct sync is handled separately via the SD service
            logger.debug(f"Skipping Schedules Direct source {source.name} - handled separately")
            return None

        else:
            logger.warning(f"Unknown EPG source type: {source.source_type}")
            return None
