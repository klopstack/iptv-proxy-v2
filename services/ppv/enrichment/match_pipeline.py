"""Calendar extract → classify → group → match → persist pipeline."""

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from models import Channel, Event, db
from services.ppv.constants import (
    HIGH_CONFIDENCE_THRESHOLD,
    MATCH_AMBIGUITY_GAP_LOW,
    MATCH_AMBIGUITY_GAP_MEDIUM,
    MATCH_AMBIGUITY_LOW_CONFIDENCE_CUTOFF,
    MEDIUM_CONFIDENCE_THRESHOLD,
    MIN_MATCH_CONFIDENCE,
)
from services.ppv.enrichability import classify_ppv_enrichment, skip_error_message
from services.ppv.enrichment.types import DetailQueueItem, EnrichmentResult, calendar_event_source
from services.ppv.extraction import PPVEventExtractor
from services.ppv.matching.context import context_for_event, resolve_sport_league_context
from services.ppv.matching.validation import competitors_match_event
from services.ppv.persistence import persist_match
from services.reverse_event_matcher.orchestrator import ReverseEventMatcher
from services.thesportsdb_calendar_scraper import CalendarEvent, get_calendar_scraper

logger = logging.getLogger(__name__)


class CalendarMatchPipeline:
    """Extract, classify, group, match, and persist PPV channels against calendar data."""

    def __init__(
        self,
        extractor: Optional[PPVEventExtractor] = None,
        calendar_scraper=None,
        reverse_matcher: Optional[ReverseEventMatcher] = None,
    ):
        self.extractor = extractor or PPVEventExtractor()
        self.calendar_scraper = calendar_scraper or get_calendar_scraper()
        self.reverse_matcher = reverse_matcher or ReverseEventMatcher(calendar_scraper=self.calendar_scraper)

    def run(
        self,
        channels: List[Channel],
        coordinator: Optional[Any] = None,
    ) -> Tuple[Dict[str, Any], Set[DetailQueueItem]]:
        """
        Run the calendar match pipeline for a channel batch.

        When ``coordinator`` is provided (PPVCalendarEnrichmentService), extraction
        and grouping delegate to it so tests can patch ``_extract_all_channels`` /
        ``_group_by_date`` on the service.

        Returns:
            (results dict, event_ids to queue for detail fetch)
        """
        extract_fn = coordinator._extract_all_channels if coordinator is not None else self.extract_all_channels
        group_fn = coordinator._group_by_date if coordinator is not None else self.group_by_date
        match_fn = coordinator._match_channel_to_calendar if coordinator is not None else self.match_channel_to_calendar
        results: Dict[str, Any] = {
            "total_channels": len(channels),
            "processed": 0,
            "matched": 0,
            "no_extraction": 0,
            "no_match": 0,
            "channels_skipped": 0,
            "errors": 0,
            "events_created": 0,
            "events_updated": 0,
            "calendar_requests_made": 0,
            "detail_queue_size": 0,
            "far_future_skipped": 0,
        }

        extraction_results = extract_fn(channels)

        filter_reasons: Dict[str, int] = defaultdict(int)
        valid_extractions = []

        for ch, ex in extraction_results:
            skip_reason = classify_ppv_enrichment(ch.name, ex)
            if skip_reason is not None:
                filter_reasons[skip_reason] += 1
                if ch.ppv_enrichment_status in (None, "queued", "retry_pending"):
                    ch.ppv_enrichment_status = "skipped"
                    ch.ppv_enrichment_error = skip_error_message(skip_reason)
                    results["channels_skipped"] += 1
                continue

            valid_extractions.append((ch, ex))

        no_extraction_count = len(extraction_results) - len(valid_extractions)
        results["no_extraction"] = no_extraction_count
        results["far_future_skipped"] = filter_reasons.get("far_future", 0)

        if filter_reasons:
            logger.info(f"Filtered out {no_extraction_count} channels: {dict(filter_reasons)}")

        logger.info(f"Extracted info from {len(valid_extractions)} channels, " f"{no_extraction_count} filtered out")

        if results["channels_skipped"]:
            try:
                db.session.commit()
            except Exception as e:
                logger.error("Error committing skipped channel statuses: %s", e, exc_info=True)
                db.session.rollback()

        event_ids_to_fetch: Set[DetailQueueItem] = set()

        if not valid_extractions:
            results["detail_queue_size"] = 0
            return results, event_ids_to_fetch

        channels_by_date = group_fn(valid_extractions)
        unique_dates = list(channels_by_date.keys())
        logger.info(f"Channels grouped into {len(unique_dates)} unique dates")

        calendar_data = {}
        for date_str in unique_dates:
            events = self.calendar_scraper.get_events_for_date(date_str)
            calendar_data[date_str] = events
            results["calendar_requests_made"] += 1

        logger.info(
            f"Loaded calendar data for {len(unique_dates)} dates, "
            f"total {sum(len(e) for e in calendar_data.values())} events"
        )

        match_failure_reasons: Dict[str, int] = defaultdict(int)

        for date_str, channel_extractions in channels_by_date.items():
            calendar_events = calendar_data.get(date_str, [])

            self.reverse_matcher.load_events_for_date_range(
                start_date=date_str,
                end_date=date_str,
                days_ahead=0,
                days_back=0,
            )

            for channel, extraction in channel_extractions:
                result = match_fn(channel, extraction, calendar_events, date_str, index_loaded=True)

                results["processed"] += 1

                if result.matched:
                    results["matched"] += 1

                    if result.calendar_event:
                        event, was_created = persist_match(
                            channel,
                            result.calendar_event,
                            result.confidence,
                            result.match_method,
                        )
                        if event:
                            if was_created:
                                results["events_created"] += 1
                            else:
                                results["events_updated"] += 1
                            event_source = calendar_event_source(result.calendar_event)
                            if event_source == Event.SOURCE_THESPORTSDB:
                                event_ids_to_fetch.add((result.calendar_event.event_id, event_source))
                        elif channel.ppv_enrichment_status == "retry_pending":
                            results["errors"] += 1
                    else:
                        channel.ppv_enrichment_status = "no_match"
                else:
                    results["no_match"] += 1
                    match_failure_reasons[result.match_method] += 1

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

            try:
                db.session.commit()
            except Exception as e:
                logger.error("Error committing enrichment batch for date %s: %s", date_str, e, exc_info=True)
                db.session.rollback()

        if match_failure_reasons:
            logger.info(f"Match failure breakdown: {dict(match_failure_reasons)}")

        results["detail_queue_size"] = len(event_ids_to_fetch)
        return results, event_ids_to_fetch

    def extract_all_channels(self, channels: List[Channel]) -> List[Tuple[Channel, Dict]]:
        results = []
        for channel in channels:
            extraction = self.extractor.extract_all(channel.name)
            results.append((channel, extraction))
        return results

    def group_by_date(self, channel_extractions: List[Tuple[Channel, Dict]]) -> Dict[str, List[Tuple[Channel, Dict]]]:
        from services.ppv.channel_matching import build_channel_matching_context

        by_date = defaultdict(list)

        for channel, extraction in channel_extractions:
            ctx = build_channel_matching_context(channel, extraction)
            date_str = ctx.get("calendar_date") or self.get_event_date(extraction)
            extraction["_matching_context"] = ctx
            by_date[date_str].append((channel, extraction))

        return dict(by_date)

    def get_event_date(self, extraction: Dict) -> str:
        if extraction.get("date"):
            date_obj = extraction["date"]
            if isinstance(date_obj, datetime):
                return date_obj.strftime("%Y-%m-%d")
            elif isinstance(date_obj, str):
                return date_obj

        inferred_how = extraction.get("inferred_how")
        if inferred_how in ("weekday", "time"):
            if extraction.get("date"):
                date_obj = extraction["date"]
                if isinstance(date_obj, datetime):
                    return date_obj.strftime("%Y-%m-%d")

        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def match_channel_to_calendar(
        self,
        channel: Channel,
        extraction: Dict,
        calendar_events: List[CalendarEvent],
        date_str: str,
        *,
        index_loaded: bool = False,
    ) -> EnrichmentResult:
        if not calendar_events:
            return EnrichmentResult(
                channel=channel,
                matched=False,
                extraction_result=extraction,
                match_method="no_calendar_events",
            )

        if not index_loaded:
            self.reverse_matcher.load_events_for_date_range(
                start_date=date_str,
                end_date=date_str,
                days_ahead=0,
                days_back=0,
            )

        match_ctx = extraction.get("_matching_context") or {}
        channel_date_for_match = match_ctx.get("channel_date_for_match")
        match_results = self.reverse_matcher.find_matches(
            channel_name=channel.name,
            max_results=5,
            min_confidence=MIN_MATCH_CONFIDENCE,
            use_channel_date=channel_date_for_match is None,
            channel_date=channel_date_for_match,
            channel_timezone="UTC" if channel_date_for_match is not None else None,
            date_tolerance_hours=match_ctx.get("date_tolerance_hours"),
        )

        if not match_results:
            return EnrichmentResult(
                channel=channel,
                matched=False,
                extraction_result=extraction,
                match_method="no_match_found",
            )

        category_name = None
        category = getattr(channel, "category", None)
        if category is not None:
            raw_name = getattr(category, "category_name", None)
            if isinstance(raw_name, str):
                category_name = raw_name

        sport_context = resolve_sport_league_context(channel.name, category_name)
        if not sport_context.is_empty:
            match_results = [r for r in match_results if context_for_event(r.event, sport_context)]
            if not match_results:
                return EnrichmentResult(
                    channel=channel,
                    matched=False,
                    extraction_result=extraction,
                    match_method="league_context_mismatch",
                )

        competitors = extraction.get("competitors")
        if competitors and len(competitors) == 2:
            validated_results = []
            for result in match_results:
                if result.match_type != "both_teams" and not competitors_match_event(
                    competitors, result.event, context=sport_context
                ):
                    continue
                validated_results.append(result)
            if not validated_results:
                return EnrichmentResult(
                    channel=channel,
                    matched=False,
                    extraction_result=extraction,
                    match_method="competitor_mismatch",
                )
            match_results = validated_results

        matches = [(result.event, result.confidence) for result in match_results]
        best_event, confidence = matches[0]

        if confidence < MIN_MATCH_CONFIDENCE:
            return EnrichmentResult(
                channel=channel,
                matched=False,
                extraction_result=extraction,
                match_method="confidence_too_low",
            )

        if confidence < MEDIUM_CONFIDENCE_THRESHOLD:
            if len(matches) > 1:
                second_confidence = matches[1][1]
                confidence_gap = confidence - second_confidence

                required_gap = (
                    MATCH_AMBIGUITY_GAP_LOW
                    if confidence < MATCH_AMBIGUITY_LOW_CONFIDENCE_CUTOFF
                    else MATCH_AMBIGUITY_GAP_MEDIUM
                )

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
