"""
PPV domain constants — single source for category, placeholder, and generic channel patterns.
"""

import re

# Re-export from EPG constants (shared with sync/category marking)
from services.epg.constants import PPV_CATEGORY_PATTERNS, PPV_PLACEHOLDER_PATTERNS  # noqa: F401

__all__ = [
    "GENERIC_CHANNEL_PATTERNS",
    "PPV_CATEGORY_PATTERNS",
    "PPV_PLACEHOLDER_PATTERNS",
    "MIN_MATCH_CONFIDENCE",
    "MEDIUM_CONFIDENCE_THRESHOLD",
    "HIGH_CONFIDENCE_THRESHOLD",
    "MAX_EVENT_AGE_DAYS",
    "MAX_EVENT_FUTURE_DAYS",
    "MAX_RETRY_ATTEMPTS",
    "ENRICHMENT_BATCH_SIZE",
    "SETTING_PPV_ENRICHMENT_ENABLED",
    "METADATA_KEY_CALENDAR_PROCESSED",
    "METADATA_KEY_CALENDAR_MATCHED",
    "METADATA_KEY_DETAILS_FETCHED",
    "METADATA_KEY_DETAIL_QUEUE_SIZE",
]

# Generic channel name patterns (inactive / numbered placeholders without events)
GENERIC_CHANNEL_PATTERNS = [
    re.compile(r"^PPV\s*\d+$", re.IGNORECASE),
    re.compile(r"^PPV\s*Event\s*\d*$", re.IGNORECASE),
    re.compile(r"^UFC\s*Event\s*\d*$", re.IGNORECASE),
    re.compile(r"^Boxing\s*Event\s*\d*$", re.IGNORECASE),
    re.compile(r"^MMA\s*Event\s*\d*$", re.IGNORECASE),
    re.compile(r"^Sports?\s*Event\s*\d*$", re.IGNORECASE),
    re.compile(r"^Live\s*Event\s*\d*$", re.IGNORECASE),
]

# Enrichment thresholds (aligned with calendar enrichment service)
MIN_MATCH_CONFIDENCE = 0.35
MEDIUM_CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.7
MAX_EVENT_AGE_DAYS = 30
MAX_EVENT_FUTURE_DAYS = 365
MAX_RETRY_ATTEMPTS = 3
ENRICHMENT_BATCH_SIZE = 100

# Scheduler / settings keys
SETTING_PPV_ENRICHMENT_ENABLED = "ppv_enrichment_enabled"
METADATA_KEY_CALENDAR_PROCESSED = "ppv_calendar_processed_count"
METADATA_KEY_CALENDAR_MATCHED = "ppv_calendar_matched_count"
METADATA_KEY_DETAILS_FETCHED = "ppv_details_fetched_count"
METADATA_KEY_DETAIL_QUEUE_SIZE = "ppv_detail_queue_size"
