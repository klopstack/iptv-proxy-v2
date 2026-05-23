"""Backward compatibility — use services.ppv.enrichment instead."""

import warnings

warnings.warn(
    "Import from services.ppv.enrichment instead of services.ppv_calendar_enrichment_service",
    DeprecationWarning,
    stacklevel=2,
)

from services.ppv.enrichment import (  # noqa: F401
    API_REQUEST_INTERVAL,
    API_REQUESTS_PER_MINUTE,
    DETAIL_FETCH_BATCH_SIZE,
    ENRICHMENT_BATCH_SIZE,
    GENERIC_CHANNEL_PATTERNS,
    EnrichmentResult,
    PPVCalendarEnrichmentService,
    enrich_ppv_channels_batch,
    get_calendar_enrichment_service,
    is_generic_channel_name,
)

__all__ = [
    "API_REQUEST_INTERVAL",
    "API_REQUESTS_PER_MINUTE",
    "DETAIL_FETCH_BATCH_SIZE",
    "ENRICHMENT_BATCH_SIZE",
    "GENERIC_CHANNEL_PATTERNS",
    "EnrichmentResult",
    "PPVCalendarEnrichmentService",
    "get_calendar_enrichment_service",
    "enrich_ppv_channels_batch",
    "is_generic_channel_name",
]
