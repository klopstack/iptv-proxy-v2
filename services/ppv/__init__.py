"""
PPV domain package — enrichment, visibility, and event-based EPG.

Public API:
    PPVEnrichmentOrchestrator, get_ppv_orchestrator
    PPVVisibilityService
    PPVEpgService
    PPVEventExtractor (extraction)
    detection helpers: is_ppv_category, is_ppv_channel, is_ppv_placeholder_name
"""

from services.ppv.detection import (
    is_generic_channel_name,
    is_ppv_category,
    is_ppv_channel,
    is_ppv_placeholder_name,
)
from services.ppv.enrichment import (
    PPVCalendarEnrichmentService,
    enrich_ppv_channels_batch,
    get_calendar_enrichment_service,
)
from services.ppv.epg import PPVEpgService
from services.ppv.extraction import PPVEventExtractor
from services.ppv.orchestrator import PPVEnrichmentOrchestrator, get_ppv_orchestrator
from services.ppv.visibility import PPVVisibilityService

__all__ = [
    "PPVEnrichmentOrchestrator",
    "get_ppv_orchestrator",
    "PPVVisibilityService",
    "PPVEpgService",
    "PPVEventExtractor",
    "PPVCalendarEnrichmentService",
    "get_calendar_enrichment_service",
    "enrich_ppv_channels_batch",
    "is_ppv_category",
    "is_ppv_channel",
    "is_ppv_placeholder_name",
    "is_generic_channel_name",
]
