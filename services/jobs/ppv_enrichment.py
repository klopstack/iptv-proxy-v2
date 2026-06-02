"""Scheduled PPV enrichment job."""

import logging
from typing import Any, Dict

from flask import Flask

logger = logging.getLogger(__name__)


def _merge_enrichment_stats(total: Dict[str, Any], batch: Dict[str, Any]) -> None:
    for key in ("accounts_processed", "channels_processed", "channels_matched", "channels_no_match", "errors"):
        total[key] = total.get(key, 0) + batch.get(key, 0)


def run_ppv_enrichment(app: Flask) -> Dict[str, Any]:
    from services.ppv.constants import PPV_ENRICHMENT_MAX_BATCHES_PER_RUN
    from services.ppv.enrichment import get_calendar_enrichment_service
    from services.ppv.orchestrator import get_ppv_orchestrator

    orchestrator = get_ppv_orchestrator(app)
    total_stats: Dict[str, Any] = {
        "accounts_processed": 0,
        "channels_processed": 0,
        "channels_matched": 0,
        "channels_no_match": 0,
        "errors": 0,
        "batches_run": 0,
    }

    max_batches = PPV_ENRICHMENT_MAX_BATCHES_PER_RUN
    batch_limit = max_batches if max_batches > 0 else None

    while batch_limit is None or total_stats["batches_run"] < batch_limit:
        stats = orchestrator.enrich_pending_channels()
        if stats.get("skipped"):
            return stats if total_stats["batches_run"] == 0 else total_stats

        total_stats["batches_run"] += 1
        _merge_enrichment_stats(total_stats, stats)

        processed = stats.get("channels_processed", 0)
        remaining = orchestrator.get_queue_stats().get("queued_count", 0)
        logger.info(
            "PPV enrichment batch %s: processed=%s matched=%s no_match=%s remaining=%s",
            total_stats["batches_run"],
            processed,
            stats.get("channels_matched", 0),
            stats.get("channels_no_match", 0),
            remaining,
        )

        if processed == 0 or remaining == 0:
            break

    if total_stats["channels_matched"] > 0:
        get_calendar_enrichment_service(app).start_detail_fetcher()
    if total_stats["channels_no_match"] > 0:
        orchestrator.run_enhanced_fallback()

    return total_stats


def run_ppv_prefetch(app: Flask) -> Dict[str, Any]:
    from services.ppv.orchestrator import get_ppv_orchestrator

    return get_ppv_orchestrator(app).prefetch_calendars(days_ahead=30, days_back=7)
