"""SofaScore calendar provider constants."""

EVENT_SOURCE_SOFASCORE = "sofascore"
CACHE_TTL_SECONDS = 12 * 3600
REQUEST_TIMEOUT = 30
MIN_REQUEST_INTERVAL_SECONDS = 3.0

SCHEDULED_EVENTS_URL = "https://api.sofascore.com/api/v1/sport/{sport}/scheduled-events/{date_str}"

_INCLUDED_STATUS_TYPES = frozenset({"notstarted", "inprogress", "finished"})
_EXCLUDED_STATUS_TYPES = frozenset({"cancelled", "postponed", "suspended", "interrupted", "canceled"})
