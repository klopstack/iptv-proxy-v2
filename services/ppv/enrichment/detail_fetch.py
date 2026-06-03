"""Background API detail fetch worker for matched PPV events."""

import threading
import time
from datetime import datetime, timedelta, timezone
from queue import Empty, Queue
from typing import Any, Dict, Optional

from flask import Flask

from models import Event, EventChannelLink, SyncMetadata, db
from services.datetime_utils import parse_thesportsdb_scheduled_at, to_naive_utc
from services.ppv.constants import METADATA_KEY_DETAILS_FETCHED
from services.ppv.enrichment.log_proxy import logger
from services.ppv.enrichment.types import DETAIL_QUEUE_IDLE_TIMEOUT_SECONDS, DETAIL_QUEUE_STOP, DetailQueueItem
from services.thesportsdb_service import TheSportsDBService, get_thesportsdb_api_request_interval


class DetailFetchWorker:
    """Queue, rate-limit, and fetch full event details from TheSportsDB."""

    def __init__(self, app: Flask, thesportsdb: Optional[TheSportsDBService] = None):
        self.app = app
        self.thesportsdb = thesportsdb or TheSportsDBService()

        self.detail_queue: Queue[DetailQueueItem] = Queue()
        self.refresh_queue: Queue[DetailQueueItem] = Queue()
        self._detail_thread: Optional[threading.Thread] = None
        self._stop_detail_thread = threading.Event()

        self.session_stats: Dict[str, int] = {
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_extraction": 0,
            "channels_no_match": 0,
            "calendar_requests": 0,
            "api_requests": 0,
        }

    def queue_items(self, items) -> None:
        for item in items:
            self.detail_queue.put(item)

    def queue_event(self, event_id: str, source: str = Event.SOURCE_THESPORTSDB) -> None:
        if not event_id or source != Event.SOURCE_THESPORTSDB:
            return
        self.detail_queue.put((str(event_id), source))
        self.ensure_running()

    def ensure_running(self) -> None:
        if not self._detail_thread or not self._detail_thread.is_alive():
            self.start()

    def start(self) -> None:
        if self._detail_thread and self._detail_thread.is_alive():
            logger.warning("Detail fetcher thread already running")
            return

        self._stop_detail_thread.clear()
        self._detail_thread = threading.Thread(
            target=self._detail_fetch_loop,
            name="PPVDetailFetcher",
            daemon=True,
        )
        self._detail_thread.start()
        logger.info("Started PPV detail fetcher thread")

    def stop(self) -> None:
        self._stop_detail_thread.set()
        for queue in (self.detail_queue, self.refresh_queue):
            try:
                queue.put_nowait(DETAIL_QUEUE_STOP)
            except Exception:
                pass
        if self._detail_thread:
            self._detail_thread.join(timeout=10)
            logger.info("Stopped PPV detail fetcher thread")

    @property
    def detail_thread(self) -> Optional[threading.Thread]:
        return self._detail_thread

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
                self.refresh_queue.put((event.external_id, event.source))

            if events:
                self.ensure_running()

            logger.info("Queued %s events for near-term time/status refresh", len(events))
            return {"queued": len(events), "hours_ahead": hours_ahead}

    def _detail_fetch_loop(self) -> None:
        logger.info("Detail fetch loop started")

        ctx = self.app.app_context()
        ctx.push()

        try:
            while not self._stop_detail_thread.is_set():
                force_refresh = False
                try:
                    external_id, source = self.refresh_queue.get_nowait()
                    force_refresh = True
                except Empty:
                    try:
                        external_id, source = self.detail_queue.get(timeout=DETAIL_QUEUE_IDLE_TIMEOUT_SECONDS)
                    except Empty:
                        continue

                if external_id == DETAIL_QUEUE_STOP[0] or self._stop_detail_thread.is_set():
                    continue

                try:
                    self.fetch_event_details(external_id, source, force_refresh=force_refresh)
                    time.sleep(get_thesportsdb_api_request_interval())

                    if force_refresh:
                        self.refresh_queue.task_done()
                    else:
                        self.detail_queue.task_done()

                except Exception as e:
                    logger.error(f"Error in detail fetch loop: {e}", exc_info=True)
                    time.sleep(1)
        finally:
            ctx.pop()

        logger.info("Detail fetch loop stopped")

    def fetch_event_details(self, external_id: str, source: str, force_refresh: bool = False) -> None:
        if source != Event.SOURCE_THESPORTSDB:
            logger.debug(
                "Skipping detail fetch for %s event %s (source uses basic completeness)",
                source,
                external_id,
            )
            return

        try:
            event = Event.query.filter_by(
                external_id=external_id,
                source=source,
            ).first()

            if not event:
                logger.warning("Event %s (%s) not found in database", external_id, source)
                return

            if not force_refresh and event.data_completeness in ("full", "enriched"):
                logger.debug("Event %s already has full details", external_id)
                return

            api_data = self.thesportsdb.get_event_by_id(external_id)

            if not api_data:
                logger.warning(f"No API data returned for event {external_id}")
                return

            changed = self.update_event_from_api(event, api_data)
            if changed:
                self._sync_epg_for_event(event)

            logger.info(f"Fetched full details for event {external_id}")
            self.session_stats["api_requests"] += 1

            details_fetched = int(SyncMetadata.get(METADATA_KEY_DETAILS_FETCHED, "0"))
            SyncMetadata.set(METADATA_KEY_DETAILS_FETCHED, str(details_fetched + 1))

            try:
                from models.provider_settings import ProviderSettings

                if ProviderSettings.get("llm_enrichment", "enabled", "false").lower() == "true":
                    from services.ppv.context import build_event_context, generate_event_description_or_fallback
                    from services.ppv.context.assembler import persist_context_metadata

                    context = build_event_context(event)
                    persist_context_metadata(event, context)
                    description = generate_event_description_or_fallback(context)
                    if description:
                        event.description = description
                        event.data_completeness = "enriched"
                        db.session.commit()
            except Exception as llm_exc:
                logger.warning(f"LLM description enrichment failed for event {external_id}: {llm_exc}")

        except Exception as e:
            logger.error(f"Error fetching details for event {external_id}: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass

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
            logger.error(f"Error updating event {event.id} from API: {e}")
            db.session.rollback()
            return False

    def _sync_epg_for_event(self, event: Event) -> None:
        try:
            from services.ppv.epg import PPVEpgService

            PPVEpgService.sync_ppv_event_to_epg_channels(event)
        except Exception as e:
            logger.warning(f"Failed to sync EPG for event {event.external_id}: {e}")
