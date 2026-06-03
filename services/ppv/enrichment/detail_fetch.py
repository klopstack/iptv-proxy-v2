"""Background API detail fetch worker for matched PPV events."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue
from typing import Any, Callable, Dict, Optional

from flask import Flask

from models import Event, EventChannelLink, SyncMetadata, db
from services.datetime_utils import parse_thesportsdb_scheduled_at, to_naive_utc
from services.ppv.constants import METADATA_KEY_DETAILS_FETCHED
from services.ppv.enrichment.log_proxy import logger
from services.ppv.enrichment.types import DETAIL_QUEUE_IDLE_TIMEOUT_SECONDS, DETAIL_QUEUE_STOP, DetailQueueItem
from services.thesportsdb_service import TheSportsDBService, get_thesportsdb_api_request_interval

LLM_ENRICHMENT_TIMEOUT_SECONDS = 45

DetailFetchHandler = Callable[[str, str, bool], bool]
"""(external_id, source, force_refresh) -> True if event should be queued for LLM."""

LlmEnrichmentHandler = Callable[[str], None]
"""Run LLM description enrichment for an event external_id (within app context)."""


class DetailFetchWorker:
    """
    Queue, rate-limit, and fetch full event details from TheSportsDB.

    Uses per-item Flask app contexts and db.session.remove() — no long-lived global
    ORM session. LLM enrichment runs only when API queues are idle.
    """

    def __init__(
        self,
        app: Flask,
        thesportsdb: Optional[TheSportsDBService] = None,
        *,
        fetch_handler: Optional[DetailFetchHandler] = None,
        llm_handler: Optional[LlmEnrichmentHandler] = None,
        stats: Optional[Dict[str, int]] = None,
    ):
        self.app = app
        self.thesportsdb = thesportsdb or TheSportsDBService()
        self._fetch_handler = fetch_handler or self._fetch_event_details_api
        self._llm_handler = llm_handler or self._run_llm_enrichment_for_event
        self.session_stats: Dict[str, int] = (
            stats
            if stats is not None
            else {
                "channels_processed": 0,
                "channels_matched": 0,
                "channels_no_extraction": 0,
                "channels_no_match": 0,
                "calendar_requests": 0,
                "api_requests": 0,
            }
        )

        self.detail_queue: Queue[DetailQueueItem] = Queue()
        self.refresh_queue: Queue[DetailQueueItem] = Queue()
        self._llm_queue: Queue[str] = Queue()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    # --- Back-compat aliases for tests ---

    @property
    def _detail_thread(self) -> Optional[threading.Thread]:
        return self._thread

    @property
    def _stop_detail_thread(self) -> threading.Event:
        return self._stop_event

    def queue_detail(self, external_id: str, source: str) -> None:
        if external_id:
            self.detail_queue.put((str(external_id), source))

    def queue_refresh(self, external_id: str, source: str) -> None:
        if external_id:
            self.refresh_queue.put((str(external_id), source))

    def queue_items(self, items) -> None:
        for item in items:
            self.detail_queue.put(item)

    def queue_event(self, event_id: str, source: str = Event.SOURCE_THESPORTSDB) -> None:
        if not event_id or source != Event.SOURCE_THESPORTSDB:
            return
        self.queue_detail(str(event_id), source)
        self.ensure_running()

    def ensure_running(self) -> None:
        if not self.is_running():
            self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            logger.warning("Detail fetcher thread already running")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="PPVDetailFetcher",
            daemon=True,
        )
        self._thread.start()
        logger.info("Started PPV detail fetch worker")

    def stop(self) -> None:
        self._stop_event.set()
        for queue in (self.detail_queue, self.refresh_queue):
            try:
                queue.put_nowait(DETAIL_QUEUE_STOP)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=10)
            self._thread = None
            logger.info("Stopped PPV detail fetch worker")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_queue_sizes(self) -> Dict[str, int]:
        return {
            "detail_queue_size": self.detail_queue.qsize(),
            "refresh_queue_size": self.refresh_queue.qsize(),
            "llm_queue_size": self._llm_queue.qsize(),
        }

    def refresh_upcoming_event_times(self, hours_ahead: int = 48) -> Dict[str, Any]:
        with self.app.app_context():
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            window_start = now - timedelta(hours=3)
            window_end = now + timedelta(hours=hours_ahead)

            events = (
                Event.query.join(EventChannelLink, Event.id == EventChannelLink.event_id)
                .filter(
                    Event.source == Event.SOURCE_THESPORTSDB,
                    Event.scheduled_at >= window_start,
                    Event.scheduled_at <= window_end,
                    Event.status.notin_([Event.STATUS_FINISHED, Event.STATUS_CANCELLED]),
                )
                .distinct()
                .all()
            )

            for event in events:
                self.queue_refresh(event.external_id, event.source)

            if events:
                self.ensure_running()

            logger.info("Queued %s events for near-term time/status refresh", len(events))
            return {"queued": len(events), "hours_ahead": hours_ahead}

    def fetch_event_details(self, external_id: str, source: str, force_refresh: bool = False) -> None:
        """Synchronous detail fetch (tests); uses a fresh app context per call."""
        with self.app.app_context():
            try:
                self._fetch_event_details_api(external_id, source, force_refresh)
            finally:
                db.session.remove()

    def _run_loop(self) -> None:
        logger.info("Detail fetch worker loop started")
        try:
            while not self._stop_event.is_set():
                force_refresh = False
                try:
                    external_id, source = self.refresh_queue.get_nowait()
                    force_refresh = True
                except Empty:
                    try:
                        external_id, source = self.detail_queue.get(timeout=DETAIL_QUEUE_IDLE_TIMEOUT_SECONDS)
                    except Empty:
                        self._drain_llm_when_idle()
                        continue

                if external_id == DETAIL_QUEUE_STOP[0] or self._stop_event.is_set():
                    continue

                queue_for_done = self.refresh_queue if force_refresh else self.detail_queue
                try:
                    self._process_detail_item(external_id, source, force_refresh=force_refresh)
                    time.sleep(get_thesportsdb_api_request_interval())
                except Exception as e:
                    logger.error("Error in detail fetch worker: %s", e, exc_info=True)
                    time.sleep(1)
                finally:
                    try:
                        queue_for_done.task_done()
                    except ValueError:
                        pass

                self._drain_llm_when_idle()
        finally:
            logger.info("Detail fetch worker loop stopped")

    def _process_detail_item(self, external_id: str, source: str, *, force_refresh: bool = False) -> None:
        with self.app.app_context():
            try:
                queue_llm = self._fetch_handler(external_id, source, force_refresh)
                if queue_llm:
                    self._llm_queue.put(external_id)
            finally:
                db.session.remove()

    def _drain_llm_when_idle(self) -> None:
        if self._llm_handler is None:
            return
        if not self.detail_queue.empty() or not self.refresh_queue.empty():
            return

        while not self._stop_event.is_set():
            if not self.detail_queue.empty() or not self.refresh_queue.empty():
                return
            try:
                external_id = self._llm_queue.get_nowait()
            except Empty:
                return
            self._process_llm_item(external_id)

    def _process_llm_item(self, external_id: str) -> None:
        llm_handler = self._llm_handler
        if llm_handler is None:
            return

        def _run() -> None:
            with self.app.app_context():
                try:
                    llm_handler(external_id)
                finally:
                    db.session.remove()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_run)
            try:
                future.result(timeout=LLM_ENRICHMENT_TIMEOUT_SECONDS)
            except FuturesTimeoutError:
                logger.warning(
                    "LLM enrichment timed out after %ss for event %s",
                    LLM_ENRICHMENT_TIMEOUT_SECONDS,
                    external_id,
                )
            except Exception as e:
                logger.warning("LLM enrichment failed for event %s: %s", external_id, e)

    def _fetch_event_details_api(self, external_id: str, source: str, force_refresh: bool = False) -> bool:
        if source != Event.SOURCE_THESPORTSDB:
            logger.debug(
                "Skipping detail fetch for %s event %s (source uses basic completeness)",
                source,
                external_id,
            )
            return False

        try:
            event = Event.query.filter_by(
                external_id=external_id,
                source=source,
            ).first()

            if not event:
                logger.warning("Event %s (%s) not found in database", external_id, source)
                return False

            if not force_refresh and event.data_completeness in ("full", "enriched"):
                logger.debug("Event %s already has full details", external_id)
                return False

            api_data = self.thesportsdb.get_event_by_id(external_id)

            if not api_data:
                logger.warning("No API data returned for event %s", external_id)
                return False

            changed = self.update_event_from_api(event, api_data)
            if changed:
                self._sync_epg_for_event(event)

            logger.info("Fetched full details for event %s", external_id)
            self.session_stats["api_requests"] += 1

            details_fetched = int(SyncMetadata.get(METADATA_KEY_DETAILS_FETCHED, "0"))
            SyncMetadata.set(METADATA_KEY_DETAILS_FETCHED, str(details_fetched + 1))

            return self._llm_enrichment_enabled()

        except Exception as e:
            logger.error("Error fetching details for event %s: %s", external_id, e)
            try:
                db.session.rollback()
            except Exception:
                pass
            return False

    @staticmethod
    def _llm_enrichment_enabled() -> bool:
        try:
            from models.provider_settings import ProviderSettings

            return ProviderSettings.get("llm_enrichment", "enabled", "false").lower() == "true"
        except Exception:
            return False

    def _run_llm_enrichment_for_event(self, external_id: str) -> None:
        from services.ppv.context import build_event_context, generate_event_description_or_fallback
        from services.ppv.context.assembler import persist_context_metadata

        event = Event.query.filter_by(
            external_id=external_id,
            source=Event.SOURCE_THESPORTSDB,
        ).first()
        if not event:
            return

        context = build_event_context(event)
        persist_context_metadata(event, context)
        description = generate_event_description_or_fallback(context)
        if description:
            event.description = description
            event.data_completeness = "enriched"
            db.session.commit()

    def update_event_from_api(self, event: Event, api_data: Dict) -> bool:
        try:
            old_scheduled = to_naive_utc(event.scheduled_at) if event.scheduled_at else None
            old_status = event.status

            event.sport = api_data.get("strSport", event.sport)
            event.league_name = api_data.get("strLeague", event.league_name)
            event.league_id = api_data.get("idLeague")

            event.home_team_name = api_data.get("strHomeTeam", event.home_team_name)
            event.home_team_id = api_data.get("idHomeTeam")
            event.away_team_name = api_data.get("strAwayTeam", event.away_team_name)
            event.away_team_id = api_data.get("idAwayTeam")

            scheduled, event_tz = parse_thesportsdb_scheduled_at(api_data)
            if scheduled is not None:
                event.scheduled_at = scheduled
            if event_tz:
                event.timezone = event_tz

            event.venue_id = api_data.get("idVenue") or event.venue_id
            event.venue_name = api_data.get("strVenue") or event.venue_name
            event.city = api_data.get("strCity") or api_data.get("strVenueLocation") or event.city
            event.country = api_data.get("strCountry") or event.country

            event.event_image = api_data.get("strPoster") or api_data.get("strThumb")

            status_str = (api_data.get("strStatus") or "").lower()
            if "finished" in status_str or "ft" == status_str:
                event.status = Event.STATUS_FINISHED
            elif "live" in status_str or "in progress" in status_str:
                event.status = Event.STATUS_LIVE
            elif "cancelled" in status_str or "postponed" in status_str:
                event.status = Event.STATUS_CANCELLED

            event.data_completeness = "full"
            event.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            db.session.commit()

            new_scheduled = to_naive_utc(event.scheduled_at) if event.scheduled_at else None
            return new_scheduled != old_scheduled or event.status != old_status

        except Exception as e:
            logger.error("Error updating event %s from API: %s", event.id, e)
            db.session.rollback()
            return False

    def _sync_epg_for_event(self, event: Event) -> None:
        try:
            from services.ppv.epg import PPVEpgService

            PPVEpgService.sync_ppv_event_to_epg_channels(event)
        except Exception as e:
            logger.warning("Failed to sync EPG for event %s: %s", event.external_id, e)
