"""Scheduled PPV enrichment job."""

import logging
from typing import Any, Dict

from flask import Flask

logger = logging.getLogger(__name__)


def run_ppv_enrichment(app: Flask) -> Dict[str, Any]:
    from services.ppv.enrichment import get_calendar_enrichment_service
    from services.ppv.orchestrator import get_ppv_orchestrator

    orchestrator = get_ppv_orchestrator(app)
    stats = orchestrator.enrich_pending_channels()
    if stats.get("skipped"):
        return stats
    if stats.get("channels_matched", 0) > 0:
        get_calendar_enrichment_service(app).start_detail_fetcher()
    if stats.get("channels_no_match", 0) > 0:
        orchestrator.run_enhanced_fallback()
    return stats


def run_ppv_prefetch(app: Flask) -> Dict[str, Any]:
    from services.ppv.orchestrator import get_ppv_orchestrator

    return get_ppv_orchestrator(app).prefetch_calendars(days_ahead=30, days_back=7)
