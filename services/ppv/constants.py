"""
PPV domain constants — single source for category, placeholder, and generic channel patterns.
"""

import re
from typing import Optional

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
    "PPV_ENRICHMENT_HOT_BATCH_SIZE",
    "PPV_ENRICHMENT_BACKLOG_THRESHOLD",
    "PPV_ENRICHMENT_HOT_WINDOW_HOURS",
    "SPORT_GRACE_HOURS",
    "DEFAULT_SPORT_GRACE_HOURS",
    "get_sport_grace_hours",
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
    re.compile(r"^Event\s*\d+$", re.IGNORECASE),
    re.compile(r"^\d+\s*-\s*PPV", re.IGNORECASE),
    re.compile(r"^PPV\s*HD\s*\d*$", re.IGNORECASE),
    re.compile(r"^\(.*\)$", re.IGNORECASE),
    re.compile(r"^MILB\s*\d{1,3}$", re.IGNORECASE),
    re.compile(r"^:?Milb\s+\d{1,3}$", re.IGNORECASE),
    re.compile(r"^(?:[A-Z]{2}\s*)?\(MiLB\s+\d{1,3}\)\s*$", re.IGNORECASE),
]

# Enrichment thresholds (aligned with calendar enrichment service)
MIN_MATCH_CONFIDENCE = 0.35
MEDIUM_CONFIDENCE_THRESHOLD = 0.6
HIGH_CONFIDENCE_THRESHOLD = 0.7
MAX_EVENT_AGE_DAYS = 30
MAX_EVENT_FUTURE_DAYS = 365
MAX_RETRY_ATTEMPTS = 3
ENRICHMENT_BATCH_SIZE = 100
ENRICHMENT_BACKLOG_BATCH_SIZE = 500

# Queue throughput tuning
PPV_ENRICHMENT_HOT_BATCH_SIZE = 50
PPV_ENRICHMENT_BACKLOG_THRESHOLD = 1000
PPV_ENRICHMENT_HOT_WINDOW_HOURS = 24
# Max enrich_pending_channels() loops per scheduler/API run (0 = drain until queue empty)
PPV_ENRICHMENT_MAX_BATCHES_PER_RUN = 0

# Sport-aware grace windows for live-game visibility (hours after scheduled_at)
SPORT_GRACE_HOURS = {
    "baseball": 4,
    "mlb": 4,
    "milb": 4,
    "hockey": 4,
    "ice hockey": 4,
    "nhl": 4,
    "basketball": 3,
    "nba": 3,
    "football": 4,
    "nfl": 4,
    "soccer": 2,
    "football (soccer)": 2,
    "boxing": 12,
    "mma": 12,
    "ufc": 12,
    "wrestling": 4,
    "tennis": 3,
    "golf": 6,
    "rugby": 3,
}
DEFAULT_SPORT_GRACE_HOURS = 6

# Feed region → default IANA for single-zone countries (PPV title timezone inference)
COUNTRY_PREFIX_TZ: dict[str, str] = {
    "UK": "Europe/London",
    "GB": "Europe/London",
    "IE": "Europe/Dublin",
    "NL": "Europe/Amsterdam",
    "BE": "Europe/Brussels",
    "DE": "Europe/Berlin",
    "FR": "Europe/Paris",
    "ES": "Europe/Madrid",
    "IT": "Europe/Rome",
    "PT": "Europe/Lisbon",
    "SE": "Europe/Stockholm",
    "NO": "Europe/Oslo",
    "DK": "Europe/Copenhagen",
    "FI": "Europe/Helsinki",
    "PL": "Europe/Warsaw",
    "AT": "Europe/Vienna",
    "CH": "Europe/Zurich",
    "GR": "Europe/Athens",
    "TR": "Europe/Istanbul",
    "RU": "Europe/Moscow",
    "JP": "Asia/Tokyo",
    "AU": "Australia/Sydney",
    "NZ": "Pacific/Auckland",
    "MX": "America/Mexico_City",
    "BR": "America/Sao_Paulo",
}

US_STYLE_REGION_CODES = frozenset({"US", "CA", "JP"})

# Provider suffix on channel names (after country prefix) → default IANA timezone
PROVIDER_SUFFIX_TZ: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"[:|]\s*Viaplay\s+SE(?:/|\b)", re.I), "Europe/Stockholm", "provider_viaplay_se"),
    (re.compile(r"[:|]\s*Viaplay\s+DK(?:/|\b)", re.I), "Europe/Copenhagen", "provider_viaplay_dk"),
    (re.compile(r"[:|]\s*Viaplay\s+NO(?:/|\b)", re.I), "Europe/Oslo", "provider_viaplay_no"),
    (re.compile(r"[:|]\s*Viaplay\s+NL(?:/|\b)", re.I), "Europe/Amsterdam", "provider_viaplay_nl"),
    (re.compile(r"Viaplay\s+SE/DK/NO", re.I), "Europe/Stockholm", "provider_viaplay_nordic"),
    (re.compile(r"[:|]\s*Telia\s+FI\b", re.I), "Europe/Helsinki", "provider_telia_fi"),
    (re.compile(r"[:|]\s*MAX\s+ES\b", re.I), "Europe/Madrid", "provider_max_es"),
    (re.compile(r"[:|]\s*Sportsnet\+", re.I), "America/Toronto", "provider_sportsnet_ca"),
    (re.compile(r"[:|]\s*beIN\s+Sports\s+FR\b", re.I), "Europe/Paris", "provider_bein_fr"),
    (re.compile(r"[:|]\s*Sky\s+Sports\s+NZ\b", re.I), "Pacific/Auckland", "provider_sky_nz"),
]


def get_sport_grace_hours(sport_name: Optional[str]) -> int:
    """Return hours after scheduled_at to keep a linked event visible in the playlist."""
    if not sport_name:
        return DEFAULT_SPORT_GRACE_HOURS
    return SPORT_GRACE_HOURS.get(sport_name.lower().strip(), DEFAULT_SPORT_GRACE_HOURS)


# Scheduler / settings keys
SETTING_PPV_ENRICHMENT_ENABLED = "ppv_enrichment_enabled"
METADATA_KEY_CALENDAR_PROCESSED = "ppv_calendar_processed_count"
METADATA_KEY_CALENDAR_MATCHED = "ppv_calendar_matched_count"
METADATA_KEY_DETAILS_FETCHED = "ppv_details_fetched_count"
METADATA_KEY_DETAIL_QUEUE_SIZE = "ppv_detail_queue_size"
