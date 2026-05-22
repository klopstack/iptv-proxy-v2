"""Backward compatibility — use services.ppv.enrichment instead."""

from services.ppv.enrichment import (  # noqa: F401
    PPVCalendarEnrichmentService,
    enrich_ppv_channels_batch,
    get_calendar_enrichment_service,
)

__all__ = [
    "PPVCalendarEnrichmentService",
    "get_calendar_enrichment_service",
    "enrich_ppv_channels_batch",
]
