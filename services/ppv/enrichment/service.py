"""Thin coordinator wiring calendar match pipeline, detail fetch, and side effects."""

import logging
from typing import Any, Dict, List, Optional

from flask import Flask

from models import Channel, Event, SyncMetadata
from services.ppv.constants import (
    METADATA_KEY_CALENDAR_MATCHED,
    METADATA_KEY_CALENDAR_PROCESSED,
    METADATA_KEY_DETAILS_FETCHED,
)
from services.ppv.enrichment.detail_fetch import DetailFetchWorker
from services.ppv.enrichment.match_pipeline import CalendarMatchPipeline
from services.ppv.enrichment.side_effects import EnrichmentSideEffects
from services.ppv.enrichment_post_hooks import get_enrichment_post_hooks
from services.ppv.persistence import sync_enrichment_status_from_links

logger = logging.getLogger(__name__)


class PPVCalendarEnrichmentService:
    """
    Calendar-based PPV enrichment coordinator.

    Delegates to CalendarMatchPipeline, DetailFetchWorker, and EnrichmentSideEffects.
    Post-batch EPG sync runs via EnrichmentPostHooks (TODO 66).
    """

    def __init__(self, app: Flask):
        self.app = app
        self.match_pipeline = CalendarMatchPipeline()
        session_stats = {
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_extraction": 0,
            "channels_no_match": 0,
            "calendar_requests": 0,
            "api_requests": 0,
        }
        self._detail_worker = DetailFetchWorker(app, stats=session_stats)
        self.detail_worker = self._detail_worker
        self.side_effects = EnrichmentSideEffects()

    # --- Back-compat: pipeline surface used by tests ---

    @property
    def extractor(self):
        return self.match_pipeline.extractor

    @extractor.setter
    def extractor(self, value):
        self.match_pipeline.extractor = value

    @property
    def calendar_scraper(self):
        return self.match_pipeline.calendar_scraper

    @calendar_scraper.setter
    def calendar_scraper(self, value):
        self.match_pipeline.calendar_scraper = value

    @property
    def reverse_matcher(self):
        return self.match_pipeline.reverse_matcher

    @reverse_matcher.setter
    def reverse_matcher(self, value):
        self.match_pipeline.reverse_matcher = value

    @property
    def thesportsdb(self):
        return self._detail_worker.thesportsdb

    @property
    def _detail_queue(self):
        return self._detail_worker.detail_queue

    @property
    def _refresh_queue(self):
        return self._detail_worker.refresh_queue

    @property
    def _detail_thread(self):
        return self._detail_worker._detail_thread

    @property
    def _stop_detail_thread(self):
        return self._detail_worker._stop_detail_thread

    @property
    def _stats(self):
        return self._detail_worker.session_stats

    def _extract_all_channels(self, channels):
        return self.match_pipeline.extract_all_channels(channels)

    def _group_by_date(self, channel_extractions):
        return self.match_pipeline.group_by_date(channel_extractions)

    def _get_event_date(self, extraction):
        return self.match_pipeline.get_event_date(extraction)

    def _match_channel_to_calendar(self, channel, extraction, calendar_events, date_str, **kwargs):
        return self.match_pipeline.match_channel_to_calendar(channel, extraction, calendar_events, date_str, **kwargs)

    def _update_event_from_api(self, event, api_data):
        return self._detail_worker.update_event_from_api(event, api_data)

    def _fetch_event_details(self, external_id, source, force_refresh=False):
        return self._detail_worker.fetch_event_details(external_id, source, force_refresh=force_refresh)

    def _update_stats(self, results):
        return self.side_effects.update_cumulative_stats(results)

    # --- Public API ---

    def enrich_channels(self, channels: List[Channel], fetch_details: bool = True) -> Dict[str, Any]:
        with self.app.app_context():
            results, event_ids_to_fetch = self.match_pipeline.run(channels, coordinator=self)

            if fetch_details and event_ids_to_fetch:
                for external_id, source in event_ids_to_fetch:
                    self._detail_worker.queue_detail(external_id, source)

                logger.info("Queued %s events for detail fetching", len(event_ids_to_fetch))

                if not self._detail_worker.is_running():
                    self.start_detail_fetcher()

            self._update_stats(results)
            sync_enrichment_status_from_links(ch.id for ch in channels)
            get_enrichment_post_hooks().run(results)
            return results

    def start_detail_fetcher(self) -> None:
        if self._detail_worker.is_running():
            logger.warning("Detail fetcher thread already running")
            return
        self._detail_worker.start()

    def stop_detail_fetcher(self) -> None:
        self._detail_worker.stop()

    def refresh_upcoming_event_times(self, hours_ahead: int = 48) -> Dict[str, Any]:
        return self._detail_worker.refresh_upcoming_event_times(hours_ahead=hours_ahead)

    def get_status(self) -> Dict[str, Any]:
        queue_sizes = self._detail_worker.get_queue_sizes()
        return {
            "detail_queue_size": queue_sizes["detail_queue_size"],
            "refresh_queue_size": queue_sizes["refresh_queue_size"],
            "llm_queue_size": queue_sizes["llm_queue_size"],
            "detail_thread_running": self._detail_worker.is_running(),
            "calendar_cache_stats": self.match_pipeline.calendar_scraper.get_cache_stats(),
            "cumulative_stats": {
                "calendar_processed": SyncMetadata.get(METADATA_KEY_CALENDAR_PROCESSED, "0"),
                "calendar_matched": SyncMetadata.get(METADATA_KEY_CALENDAR_MATCHED, "0"),
                "details_fetched": SyncMetadata.get(METADATA_KEY_DETAILS_FETCHED, "0"),
            },
            "session_stats": self._detail_worker.session_stats.copy(),
        }

    def queue_event_detail(self, event_id: str, source: str = Event.SOURCE_THESPORTSDB) -> None:
        self._detail_worker.queue_event(event_id, source)


_service_instance: Optional[PPVCalendarEnrichmentService] = None


def get_calendar_enrichment_service(app: Flask) -> PPVCalendarEnrichmentService:
    global _service_instance
    if _service_instance is None:
        _service_instance = PPVCalendarEnrichmentService(app)
    return _service_instance


def enrich_ppv_channels_batch(app: Flask, account_id: int) -> Dict[str, Any]:
    with app.app_context():
        channels = Channel.query.filter(
            Channel.account_id == account_id,
            Channel.is_ppv.is_(True),
        ).all()

        if not channels:
            return {"error": "No PPV channels found for account"}

        service = get_calendar_enrichment_service(app)
        return service.enrich_channels(channels)
