"""Shared types and helpers for PPV calendar enrichment."""

from typing import Dict, Optional, Tuple

from models import Event
from services.thesportsdb_calendar_scraper import CalendarEvent

DetailQueueItem = Tuple[str, str]  # (external_id, source)

# Wakes detail-fetch thread blocked on queue.get() during stop()
DETAIL_QUEUE_STOP: DetailQueueItem = ("", "")

# Idle poll when queues are empty (longer timeout would slow test teardown and shutdown)
DETAIL_QUEUE_IDLE_TIMEOUT_SECONDS = 1.0

DETAIL_FETCH_BATCH_SIZE = 25


def calendar_event_source(calendar_event: CalendarEvent) -> str:
    source = getattr(calendar_event, "source", None) or Event.SOURCE_THESPORTSDB
    if source == "mlb_stats_api":
        return Event.SOURCE_MLB_STATS
    return source


class EnrichmentResult:
    """Result of attempting to enrich a channel."""

    def __init__(
        self,
        channel,
        matched: bool,
        event=None,
        calendar_event: Optional[CalendarEvent] = None,
        confidence: float = 0.0,
        match_method: str = "none",
        extraction_result: Optional[Dict] = None,
        error: Optional[str] = None,
    ):
        self.channel = channel
        self.matched = matched
        self.event = event
        self.calendar_event = calendar_event
        self.confidence = confidence
        self.match_method = match_method
        self.extraction_result = extraction_result
        self.error = error
