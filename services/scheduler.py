"""
Background scheduler for periodic channel synchronization
"""

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

from models import Account, EpgSource, SyncMetadata
from services.scheduler_lock import SchedulerLock
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

# PPV enrichment settings
SYNC_KEY_LAST_PPV_ENRICHMENT = "last_ppv_enrichment"
SYNC_KEY_LAST_PPV_PREFETCH = "last_ppv_prefetch"
DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS = 1  # Run hourly to respect rate limits
DEFAULT_PPV_PREFETCH_INTERVAL_HOURS = 6  # Pre-fetch event data every 6 hours

# Sportsipy team data refresh settings
SYNC_KEY_LAST_SPORTSIPY_REFRESH = "last_sportsipy_refresh"
DEFAULT_SPORTSIPY_REFRESH_INTERVAL_HOURS = 168  # Weekly (7 days)

# Data retention maintenance
SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP = "last_epg_program_cleanup"
SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP = "last_health_check_cleanup"
DEFAULT_EPG_PROGRAM_CLEANUP_INTERVAL_HOURS = 24
DEFAULT_HEALTH_CHECK_CLEANUP_INTERVAL_HOURS = 168
DEFAULT_EPG_PROGRAM_RETENTION_DAYS = 7

# Scheduler heartbeat for multi-worker detection
SYNC_KEY_SCHEDULER_HEARTBEAT = "scheduler_heartbeat"
# Must exceed longest single sync step (EPG fetches use up to 600s timeouts)
SCHEDULER_HEARTBEAT_TIMEOUT_SECONDS = 900


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
        self._lock = SchedulerLock()
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

            from services.epg_sync_orchestrator import source_needs_sync
            from services.epg_sync_progress import EpgSyncProgress

            epg_sources = []
            for source in EpgSource.query.order_by(EpgSource.priority, EpgSource.name).all():
                snap = EpgSyncProgress.snapshot(source)
                snap["due"] = source.enabled and source_needs_sync(source, self._epg_interval_hours)
                epg_sources.append(snap)

            return {
                "running": self.running or self._is_scheduler_alive(),
                "local_running": self.running,
                "lock_held": self._lock.held,
                # Legacy compatibility
                "interval_hours": self.interval_hours,
                "interval_seconds": self.interval_seconds,
                # Detailed sync info
                "syncs": {
                    "accounts": get_sync_info(SYNC_KEY_LAST_ACCOUNT_SYNC, self._account_interval_hours),
                    "epg": get_sync_info(SYNC_KEY_LAST_EPG_SYNC, self._epg_interval_hours),
                    "fcc": get_sync_info(SYNC_KEY_LAST_FCC_SYNC, self._fcc_interval_hours),
                    "ppv_enrichment": get_sync_info(
                        SYNC_KEY_LAST_PPV_ENRICHMENT, DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS
                    ),
                },
                "epg_sources": epg_sources,
            }

    def start(self):
        """Start the scheduler in this worker if the cross-process lock is available."""
        if self.running:
            return

        if not self._lock.try_acquire():
            logger.debug("Scheduler lock held by another worker (pid=%s)", os.getpid())
            return

        self.running = True
        with self.app.app_context():
            self._update_heartbeat()
        self.thread = threading.Thread(target=self._run, daemon=True, name="sync-scheduler")
        self.thread.start()
        logger.info(
            "Sync scheduler started in worker pid=%s (interval: %s hours)",
            os.getpid(),
            self.interval_hours,
        )

    def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self._lock.release()
        with self.app.app_context():
            SyncMetadata.delete(SYNC_KEY_SCHEDULER_HEARTBEAT)
        logger.info("Sync scheduler stopped")

    def _update_heartbeat(self):
        """Update the scheduler heartbeat timestamp"""
        SyncMetadata.set(SYNC_KEY_SCHEDULER_HEARTBEAT, datetime.now(timezone.utc).isoformat())

    def _touch_heartbeat(self):
        """Update heartbeat; log but do not raise on failure."""
        try:
            self._update_heartbeat()
        except Exception as e:
            logger.error("Error updating scheduler heartbeat: %s", e)

    def _is_scheduler_alive(self) -> bool:
        """Check if scheduler is alive based on heartbeat (works across workers)"""
        heartbeat_str = SyncMetadata.get(SYNC_KEY_SCHEDULER_HEARTBEAT)
        if not heartbeat_str:
            return False

        try:
            heartbeat = datetime.fromisoformat(heartbeat_str)
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)

            age_seconds = (datetime.now(timezone.utc) - heartbeat).total_seconds()
            return age_seconds < SCHEDULER_HEARTBEAT_TIMEOUT_SECONDS
        except (ValueError, TypeError):
            return False

    def _get_last_sync_time(self, key: str) -> Optional[datetime]:
        """Get the last sync time from persistent storage"""
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
            # Heartbeat before sync work so long-running jobs do not look dead
            try:
                with self.app.app_context():
                    self._touch_heartbeat()
            except Exception as e:
                logger.error("Error updating scheduler heartbeat before sync: %s", e)

            try:
                self._check_and_sync()
            except Exception as e:
                logger.error(f"Error in sync scheduler: {e}")
                # Ensure we rollback any failed transaction
                try:
                    from models import db

                    with self.app.app_context():
                        db.session.rollback()
                except Exception as rollback_error:
                    # Rollback is best-effort after a scheduler failure; log and continue the loop.
                    logger.warning(
                        "Failed to rollback database session after scheduler error: %s",
                        rollback_error,
                    )

            try:
                with self.app.app_context():
                    self._touch_heartbeat()
            except Exception as e:
                logger.error("Error updating scheduler heartbeat after sync: %s", e)

            # Sleep in small intervals so we can stop quickly
            for _ in range(self._check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def _check_and_sync(self):
        """Check if any syncs are due and run them"""
        with self.app.app_context():
            # Health scans first so long EPG/account sync jobs cannot starve them
            self._scan_channel_health()

            # Check if account/channel sync is needed
            if self._needs_sync(SYNC_KEY_LAST_ACCOUNT_SYNC, self._account_interval_hours):
                logger.info(f"Account sync due (interval: {self._account_interval_hours} hours)")
                self._sync_accounts()
                self._set_last_sync_time(SYNC_KEY_LAST_ACCOUNT_SYNC)
                self._touch_heartbeat()

            self._sync_epg_sources_if_due()

            # Check if FCC sync is needed (configurable, default weekly)
            if self._needs_sync(SYNC_KEY_LAST_FCC_SYNC, self._fcc_interval_hours):
                logger.info(f"FCC sync due (interval: {self._fcc_interval_hours} hours)")
                self._sync_fcc_data()
                self._set_last_sync_time(SYNC_KEY_LAST_FCC_SYNC)
                self._touch_heartbeat()

            # Check if PPV event pre-fetch is needed (every 6 hours)
            # This loads event data for dates found in channels + 30 days ahead
            if self._needs_sync(SYNC_KEY_LAST_PPV_PREFETCH, DEFAULT_PPV_PREFETCH_INTERVAL_HOURS):
                logger.info("PPV event pre-fetch due (6 hour schedule)")
                self._prefetch_ppv_events()
                self._set_last_sync_time(SYNC_KEY_LAST_PPV_PREFETCH)
                self._touch_heartbeat()

            # Check if PPV enrichment is needed (hourly, respects API rate limits)
            if self._needs_sync(SYNC_KEY_LAST_PPV_ENRICHMENT, DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS):
                logger.info("PPV enrichment due (hourly schedule)")
                self._enrich_ppv_events()
                self._set_last_sync_time(SYNC_KEY_LAST_PPV_ENRICHMENT)
                self._touch_heartbeat()

            # Check if sportsipy team data refresh is needed (weekly)
            if self._needs_sync(SYNC_KEY_LAST_SPORTSIPY_REFRESH, DEFAULT_SPORTSIPY_REFRESH_INTERVAL_HOURS):
                logger.info("Sportsipy team data refresh due (weekly schedule)")
                self._refresh_sportsipy_teams()
                self._set_last_sync_time(SYNC_KEY_LAST_SPORTSIPY_REFRESH)
                self._touch_heartbeat()

            # Expired EPG program cleanup (daily)
            if self._needs_sync(SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP, DEFAULT_EPG_PROGRAM_CLEANUP_INTERVAL_HOURS):
                logger.info("EPG program cleanup due (daily schedule)")
                self._cleanup_epg_programs()
                self._set_last_sync_time(SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP)
                self._touch_heartbeat()

            # Health check history cleanup (weekly)
            if self._needs_sync(SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP, DEFAULT_HEALTH_CHECK_CLEANUP_INTERVAL_HOURS):
                logger.info("Health check history cleanup due (weekly schedule)")
                self._cleanup_health_checks()
                self._set_last_sync_time(SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP)
                self._touch_heartbeat()

            self._touch_heartbeat()

    def _sync_accounts(self):
        """Sync all enabled accounts and process their tags"""
        from models import db

        accounts = Account.query.filter_by(enabled=True).all()
        logger.info(f"Syncing {len(accounts)} enabled account(s)")

        for account in accounts:
            try:
                self._touch_heartbeat()
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
        """Run one channel health scan pass for all enabled accounts."""
        try:
            from services.channel_health_service import ChannelHealthService

            ChannelHealthService.run_scheduled_scan_pass()
        except Exception as e:
            logger.error("Error in channel health scanning: %s", e)

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

    def _sync_epg_sources_if_due(self):
        """Sync enabled EPG sources that are past their interval (parallel, per-source progress)."""
        try:
            from services.epg_sync_orchestrator import EpgSyncOrchestrator, source_needs_sync

            due = [
                s
                for s in EpgSource.query.filter_by(enabled=True).all()
                if source_needs_sync(s, self._epg_interval_hours)
            ]
            if not due:
                return

            logger.info("EPG sync: %s source(s) due (interval %sh)", len(due), self._epg_interval_hours)
            self._touch_heartbeat()
            result = EpgSyncOrchestrator(self.app).sync_sources(due, parallel=True)
            self._touch_heartbeat()
            logger.info(
                "EPG sync pass complete: %s/%s succeeded",
                result.get("sources_synced", 0),
                result.get("total_sources", 0),
            )
        except Exception as e:
            logger.error("Error in EPG source sync: %s", e)

    def _prefetch_ppv_events(self):
        """
        Pre-fetch event data for PPV matching.

        Runs every 6 hours. Extracts dates from PPV channel names and
        fetches event data for those dates plus 30 days ahead.
        This ensures event data is available before matching is attempted.
        """
        try:
            from services.jobs.ppv_enrichment import run_ppv_prefetch

            logger.info("Starting PPV event data pre-fetch")

            stats = run_ppv_prefetch(self.app)

            logger.info(
                f"PPV pre-fetch complete: "
                f"{stats.get('total_dates', 0)} dates checked, "
                f"{stats.get('newly_fetched', 0)} newly fetched, "
                f"{stats.get('already_cached', 0)} already cached, "
                f"{stats.get('total_events', 0)} total events"
            )

        except Exception as e:
            logger.error(f"Error pre-fetching PPV events: {e}", exc_info=True)

    def _enrich_ppv_events(self):
        """
        Enrich PPV events using calendar-based scraping.

        Runs hourly. Uses calendar scraping for bulk event discovery
        (no API rate limits), then fetches event details via API.
        """
        try:
            from services.jobs.ppv_enrichment import run_ppv_enrichment

            logger.info("Starting PPV calendar-based enrichment")

            total_stats = run_ppv_enrichment(self.app)

            if total_stats.get("skipped"):
                return

            logger.info(
                "PPV enrichment complete: %s processed, %s matched, %s no_match",
                total_stats.get("channels_processed", 0),
                total_stats.get("channels_matched", 0),
                total_stats.get("channels_no_match", 0),
            )

        except Exception as e:
            logger.error(f"Error enriching PPV events: {e}", exc_info=True)

    def _refresh_sportsipy_teams(self):
        """
        Refresh sports team data from sportsipy.

        Runs weekly. Updates team names and abbreviations in the database
        for use in PPV channel matching. Includes delays to avoid
        Sports Reference rate limiting.
        """
        try:
            from services.sportsipy_service import (
                get_sportsipy_service,
                refresh_teams_from_sportsipy,
                seed_initial_team_data,
            )

            logger.info("Starting sportsipy team data refresh")

            # Seed initial data if empty
            seed_result = seed_initial_team_data()
            if seed_result.get("teams_added", 0) > 0:
                logger.info(f"Seeded {seed_result['teams_added']} initial teams")

            # Refresh from sportsipy with rate limiting delays
            result = refresh_teams_from_sportsipy(
                sports=["fb", "mlb", "nba", "ncaab", "ncaaf", "nfl", "nhl"],
                delay_seconds=3.0,  # 3 second delay between sports
            )

            if result.get("success"):
                logger.info(
                    f"Sportsipy refresh complete: "
                    f"{result.get('teams_added', 0)} added, "
                    f"{result.get('teams_updated', 0)} updated, "
                    f"sports: {result.get('sports_processed', [])}"
                )

                # Reload team data in service
                service = get_sportsipy_service()
                service.reload_team_data()
            else:
                logger.warning(f"Sportsipy refresh had issues: {result.get('errors', [])}")

        except Exception as e:
            logger.error(f"Error refreshing sportsipy teams: {e}", exc_info=True)

    def _cleanup_epg_programs(self):
        """Remove expired rows from epg_programs."""
        try:
            from services.epg.programs import cleanup_expired_programs

            deleted = cleanup_expired_programs(days_old=DEFAULT_EPG_PROGRAM_RETENTION_DAYS)
            logger.info("EPG program cleanup removed %s row(s)", deleted)
        except Exception as e:
            logger.error("Error during EPG program cleanup: %s", e, exc_info=True)

    def _cleanup_health_checks(self):
        """Remove old channel_health_checks rows."""
        try:
            from services.channel_health_service import cleanup_old_health_checks

            deleted = cleanup_old_health_checks()
            logger.info("Health check cleanup removed %s row(s)", deleted)
        except Exception as e:
            logger.error("Error during health check cleanup: %s", e, exc_info=True)
