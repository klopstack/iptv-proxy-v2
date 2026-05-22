"""
Persist PPV match results to Event and EventChannelLink tables.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from models import Channel, Event, EventChannelLink, db
from services.ppv.constants import MAX_EVENT_AGE_DAYS, MAX_EVENT_FUTURE_DAYS
from services.thesportsdb_calendar_scraper import CalendarEvent

logger = logging.getLogger(__name__)


def create_or_update_event(calendar_event: CalendarEvent) -> Optional[Event]:
    """Create or update an Event from calendar scraper data."""
    try:
        if calendar_event.scheduled_at:
            now = datetime.now(timezone.utc)
            event_date = calendar_event.scheduled_at
            if event_date.tzinfo is None:
                event_date = event_date.replace(tzinfo=timezone.utc)
            days_diff = (event_date - now).days
            if days_diff < -MAX_EVENT_AGE_DAYS:
                logger.warning(
                    "Rejecting old event: %s @ %s (%s days old)",
                    calendar_event.event_name,
                    event_date,
                    abs(days_diff),
                )
                return None
            if days_diff > MAX_EVENT_FUTURE_DAYS:
                logger.warning(
                    "Rejecting far-future event: %s @ %s (%s days ahead)",
                    calendar_event.event_name,
                    event_date,
                    days_diff,
                )
                return None

        event = Event.query.filter_by(
            external_id=calendar_event.event_id,
            source=Event.SOURCE_THESPORTSDB,
        ).first()

        if event:
            if not event.scheduled_at and calendar_event.scheduled_at:
                event.scheduled_at = calendar_event.scheduled_at
            return event

        event = Event(
            external_id=calendar_event.event_id,
            source=Event.SOURCE_THESPORTSDB,
            title=calendar_event.event_name,
            home_team_id="",
            home_team_name=calendar_event.home_team or "Unknown",
            away_team_id="",
            away_team_name=calendar_event.away_team or "Unknown",
            league_name=calendar_event.league_name,
            scheduled_at=calendar_event.scheduled_at or datetime.now(timezone.utc),
            is_ppv=True,
            data_completeness="basic",
            status=Event.STATUS_SCHEDULED,
        )
        db.session.add(event)
        return event

    except Exception as e:
        logger.error("Error creating event for %s: %s", calendar_event.event_id, e)
        return None


def link_channel_to_event(
    channel: Channel,
    event: Event,
    confidence: float,
    match_method: str,
) -> EventChannelLink:
    """Create or update EventChannelLink for a channel/event pair."""
    existing = EventChannelLink.query.filter_by(
        event_id=event.id,
        channel_id=channel.id,
    ).first()

    if existing:
        if confidence > existing.match_confidence:
            existing.match_confidence = confidence
            existing.match_method = match_method
        return existing

    link = EventChannelLink(
        event_id=event.id,
        channel_id=channel.id,
        match_confidence=confidence,
        match_method=match_method,
        feed_type="primary",
    )
    db.session.add(link)
    return link


def persist_match(
    channel: Channel,
    calendar_event: CalendarEvent,
    confidence: float,
    match_method: str,
) -> Tuple[Optional[Event], bool]:
    """
    Persist a calendar match for a channel.

    Returns:
        (event, created_new_link) — event is None if validation failed.
    """
    event = create_or_update_event(calendar_event)
    if not event:
        channel.ppv_enrichment_status = "no_match"
        return None, False

    db.session.flush()
    link_channel_to_event(channel, event, confidence, match_method)
    channel.ppv_enrichment_status = "matched"
    channel.ppv_enrichment_error = None
    return event, True


def persist_enhanced_match(
    channel: Channel,
    match_result: Any,
) -> Tuple[Optional[Event], bool]:
    """
    Persist a match from EnhancedPPVMatcher (EnhancedMatchResult).

    Returns (event, success). No-op if match_result has no event.
    """
    if not match_result or not getattr(match_result, "event", None):
        return None, False

    cal_event = match_result.event
    if not isinstance(cal_event, CalendarEvent):
        return None, False

    confidence = float(getattr(match_result, "confidence", 0.0) or 0.0)
    method = str(getattr(match_result, "match_method", "enhanced") or "enhanced")
    return persist_match(channel, cal_event, confidence, method)
