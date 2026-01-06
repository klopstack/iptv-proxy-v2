"""
PPV Event Enrichment Service v2

Redesigned enrichment workflow that uses calendar scraping instead of API for bulk discovery.

Workflow:
1. Primary Thread (Calendar-based matching):
   - Extract event info from channel name using PPVEventExtractor
   - Filter out placeholders, inactive channels, no-extraction cases
   - Group channels by inferred date
   - Fetch calendar pages for each unique date (cached)
   - Match channels to calendar events using fuzzy matching
   - Create Event records with event_id and basic info
   - Queue matched events for detailed enrichment

2. Secondary Thread (API detail fetching):
   - Process queue of event_ids that need full details
   - Rate limited to 30 requests/minute
   - Fetch full event details from TheSportsDB API
   - Update Event records with complete information
   - Mark channels as fully enriched

Benefits:
- Calendar scraping has no API rate limits
- One calendar request returns all events for a day
- API calls only needed for events that actually match
- Much faster initial matching phase
"""

import logging
import random
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask

from models import Channel, Event, EventChannelLink, SyncMetadata, db
from services.ppv_event_extractor import PPVEventExtractor
from services.reverse_event_matcher.orchestrator import ReverseEventMatcher
from services.thesportsdb_calendar_scraper import CalendarEvent, get_calendar_scraper
from services.thesportsdb_service import TheSportsDBService

logger = logging.getLogger(__name__)

# Rate limiting for API (used only for event detail fetching)
API_REQUESTS_PER_MINUTE = 30  # TheSportsDB official limit
API_REQUEST_INTERVAL = 60.0 / API_REQUESTS_PER_MINUTE  # ~2 seconds between requests

# Jitter for calendar requests (to avoid bot detection)
CALENDAR_REQUEST_MIN_DELAY = 0.5  # Minimum delay between calendar requests (seconds)
CALENDAR_REQUEST_MAX_DELAY = 3.0  # Maximum delay between calendar requests (seconds)

# Processing configuration
ENRICHMENT_BATCH_SIZE = 100  # Channels to process per batch (larger since no API limits)
DETAIL_FETCH_BATCH_SIZE = 25  # Events to fetch details for per minute
MAX_RETRY_ATTEMPTS = 3

# Match confidence thresholds
MIN_MATCH_CONFIDENCE = 0.35  # Minimum confidence to consider a match (lowered to accept partial team name matches)
MEDIUM_CONFIDENCE_THRESHOLD = 0.6  # Above this, accept without ambiguity check
HIGH_CONFIDENCE_THRESHOLD = 0.7  # Above this, we're highly confident in the match

# Event age validation
MAX_EVENT_AGE_DAYS = 30  # Reject events older than this
MAX_EVENT_FUTURE_DAYS = 365  # Reject events further in future than this

# Generic channel name patterns that indicate inactive/placeholder channels
# These channels typically don't have actual events broadcasting
GENERIC_CHANNEL_PATTERNS = [
    r"^PPV\s*\d+$",  # "PPV 1", "PPV 23"
    r"^PPV\s*Event\s*\d*$",  # "PPV Event", "PPV Event 1"
    r"^UFC\s*Event\s*\d*$",  # "UFC Event", "UFC Event 1"
    r"^Boxing\s*Event\s*\d*$",  # "Boxing Event"
    r"^MMA\s*Event\s*\d*$",  # "MMA Event"
    r"^Sports?\s*Event\s*\d*$",  # "Sport Event", "Sports Event 1"
    r"^Live\s*Event\s*\d*$",  # "Live Event"
    r"^Event\s*\d+$",  # "Event 1", "Event 23"
    r"^\d+\s*-\s*PPV",  # "1 - PPV", "23 - PPV"
    r"^PPV\s*HD\s*\d*$",  # "PPV HD", "PPV HD 1"
    r"^\(.*\)$",  # Just provider info like "(ESPN)" or "(Fanatiz 012)"
]

# Metadata keys
METADATA_KEY_CALENDAR_PROCESSED = "ppv_calendar_processed_count"
METADATA_KEY_CALENDAR_MATCHED = "ppv_calendar_matched_count"
METADATA_KEY_DETAIL_QUEUE_SIZE = "ppv_detail_queue_size"
METADATA_KEY_DETAILS_FETCHED = "ppv_details_fetched_count"


class EnrichmentResult:
    """Result of attempting to enrich a channel."""

    def __init__(
        self,
        channel: Channel,
        matched: bool,
        event: Optional[Event] = None,
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


def is_generic_channel_name(channel_name: str) -> bool:
    """
    Check if a channel name is generic/placeholder-like.

    Generic names like "PPV 1", "UFC Event", etc. indicate the channel
    is not currently broadcasting an actual event and should be filtered.

    Args:
        channel_name: Channel name to check

    Returns:
        True if the name is generic/placeholder-like
    """
    import re

    name = channel_name.strip()
    for pattern in GENERIC_CHANNEL_PATTERNS:
        if re.match(pattern, name, re.IGNORECASE):
            return True
    return False


class PPVCalendarEnrichmentService:
    """
    Calendar-based PPV enrichment service.

    Uses HTML scraping of TheSportsDB calendar pages for bulk event discovery,
    then API calls only for fetching full details of matched events.
    """

    def __init__(self, app: Flask):
        """
        Initialize the enrichment service.

        Args:
            app: Flask application instance
        """
        self.app = app
        self.extractor = PPVEventExtractor()
        self.calendar_scraper = get_calendar_scraper()
        self.reverse_matcher = ReverseEventMatcher(calendar_scraper=self.calendar_scraper)
        self.thesportsdb = TheSportsDBService()

        # Queue for events needing detail fetch (secondary thread)
        self._detail_queue: Queue[str] = Queue()  # Queue of event_ids
        self._detail_thread: Optional[threading.Thread] = None
        self._stop_detail_thread = threading.Event()

        # Statistics
        self._stats = {
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_extraction": 0,
            "channels_no_match": 0,
            "calendar_requests": 0,
            "api_requests": 0,
        }

    def enrich_channels(self, channels: List[Channel], fetch_details: bool = True) -> Dict[str, Any]:
        """
        Enrich a list of PPV channels using calendar scraping.

        Args:
            channels: List of Channel objects to enrich
            fetch_details: If True, also fetch full event details via API

        Returns:
            Dict with enrichment statistics
        """
        with self.app.app_context():
            results = {
                "total_channels": len(channels),
                "processed": 0,
                "matched": 0,
                "no_extraction": 0,
                "no_match": 0,
                "errors": 0,
                "events_created": 0,
                "events_updated": 0,
                "calendar_requests_made": 0,
                "detail_queue_size": 0,
            }

            # Step 1: Extract event info from all channels
            extraction_results = self._extract_all_channels(channels)

            # Step 2: Filter out no-extraction cases with detailed tracking
            filter_reasons: Dict[str, int] = defaultdict(int)
            valid_extractions = []

            for ch, ex in extraction_results:
                # Check various filter conditions
                if ex["is_placeholder"]:
                    filter_reasons["placeholder"] += 1
                    continue
                if ex.get("is_inactive", False):
                    filter_reasons["inactive"] += 1
                    continue
                if is_generic_channel_name(ch.name):
                    filter_reasons["generic_name"] += 1
                    continue
                if not ex.get("competitors"):
                    # Log unusual case: has date but no competitors
                    if ex.get("date") or ex.get("time_only"):
                        logger.debug(
                            f"Channel has date but no competitors: '{ch.name}' - "
                            f"date={ex.get('date')}, time={ex.get('time_only')}, inferred_how={ex.get('inferred_how')}"
                        )
                        filter_reasons["date_but_no_competitors"] += 1
                    else:
                        filter_reasons["no_competitors"] += 1
                    continue

                valid_extractions.append((ch, ex))

            no_extraction_count = len(extraction_results) - len(valid_extractions)
            results["no_extraction"] = no_extraction_count

            # Log filter breakdown
            if filter_reasons:
                logger.info(f"Filtered out {no_extraction_count} channels: {dict(filter_reasons)}")

            logger.info(
                f"Extracted info from {len(valid_extractions)} channels, " f"{no_extraction_count} filtered out"
            )

            # Step 3: Group channels by inferred date
            channels_by_date = self._group_by_date(valid_extractions)
            unique_dates = list(channels_by_date.keys())
            logger.info(f"Channels grouped into {len(unique_dates)} unique dates")

            # Step 4: Fetch calendar data for each unique date (cached)
            calendar_data = {}
            for date_str in unique_dates:
                events = self.calendar_scraper.get_events_for_date(date_str)
                calendar_data[date_str] = events
                results["calendar_requests_made"] += 1

                # Add jitter to avoid bot detection
                if date_str != unique_dates[-1]:  # Don't sleep after last request
                    jitter_delay = random.uniform(CALENDAR_REQUEST_MIN_DELAY, CALENDAR_REQUEST_MAX_DELAY)
                    time.sleep(jitter_delay)

            logger.info(
                f"Loaded calendar data for {len(unique_dates)} dates, "
                f"total {sum(len(e) for e in calendar_data.values())} events"
            )

            # Step 5: Match channels to calendar events
            event_ids_to_fetch = set()
            match_failure_reasons: Dict[str, int] = defaultdict(int)

            for date_str, channel_extractions in channels_by_date.items():
                calendar_events = calendar_data.get(date_str, [])

                for channel, extraction in channel_extractions:
                    result = self._match_channel_to_calendar(channel, extraction, calendar_events, date_str)

                    results["processed"] += 1

                    if result.matched:
                        results["matched"] += 1

                        # Create or get event record (calendar_event is set when matched)
                        if result.calendar_event:
                            event = self._create_or_update_event(result.calendar_event)
                            if event:
                                results["events_created"] += 1

                                # Link channel to event
                                self._link_channel_to_event(channel, event, result.confidence, result.match_method)

                                # Queue for detail fetch
                                event_ids_to_fetch.add(result.calendar_event.event_id)

                                # Update channel status
                                channel.ppv_enrichment_status = "matched"
                        else:
                            # Should never happen if matched is True, but handle gracefully
                            channel.ppv_enrichment_status = "no_match"
                    else:
                        results["no_match"] += 1
                        match_failure_reasons[result.match_method] += 1

                        # Log detailed info for failed matches (sample to avoid log spam)
                        if results["no_match"] <= 10 or results["no_match"] % 100 == 0:
                            competitors = extraction.get("competitors")
                            logger.debug(
                                f"No match for '{channel.name}': "
                                f"competitors={competitors}, "
                                f"date={date_str}, "
                                f"time={extraction.get('time_only')}, "
                                f"reason={result.match_method}, "
                                f"calendar_events_count={len(calendar_events)}"
                            )

                        channel.ppv_enrichment_status = "no_match"

                    db.session.commit()

            # Log match failure breakdown
            if match_failure_reasons:
                logger.info(f"Match failure breakdown: {dict(match_failure_reasons)}")

            results["detail_queue_size"] = len(event_ids_to_fetch)

            # Step 6: Queue events for detail fetching (if requested)
            if fetch_details and event_ids_to_fetch:
                for event_id in event_ids_to_fetch:
                    self._detail_queue.put(event_id)

                logger.info(f"Queued {len(event_ids_to_fetch)} events for detail fetching")

                # Auto-start the detail fetcher thread if not running
                if not self._detail_thread or not self._detail_thread.is_alive():
                    self.start_detail_fetcher()

            # Update persistent stats
            self._update_stats(results)

            # Auto-create PPV EPG source if events were created/updated
            if results.get("events_created", 0) > 0 or results.get("events_updated", 0) > 0:
                try:
                    from services.ppv_epg_service import PPVEpgService

                    source_id = PPVEpgService.create_epg_source_for_ppv_events()
                    logger.info(f"Auto-created/verified PPV EPG source with ID: {source_id}")

                    # Sync events to EPG channels
                    created, updated = PPVEpgService.sync_ppv_events_to_epg_channels(source_id)
                    logger.info(f"Synced PPV events to EPG: {created} created, {updated} updated")

                    # Auto-match PPV channels to the EPG
                    from services.epg_match_rules_service import EpgMatchRulesService

                    match_stats = EpgMatchRulesService.match_ppv_channels_to_epg(source_id=source_id, batch_size=100)
                    logger.info(
                        f"Auto-matched PPV channels: {match_stats.get('matched_count', 0)} matched, "
                        f"{match_stats.get('unmatched_count', 0)} unmatched"
                    )
                    results["ppv_epg_matched"] = match_stats.get("matched_count", 0)
                except Exception as e:
                    logger.error(f"Failed to auto-create/match PPV EPG source: {e}")

            return results

    def _extract_all_channels(self, channels: List[Channel]) -> List[Tuple[Channel, Dict]]:
        """
        Extract event information from all channels.

        Args:
            channels: List of channels to process

        Returns:
            List of (channel, extraction_result) tuples
        """
        results = []
        for channel in channels:
            extraction = self.extractor.extract_all(channel.name)
            results.append((channel, extraction))
        return results

    def _group_by_date(self, channel_extractions: List[Tuple[Channel, Dict]]) -> Dict[str, List[Tuple[Channel, Dict]]]:
        """
        Group channels by their inferred event date.

        Args:
            channel_extractions: List of (channel, extraction_result) tuples

        Returns:
            Dict mapping date strings (YYYY-MM-DD) to lists of (channel, extraction)
        """
        by_date = defaultdict(list)

        for channel, extraction in channel_extractions:
            # Get the inferred date
            date_str = self._get_event_date(extraction)
            by_date[date_str].append((channel, extraction))

        return dict(by_date)

    def _get_event_date(self, extraction: Dict) -> str:
        """
        Determine the event date from extraction result.

        Priority:
        1. Explicit date from channel name
        2. Inferred date from weekday
        3. Inferred date from time (assume today if evening, tomorrow if morning)
        4. Default to today

        Args:
            extraction: Result from PPVEventExtractor.extract_all()

        Returns:
            Date string in YYYY-MM-DD format
        """
        # Check for explicit date
        if extraction.get("date"):
            date_obj = extraction["date"]
            if isinstance(date_obj, datetime):
                return date_obj.strftime("%Y-%m-%d")
            elif isinstance(date_obj, str):
                return date_obj

        # Check for inferred date
        inferred_how = extraction.get("inferred_how")
        if inferred_how in ("weekday", "time"):
            # Use the date inference from extractor
            if extraction.get("date"):
                date_obj = extraction["date"]
                if isinstance(date_obj, datetime):
                    return date_obj.strftime("%Y-%m-%d")

        # Default to today
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _match_channel_to_calendar(
        self,
        channel: Channel,
        extraction: Dict,
        calendar_events: List[CalendarEvent],
        date_str: str,
    ) -> EnrichmentResult:
        """
        Match a channel to a calendar event.

        Args:
            channel: Channel to match
            extraction: Extraction result from PPVEventExtractor
            calendar_events: List of CalendarEvent objects for the date
            date_str: Date string

        Returns:
            EnrichmentResult with match details
        """
        if not calendar_events:
            return EnrichmentResult(
                channel=channel,
                matched=False,
                extraction_result=extraction,
                match_method="no_calendar_events",
            )

        # Load events for this date range using ReverseEventMatcher
        # (it caches internally so multiple calls are efficient)
        self.reverse_matcher.load_events_for_date_range(
            start_date=date_str,
            end_date=date_str,  # Single day
            days_ahead=0,
            days_back=0,
        )

        # Use ReverseEventMatcher's find_matches method with date validation
        # IMPORTANT: use_channel_date=True enables extraction and validation of
        # the date from the channel name against event dates. This helps reject
        # mismatches like old replays (2025 events) being matched to new events.
        match_results = self.reverse_matcher.find_matches(
            channel_name=channel.name,
            max_results=5,
            min_confidence=MIN_MATCH_CONFIDENCE,
            use_channel_date=True,  # Enable date extraction and validation
        )

        # Convert MatchResult objects to (CalendarEvent, confidence) tuples
        # to maintain compatibility with existing code
        matches = [(result.event, result.confidence) for result in match_results]

        if not matches:
            return EnrichmentResult(
                channel=channel,
                matched=False,
                extraction_result=extraction,
                match_method="no_match_found",
            )

        # Get best match
        best_event, confidence = matches[0]

        if confidence < MIN_MATCH_CONFIDENCE:
            return EnrichmentResult(
                channel=channel,
                matched=False,
                extraction_result=extraction,
                match_method="confidence_too_low",
            )

        # For low-to-medium confidence matches (below 0.6), require a clear winner
        # to avoid accepting ambiguous matches where multiple events are equally plausible
        if confidence < MEDIUM_CONFIDENCE_THRESHOLD:
            # If there's a second match that's very close in confidence, reject
            # (ambiguous match - not confident enough to choose)
            if len(matches) > 1:
                second_confidence = matches[1][1]
                confidence_gap = confidence - second_confidence

                # For low confidence (0.35-0.5): require 0.2 gap to ensure it's the right match
                # For medium confidence (0.5-0.6): require 0.15 gap
                required_gap = 0.2 if confidence < 0.5 else 0.15

                if confidence_gap < required_gap:
                    logger.debug(
                        f"Rejecting ambiguous match for '{channel.name[:60]}': "
                        f"best={confidence:.2f}, second={second_confidence:.2f}, gap={confidence_gap:.2f} (required={required_gap:.2f})"
                    )
                    return EnrichmentResult(
                        channel=channel,
                        matched=False,
                        extraction_result=extraction,
                        match_method="ambiguous_match",
                    )

        # Determine match method based on confidence
        if confidence >= HIGH_CONFIDENCE_THRESHOLD:
            match_method = "calendar_high_confidence"
        elif confidence >= MEDIUM_CONFIDENCE_THRESHOLD:
            match_method = "calendar_medium_confidence"
        else:
            match_method = "calendar_low_confidence"

        return EnrichmentResult(
            channel=channel,
            matched=True,
            calendar_event=best_event,
            confidence=confidence,
            match_method=match_method,
            extraction_result=extraction,
        )

    def _create_or_update_event(self, calendar_event: CalendarEvent) -> Optional[Event]:
        """
        Create or update an Event record from calendar data.

        Args:
            calendar_event: CalendarEvent from scraper

        Returns:
            Event model instance, or None if event is invalid (e.g., too old)
        """
        try:
            # First, validate the event age before doing anything
            # This prevents storing old historical events (like 2014 Liverpool vs Swansea)
            if calendar_event.scheduled_at:
                now = datetime.now(timezone.utc)
                event_date = calendar_event.scheduled_at
                if event_date.tzinfo is None:
                    event_date = event_date.replace(tzinfo=timezone.utc)

                days_diff = (event_date - now).days

                # Check if event is too old
                if days_diff < -MAX_EVENT_AGE_DAYS:
                    logger.warning(
                        f"Rejecting old event: {calendar_event.event_name} @ {event_date} "
                        f"is {abs(days_diff)} days old (max: {MAX_EVENT_AGE_DAYS})"
                    )
                    return None

                # Check if event is too far in the future
                if days_diff > MAX_EVENT_FUTURE_DAYS:
                    logger.warning(
                        f"Rejecting future event: {calendar_event.event_name} @ {event_date} "
                        f"is {days_diff} days in the future (max: {MAX_EVENT_FUTURE_DAYS})"
                    )
                    return None

            # Check if event already exists
            event = Event.query.filter_by(
                external_id=calendar_event.event_id,
                source=Event.SOURCE_THESPORTSDB,
            ).first()

            if event:
                # Update with any new info
                if not event.scheduled_at and calendar_event.scheduled_at:
                    event.scheduled_at = calendar_event.scheduled_at
                return event

            # Create new event
            # Note: Model has nullable=False for team IDs/names, so we provide defaults
            # The IDs will be populated when we fetch full details from API
            event = Event(
                external_id=calendar_event.event_id,
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="",  # Will be populated by detail fetch
                home_team_name=calendar_event.home_team or "Unknown",
                away_team_id="",  # Will be populated by detail fetch
                away_team_name=calendar_event.away_team or "Unknown",
                league_name=calendar_event.league_name,
                scheduled_at=calendar_event.scheduled_at or datetime.now(timezone.utc),
                is_ppv=True,
                data_completeness="basic",  # Only have calendar data, not full details
                status=Event.STATUS_SCHEDULED,
            )

            db.session.add(event)
            return event

        except Exception as e:
            logger.error(f"Error creating event for {calendar_event.event_id}: {e}")
            return None

    def _link_channel_to_event(
        self,
        channel: Channel,
        event: Event,
        confidence: float,
        match_method: str,
    ) -> None:
        """
        Create a link between a channel and an event.

        Args:
            channel: Channel model
            event: Event model
            confidence: Match confidence score
            match_method: How the match was made
        """
        try:
            # Check if link already exists
            existing = EventChannelLink.query.filter_by(
                event_id=event.id,
                channel_id=channel.id,
            ).first()

            if existing:
                # Update confidence if new match is better
                if confidence > existing.match_confidence:
                    existing.match_confidence = confidence
                    existing.match_method = match_method
                return

            # Create new link
            link = EventChannelLink(
                event_id=event.id,
                channel_id=channel.id,
                match_confidence=confidence,
                match_method=match_method,
                feed_type="primary",
            )
            db.session.add(link)

        except Exception as e:
            logger.error(f"Error linking channel {channel.id} to event {event.id}: {e}")

    # =========================================================================
    # Secondary Thread: API Detail Fetching
    # =========================================================================

    def start_detail_fetcher(self) -> None:
        """Start the background thread for fetching event details."""
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

    def stop_detail_fetcher(self) -> None:
        """Stop the background detail fetcher thread."""
        self._stop_detail_thread.set()
        if self._detail_thread:
            self._detail_thread.join(timeout=10)
            logger.info("Stopped PPV detail fetcher thread")

    def _detail_fetch_loop(self) -> None:
        """
        Background loop for fetching event details from API.

        Rate limited to 30 requests/minute.
        """
        logger.info("Detail fetch loop started")

        # Create an app context for the entire thread lifetime
        # This is necessary because Flask contexts are thread-local
        ctx = self.app.app_context()
        ctx.push()

        try:
            while not self._stop_detail_thread.is_set():
                try:
                    # Get next event ID from queue (with timeout)
                    event_id = self._detail_queue.get(timeout=5.0)

                    # Fetch details from API
                    self._fetch_event_details(event_id)

                    # Rate limit: wait between requests
                    time.sleep(API_REQUEST_INTERVAL)

                    self._detail_queue.task_done()

                except Empty:
                    # Queue empty, just continue waiting
                    continue
                except Exception as e:
                    logger.error(f"Error in detail fetch loop: {e}", exc_info=True)
                    time.sleep(1)  # Brief pause on error
        finally:
            ctx.pop()

        logger.info("Detail fetch loop stopped")

    def _fetch_event_details(self, event_id: str) -> None:
        """
        Fetch full event details from TheSportsDB API.

        Note: This method must be called within an app context.

        Args:
            event_id: TheSportsDB event ID
        """
        try:
            # Find the event in our database
            event = Event.query.filter_by(
                external_id=event_id,
                source=Event.SOURCE_THESPORTSDB,
            ).first()

            if not event:
                logger.warning(f"Event {event_id} not found in database")
                return

            # Skip if already has full details
            if event.data_completeness == "full":
                logger.debug(f"Event {event_id} already has full details")
                return

            # Fetch from API
            api_data = self.thesportsdb.get_event_by_id(event_id)

            if not api_data:
                logger.warning(f"No API data returned for event {event_id}")
                return

            # Update event with full details
            self._update_event_from_api(event, api_data)

            logger.info(f"Fetched full details for event {event_id}")
            self._stats["api_requests"] += 1

        except Exception as e:
            logger.error(f"Error fetching details for event {event_id}: {e}")
            try:
                db.session.rollback()
            except Exception:
                pass  # Ignore rollback errors

    def _update_event_from_api(self, event: Event, api_data: Dict) -> None:
        """
        Update an Event record with full API data.

        Args:
            event: Event model to update
            api_data: Data from TheSportsDB API
        """
        try:
            # Update basic info
            event.sport = api_data.get("strSport", event.sport)
            event.league_name = api_data.get("strLeague", event.league_name)
            event.league_id = api_data.get("idLeague")

            # Update teams
            event.home_team_name = api_data.get("strHomeTeam", event.home_team_name)
            event.home_team_id = api_data.get("idHomeTeam")
            event.away_team_name = api_data.get("strAwayTeam", event.away_team_name)
            event.away_team_id = api_data.get("idAwayTeam")

            # Update scheduling
            scheduled_str = api_data.get("strTimestamp") or api_data.get("dateEvent")
            if scheduled_str:
                try:
                    if "T" in scheduled_str:
                        event.scheduled_at = datetime.fromisoformat(scheduled_str.replace("Z", "+00:00"))
                    else:
                        event.scheduled_at = datetime.strptime(scheduled_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    pass

            # Update venue info
            event.venue_name = api_data.get("strVenue")
            event.city = api_data.get("strCity")
            event.country = api_data.get("strCountry")

            # Update poster/thumbnail
            event.event_image = api_data.get("strPoster") or api_data.get("strThumb")

            # Update status
            status_str = (api_data.get("strStatus") or "").lower()
            if "finished" in status_str or "ft" == status_str:
                event.status = Event.STATUS_FINISHED
            elif "live" in status_str or "in progress" in status_str:
                event.status = Event.STATUS_LIVE
            elif "cancelled" in status_str or "postponed" in status_str:
                event.status = Event.STATUS_CANCELLED

            # Mark as having full details
            event.data_completeness = "full"
            event.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)

            db.session.commit()

        except Exception as e:
            logger.error(f"Error updating event {event.id} from API: {e}")
            db.session.rollback()

    def _update_stats(self, results: Dict) -> None:
        """Update persistent statistics."""
        try:
            processed = int(SyncMetadata.get(METADATA_KEY_CALENDAR_PROCESSED, "0"))
            processed += results["processed"]
            SyncMetadata.set(METADATA_KEY_CALENDAR_PROCESSED, str(processed))

            matched = int(SyncMetadata.get(METADATA_KEY_CALENDAR_MATCHED, "0"))
            matched += results["matched"]
            SyncMetadata.set(METADATA_KEY_CALENDAR_MATCHED, str(matched))

        except Exception as e:
            logger.error(f"Error updating stats: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get current enrichment service status."""
        return {
            "detail_queue_size": self._detail_queue.qsize(),
            "detail_thread_running": (self._detail_thread.is_alive() if self._detail_thread else False),
            "calendar_cache_stats": self.calendar_scraper.get_cache_stats(),
            "cumulative_stats": {
                "calendar_processed": SyncMetadata.get(METADATA_KEY_CALENDAR_PROCESSED, "0"),
                "calendar_matched": SyncMetadata.get(METADATA_KEY_CALENDAR_MATCHED, "0"),
                "details_fetched": SyncMetadata.get(METADATA_KEY_DETAILS_FETCHED, "0"),
            },
            "session_stats": self._stats.copy(),
        }


# =========================================================================
# Convenience Functions
# =========================================================================

_service_instance: Optional[PPVCalendarEnrichmentService] = None


def get_calendar_enrichment_service(app: Flask) -> PPVCalendarEnrichmentService:
    """Get or create the calendar enrichment service singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = PPVCalendarEnrichmentService(app)
    return _service_instance


def enrich_ppv_channels_batch(app: Flask, account_id: int) -> Dict[str, Any]:
    """
    Convenience function to enrich all PPV channels for an account.

    Args:
        app: Flask application
        account_id: Account ID to process

    Returns:
        Enrichment results
    """
    with app.app_context():
        channels = Channel.query.filter(
            Channel.account_id == account_id,
            Channel.is_ppv.is_(True),
        ).all()

        if not channels:
            return {"error": "No PPV channels found for account"}

        service = get_calendar_enrichment_service(app)
        return service.enrich_channels(channels)
