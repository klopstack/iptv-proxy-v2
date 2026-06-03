"""Background scheduler for periodic channel synchronization."""

import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional, Union

from models import EpgSource, SyncMetadata
from services.datetime_utils import serialize_utc_iso
from services.epg_sync_orchestrator import SYNC_KEY_LAST_EPG_SYNC
from services.scheduler_constants import (
    DEFAULT_ACCOUNT_INTERVAL_HOURS,
    DEFAULT_EPG_INTERVAL_HOURS,
    DEFAULT_EPG_PROGRAM_CLEANUP_INTERVAL_HOURS,
    DEFAULT_FCC_INTERVAL_HOURS,
    DEFAULT_HEALTH_CHECK_CLEANUP_INTERVAL_HOURS,
    DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS,
    DEFAULT_PPV_PREFETCH_INTERVAL_HOURS,
    DEFAULT_PPV_TIME_REFRESH_INTERVAL_HOURS,
    DEFAULT_SPORTSIPY_REFRESH_INTERVAL_HOURS,
    SCHEDULER_HEARTBEAT_TIMEOUT_SECONDS,
    SYNC_KEY_ACCOUNT_INTERVAL,
    SYNC_KEY_EPG_INTERVAL,
    SYNC_KEY_FCC_INTERVAL,
    SYNC_KEY_LAST_ACCOUNT_SYNC,
    SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP,
    SYNC_KEY_LAST_FCC_SYNC,
    SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP,
    SYNC_KEY_LAST_PPV_ENRICHMENT,
    SYNC_KEY_LAST_PPV_PREFETCH,
    SYNC_KEY_LAST_PPV_TIME_REFRESH,
    SYNC_KEY_LAST_SPORTSIPY_REFRESH,
    SYNC_KEY_SCHEDULER_HEARTBEAT,
)
from services.scheduler_jobs import accounts as accounts_job
from services.scheduler_jobs import cleanup as cleanup_job
from services.scheduler_jobs import epg as epg_job
from services.scheduler_jobs import fcc as fcc_job
from services.scheduler_jobs import health as health_job
from services.scheduler_jobs import ppv as ppv_job
from services.scheduler_jobs import sportsipy as sportsipy_job
from services.scheduler_lock import SchedulerLock
from services.scheduler_registry import JobDefinition, build_scheduled_jobs
from services.scheduler_sync_metadata import (
    default_failure_message,
    failure_at_key,
    failure_error_key,
    get_last_sync_time,
    get_sync_failure_fields,
    needs_sync,
    record_sync_failure,
    record_sync_success,
    resolve_last_run_status,
    set_last_sync_time,
)

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Scheduler for periodic channel sync with persistent timing and separate intervals."""

    def __init__(self, app, interval_hours=DEFAULT_ACCOUNT_INTERVAL_HOURS):
        self.app = app
        self.interval_hours = interval_hours
        self.interval_seconds = interval_hours * 3600
        self.running = False
        self.thread = None
        self._lock = SchedulerLock()
        self._check_interval = 60
        with self.app.app_context():
            self._account_interval_hours = self._load_interval(SYNC_KEY_ACCOUNT_INTERVAL, interval_hours)
            self._epg_interval_hours = self._load_interval(SYNC_KEY_EPG_INTERVAL, DEFAULT_EPG_INTERVAL_HOURS)
            self._fcc_interval_hours = self._load_interval(SYNC_KEY_FCC_INTERVAL, DEFAULT_FCC_INTERVAL_HOURS)

    def _load_interval(self, key: str, default: int) -> int:
        try:
            value = SyncMetadata.get(key)
            if value:
                try:
                    return int(value)
                except (ValueError, TypeError):
                    pass
        except Exception:
            pass
        return default

    def _save_interval(self, key: str, value: int):
        SyncMetadata.set(key, str(value))

    @property
    def account_interval_hours(self) -> int:
        return self._account_interval_hours

    @account_interval_hours.setter
    def account_interval_hours(self, value: int):
        self._account_interval_hours = value
        self._save_interval(SYNC_KEY_ACCOUNT_INTERVAL, value)
        self.interval_hours = value
        self.interval_seconds = value * 3600

    @property
    def epg_interval_hours(self) -> int:
        return self._epg_interval_hours

    @epg_interval_hours.setter
    def epg_interval_hours(self, value: int):
        self._epg_interval_hours = value
        self._save_interval(SYNC_KEY_EPG_INTERVAL, value)

    @property
    def fcc_interval_hours(self) -> int:
        return self._fcc_interval_hours

    @fcc_interval_hours.setter
    def fcc_interval_hours(self, value: int):
        self._fcc_interval_hours = value
        self._save_interval(SYNC_KEY_FCC_INTERVAL, value)

    def get_status(self) -> dict:
        with self.app.app_context():
            now = datetime.now(timezone.utc)

            def get_sync_info(key: str, interval_hours: int) -> dict:
                last_sync = self._get_last_sync_time(key)
                if last_sync:
                    if last_sync.tzinfo is None:
                        last_sync = last_sync.replace(tzinfo=timezone.utc)
                    next_sync = last_sync + timedelta(hours=interval_hours)
                    overdue = now >= next_sync
                else:
                    next_sync = None
                    overdue = True
                failure = self._get_sync_failure_fields(key)
                return {
                    "interval_hours": interval_hours,
                    "last_sync": serialize_utc_iso(last_sync),
                    "last_success_at": serialize_utc_iso(last_sync),
                    "next_sync": serialize_utc_iso(next_sync),
                    "overdue": overdue,
                    "last_failure_at": failure["last_failure_at"],
                    "last_error": failure["last_error"],
                    "last_run_status": self._resolve_last_run_status(last_sync, failure["last_error"]),
                }

            from services.epg_sync_orchestrator import source_needs_sync
            from services.epg_sync_progress import EpgSyncProgress

            epg_sources = []
            for source in EpgSource.query.order_by(EpgSource.priority, EpgSource.name).all():
                snap = EpgSyncProgress.snapshot(source)
                snap["due"] = source.enabled and source_needs_sync(source, self._epg_interval_hours)
                epg_sources.append(snap)

            syncs = {
                "accounts": (SYNC_KEY_LAST_ACCOUNT_SYNC, self._account_interval_hours),
                "epg": (SYNC_KEY_LAST_EPG_SYNC, self._epg_interval_hours),
                "fcc": (SYNC_KEY_LAST_FCC_SYNC, self._fcc_interval_hours),
                "ppv_prefetch": (SYNC_KEY_LAST_PPV_PREFETCH, DEFAULT_PPV_PREFETCH_INTERVAL_HOURS),
                "ppv_enrichment": (SYNC_KEY_LAST_PPV_ENRICHMENT, DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS),
                "ppv_time_refresh": (SYNC_KEY_LAST_PPV_TIME_REFRESH, DEFAULT_PPV_TIME_REFRESH_INTERVAL_HOURS),
                "sportsipy_refresh": (SYNC_KEY_LAST_SPORTSIPY_REFRESH, DEFAULT_SPORTSIPY_REFRESH_INTERVAL_HOURS),
                "epg_program_cleanup": (SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP, DEFAULT_EPG_PROGRAM_CLEANUP_INTERVAL_HOURS),
                "health_check_cleanup": (
                    SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP,
                    DEFAULT_HEALTH_CHECK_CLEANUP_INTERVAL_HOURS,
                ),
            }
            return {
                "running": self.running or self._is_scheduler_alive(),
                "local_running": self.running,
                "lock_held": self._lock.held,
                "syncs": {name: get_sync_info(key, hours) for name, (key, hours) in syncs.items()},
                "epg_sources": epg_sources,
            }

    def start(self):
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
        logger.info("Sync scheduler started in worker pid=%s (interval: %s hours)", os.getpid(), self.interval_hours)

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        self._lock.release()
        with self.app.app_context():
            SyncMetadata.delete(SYNC_KEY_SCHEDULER_HEARTBEAT)
        logger.info("Sync scheduler stopped")

    def _update_heartbeat(self):
        SyncMetadata.set(SYNC_KEY_SCHEDULER_HEARTBEAT, serialize_utc_iso(datetime.now(timezone.utc)))

    def _touch_heartbeat(self):
        try:
            self._update_heartbeat()
        except Exception as e:
            logger.error("Error updating scheduler heartbeat: %s", e)

    def _is_scheduler_alive(self) -> bool:
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
        return get_last_sync_time(key)

    def _set_last_sync_time(self, key: str, when: Optional[datetime] = None):
        set_last_sync_time(key, when)

    @staticmethod
    def _failure_at_key(last_sync_key: str) -> str:
        return failure_at_key(last_sync_key)

    @staticmethod
    def _failure_error_key(last_sync_key: str) -> str:
        return failure_error_key(last_sync_key)

    def _record_sync_failure(self, last_sync_key: str, error: str) -> None:
        record_sync_failure(last_sync_key, error)

    def _record_sync_success(self, last_sync_key: str) -> None:
        record_sync_success(last_sync_key)

    def _get_sync_failure_fields(self, last_sync_key: str) -> dict:
        return get_sync_failure_fields(last_sync_key)

    @staticmethod
    def _resolve_last_run_status(last_success: Optional[datetime], last_error: Optional[str]) -> str:
        return resolve_last_run_status(last_success, last_error)

    def _default_failure_message(self, last_sync_key: str) -> str:
        return default_failure_message(last_sync_key)

    def _needs_sync(self, key: str, interval_hours: int) -> bool:
        return needs_sync(key, interval_hours)

    def _resolve_interval_hours(self, interval_hours: Union[int, Callable[["SyncScheduler"], int]]) -> int:
        return interval_hours(self) if callable(interval_hours) else interval_hours

    def _resolve_log_message(
        self, log_message: Optional[Union[str, Callable[["SyncScheduler"], str]]]
    ) -> Optional[str]:
        if log_message is None:
            return None
        return log_message(self) if callable(log_message) else log_message

    def _run_scheduled_job(
        self, last_sync_key: str, interval_hours: int, job_fn, *, log_message: Optional[str] = None
    ) -> None:
        if not self._needs_sync(last_sync_key, interval_hours):
            return
        if log_message:
            logger.info(log_message)
        try:
            success = job_fn()
        except Exception as exc:
            logger.error("Scheduled job %s failed: %s", last_sync_key, exc)
            self._record_sync_failure(last_sync_key, str(exc))
            return
        if success:
            self._set_last_sync_time(last_sync_key)
            self._record_sync_success(last_sync_key)
            self._touch_heartbeat()
        else:
            self._record_sync_failure(last_sync_key, self._default_failure_message(last_sync_key))

    def _run_scheduled_job_def(self, job: JobDefinition) -> None:
        self._run_scheduled_job(
            job.last_sync_key,
            self._resolve_interval_hours(job.interval_hours),
            lambda: job.run(self),
            log_message=self._resolve_log_message(job.log_message),
        )

    def _run(self):
        for _ in range(30):
            if not self.running:
                return
            time.sleep(1)
        while self.running:
            try:
                with self.app.app_context():
                    self._touch_heartbeat()
            except Exception as e:
                logger.error("Error updating scheduler heartbeat before sync: %s", e)
            try:
                self._check_and_sync()
            except Exception as e:
                logger.error("Error in sync scheduler: %s", e)
                try:
                    from models import db

                    with self.app.app_context():
                        db.session.rollback()
                except Exception as rollback_error:
                    logger.warning("Failed to rollback after scheduler error: %s", rollback_error)
            try:
                with self.app.app_context():
                    self._touch_heartbeat()
            except Exception as e:
                logger.error("Error updating scheduler heartbeat after sync: %s", e)
            for _ in range(self._check_interval):
                if not self.running:
                    break
                time.sleep(1)

    def _check_and_sync(self):
        with self.app.app_context():
            self._scan_channel_health()
            for job in build_scheduled_jobs():
                self._run_scheduled_job_def(job)
                if job.status_key == "accounts":
                    self._sync_epg_sources_if_due()
            self._touch_heartbeat()

    def _sync_accounts(self) -> bool:
        return accounts_job.run_account_sync(touch_heartbeat=self._touch_heartbeat)

    def _scan_channel_health(self):
        health_job.run_channel_health_scan()

    def _sync_fcc_data(self) -> bool:
        return fcc_job.run_fcc_sync()

    def _sync_epg_sources_if_due(self):
        epg_job.run_epg_source_sync(
            self.app,
            self._epg_interval_hours,
            touch_heartbeat=self._touch_heartbeat,
            record_success=self._record_sync_success,
            record_failure=self._record_sync_failure,
        )

    def _prefetch_ppv_events(self) -> bool:
        return ppv_job.run_ppv_prefetch_job(self.app)

    def _enrich_ppv_events(self) -> bool:
        return ppv_job.run_ppv_enrichment_job(self.app)

    def _refresh_ppv_event_times(self) -> bool:
        return ppv_job.run_ppv_time_refresh_job(self.app)

    def _refresh_sportsipy_teams(self) -> bool:
        return sportsipy_job.run_sportsipy_team_refresh()

    def _cleanup_epg_programs(self) -> bool:
        return cleanup_job.run_epg_program_cleanup()

    def _cleanup_health_checks(self) -> bool:
        return cleanup_job.run_health_check_cleanup()
