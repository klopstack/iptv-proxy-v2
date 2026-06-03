"""
PPV Event Enrichment Service v2

Calendar-based matching with optional API detail fetch. Phase 1 split:
- CalendarMatchPipeline — extract, classify, group, match, persist
- DetailFetchWorker — queue, rate limit, API update, LLM hook
- EnrichmentSideEffects — EPG sync, orphan prune, cumulative stats
- PPVCalendarEnrichmentService — thin coordinator
"""

from services.ppv.cleanup import prune_orphan_ppv_events, sync_ppv_epg_after_enrichment
from services.ppv.enrichment.log import logger  # noqa: F401 — patch target for tests
from services.ppv.enrichment.detail_fetch import DetailFetchWorker
from services.ppv.enrichment.match_pipeline import CalendarMatchPipeline
from services.ppv.enrichment.service import (
    PPVCalendarEnrichmentService,
    enrich_ppv_channels_batch,
    get_calendar_enrichment_service,
)
from services.ppv.enrichment.service import _service_instance  # noqa: F401 — tests reset singleton
from services.ppv.enrichment.side_effects import EnrichmentSideEffects
from services.ppv.enrichment.types import EnrichmentResult
from services.ppv.persistence import sync_enrichment_status_from_links

__all__ = [
    "logger",
    "CalendarMatchPipeline",
    "DetailFetchWorker",
    "EnrichmentResult",
    "EnrichmentSideEffects",
    "PPVCalendarEnrichmentService",
    "enrich_ppv_channels_batch",
    "get_calendar_enrichment_service",
    "prune_orphan_ppv_events",
    "sync_enrichment_status_from_links",
    "sync_ppv_epg_after_enrichment",
]
