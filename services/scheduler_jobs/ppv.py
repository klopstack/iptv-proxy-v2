"""PPV prefetch, enrichment, and near-term time refresh jobs."""

import logging
from typing import Any, Dict

from flask import Flask

logger = logging.getLogger(__name__)


def run_ppv_prefetch_job(app: Flask) -> bool:
    try:
        from services.jobs.ppv_enrichment import run_ppv_prefetch

        logger.info("Starting PPV event data pre-fetch")
        stats = run_ppv_prefetch(app)
        logger.info(
            "PPV pre-fetch complete: %s dates checked, %s newly fetched, %s cached, %s events",
            stats.get("total_dates", 0),
            stats.get("newly_fetched", 0),
            stats.get("already_cached", 0),
            stats.get("total_events", 0),
        )
        return True
    except Exception:
        logger.error("Error pre-fetching PPV events", exc_info=True)
        return False


def run_ppv_enrichment_job(app: Flask) -> bool:
    try:
        from services.jobs.ppv_enrichment import run_ppv_enrichment

        logger.info("Starting PPV calendar-based enrichment")
        total_stats = run_ppv_enrichment(app)
        if total_stats.get("skipped"):
            return True
        logger.info(
            "PPV enrichment complete: %s batches, %s processed, %s matched, %s no_match",
            total_stats.get("batches_run", 1),
            total_stats.get("channels_processed", 0),
            total_stats.get("channels_matched", 0),
            total_stats.get("channels_no_match", 0),
        )
        return True
    except Exception:
        logger.error("Error enriching PPV events", exc_info=True)
        return False


def ppv_enrichment_log_context(app: Flask) -> Dict[str, Any]:
    try:
        from services.ppv.orchestrator import get_ppv_orchestrator

        return get_ppv_orchestrator(app).get_queue_stats()
    except Exception:
        return {}


def run_ppv_time_refresh_job(app: Flask) -> bool:
    try:
        from services.ppv.enrichment import get_calendar_enrichment_service

        logger.info("Starting PPV near-term event time refresh")
        service = get_calendar_enrichment_service(app)
        stats = service.refresh_upcoming_event_times()
        logger.info("PPV time refresh queued %s events", stats.get("queued", 0))
        return True
    except Exception:
        logger.error("Error refreshing PPV event times", exc_info=True)
        return False
