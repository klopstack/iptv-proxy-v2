"""Declarative registry of interval-gated SyncScheduler jobs."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional, Union

from services.epg_sync_orchestrator import SYNC_KEY_LAST_EPG_SYNC
from services.scheduler_constants import (
    DEFAULT_EPG_PROGRAM_CLEANUP_INTERVAL_HOURS,
    DEFAULT_HEALTH_CHECK_CLEANUP_INTERVAL_HOURS,
    DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS,
    DEFAULT_PPV_PREFETCH_INTERVAL_HOURS,
    DEFAULT_PPV_TIME_REFRESH_INTERVAL_HOURS,
    DEFAULT_SPORTSIPY_REFRESH_INTERVAL_HOURS,
    SYNC_KEY_LAST_ACCOUNT_SYNC,
    SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP,
    SYNC_KEY_LAST_FCC_SYNC,
    SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP,
    SYNC_KEY_LAST_PPV_ENRICHMENT,
    SYNC_KEY_LAST_PPV_PREFETCH,
    SYNC_KEY_LAST_PPV_TIME_REFRESH,
    SYNC_KEY_LAST_SPORTSIPY_REFRESH,
)
from services.scheduler_jobs.ppv import ppv_enrichment_log_context

if TYPE_CHECKING:
    from services.scheduler import SyncScheduler

IntervalResolver = Callable[["SyncScheduler"], int]
LogMessageResolver = Union[str, Callable[["SyncScheduler"], str]]
JobRunner = Callable[["SyncScheduler"], bool]


@dataclass(frozen=True)
class JobDefinition:
    last_sync_key: str
    status_key: str
    interval_hours: Union[int, IntervalResolver]
    run: JobRunner
    log_message: Optional[LogMessageResolver] = None
    advance_timestamp_on_success: bool = True


def _account_interval(scheduler: "SyncScheduler") -> int:
    return scheduler._account_interval_hours


def _fcc_interval(scheduler: "SyncScheduler") -> int:
    return scheduler._fcc_interval_hours


def _account_log(scheduler: "SyncScheduler") -> str:
    return f"Account sync due (interval: {scheduler._account_interval_hours} hours)"


def _fcc_log(scheduler: "SyncScheduler") -> str:
    return f"FCC sync due (interval: {scheduler._fcc_interval_hours} hours)"


def _ppv_enrichment_log(scheduler: "SyncScheduler") -> str:
    queue = ppv_enrichment_log_context(scheduler.app)
    return (
        f"PPV enrichment due (interval: {int(DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS * 60)} min, "
        f"backlog: {queue.get('queued_count', '?')})"
    )


def _run_accounts(scheduler: "SyncScheduler") -> bool:
    return scheduler._sync_accounts()


def _run_fcc(scheduler: "SyncScheduler") -> bool:
    return scheduler._sync_fcc_data()


def _run_ppv_prefetch(scheduler: "SyncScheduler") -> bool:
    return scheduler._prefetch_ppv_events()


def _run_ppv_enrichment(scheduler: "SyncScheduler") -> bool:
    return scheduler._enrich_ppv_events()


def _run_ppv_time_refresh(scheduler: "SyncScheduler") -> bool:
    return scheduler._refresh_ppv_event_times()


def _run_sportsipy(scheduler: "SyncScheduler") -> bool:
    return scheduler._refresh_sportsipy_teams()


def _run_epg_cleanup(scheduler: "SyncScheduler") -> bool:
    return scheduler._cleanup_epg_programs()


def _run_health_cleanup(scheduler: "SyncScheduler") -> bool:
    return scheduler._cleanup_health_checks()


def build_scheduled_jobs() -> tuple[JobDefinition, ...]:
    return (
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_ACCOUNT_SYNC,
            status_key="accounts",
            interval_hours=_account_interval,
            run=_run_accounts,
            log_message=_account_log,
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_FCC_SYNC,
            status_key="fcc",
            interval_hours=_fcc_interval,
            run=_run_fcc,
            log_message=_fcc_log,
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_PPV_PREFETCH,
            status_key="ppv_prefetch",
            interval_hours=DEFAULT_PPV_PREFETCH_INTERVAL_HOURS,
            run=_run_ppv_prefetch,
            log_message="PPV event pre-fetch due (6 hour schedule)",
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_PPV_ENRICHMENT,
            status_key="ppv_enrichment",
            interval_hours=DEFAULT_PPV_ENRICHMENT_INTERVAL_HOURS,
            run=_run_ppv_enrichment,
            log_message=_ppv_enrichment_log,
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_PPV_TIME_REFRESH,
            status_key="ppv_time_refresh",
            interval_hours=DEFAULT_PPV_TIME_REFRESH_INTERVAL_HOURS,
            run=_run_ppv_time_refresh,
            log_message="PPV near-term event time refresh due (hourly schedule)",
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_SPORTSIPY_REFRESH,
            status_key="sportsipy_refresh",
            interval_hours=DEFAULT_SPORTSIPY_REFRESH_INTERVAL_HOURS,
            run=_run_sportsipy,
            log_message="Sportsipy team data refresh due (weekly schedule)",
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_EPG_PROGRAM_CLEANUP,
            status_key="epg_program_cleanup",
            interval_hours=DEFAULT_EPG_PROGRAM_CLEANUP_INTERVAL_HOURS,
            run=_run_epg_cleanup,
            log_message="EPG program cleanup due (daily schedule)",
        ),
        JobDefinition(
            last_sync_key=SYNC_KEY_LAST_HEALTH_CHECK_CLEANUP,
            status_key="health_check_cleanup",
            interval_hours=DEFAULT_HEALTH_CHECK_CLEANUP_INTERVAL_HOURS,
            run=_run_health_cleanup,
            log_message="Health check history cleanup due (weekly schedule)",
        ),
    )


EPG_STATUS_JOB = ("epg", SYNC_KEY_LAST_EPG_SYNC)
