"""
Persist PPV match results to Event and EventChannelLink tables.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Iterable, Optional, Tuple

from models import Channel, Event, EventChannelLink, db
from services.datetime_utils import to_naive_utc
from services.ppv.constants import MAX_EVENT_AGE_DAYS, MAX_EVENT_FUTURE_DAYS
from services.thesportsdb_calendar_scraper import CalendarEvent

logger = logging.getLogger(__name__)


def create_or_update_event(calendar_event: CalendarEvent) -> Tuple[Optional[Event], bool]:
    """Create or update an Event from calendar scraper data.

    Returns:
        (event, was_created) — event is None when validation rejects the calendar row.
    """
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
                return None, False
            if days_diff > MAX_EVENT_FUTURE_DAYS:
                logger.warning(
                    "Rejecting far-future event: %s @ %s (%s days ahead)",
                    calendar_event.event_name,
                    event_date,
                    days_diff,
                )
                return None, False

        event_source = getattr(calendar_event, "source", None) or Event.SOURCE_THESPORTSDB
        if event_source == "mlb_stats_api":
            event_source = Event.SOURCE_MLB_STATS

        event = Event.query.filter_by(
            external_id=calendar_event.event_id,
            source=event_source,
        ).first()

        if event:
            if calendar_event.scheduled_at:
                event.scheduled_at = to_naive_utc(calendar_event.scheduled_at)
            if calendar_event.timezone:
                event.timezone = calendar_event.timezone
            if calendar_event.home_team:
                event.home_team_name = calendar_event.home_team
            if calendar_event.away_team:
                event.away_team_name = calendar_event.away_team
            if calendar_event.event_name:
                event.title = calendar_event.event_name
            if calendar_event.league_name:
                event.league_name = calendar_event.league_name
            if getattr(calendar_event, "home_team_id", None):
                event.home_team_id = calendar_event.home_team_id
            if getattr(calendar_event, "away_team_id", None):
                event.away_team_id = calendar_event.away_team_id
            if getattr(calendar_event, "sport", None):
                event.sport = calendar_event.sport
            return event, False

        event = Event(
            external_id=calendar_event.event_id,
            source=event_source,
            title=calendar_event.event_name,
            sport=getattr(calendar_event, "sport", None) or "MiLB",
            home_team_id=getattr(calendar_event, "home_team_id", None) or "",
            home_team_name=calendar_event.home_team or "Unknown",
            away_team_id=getattr(calendar_event, "away_team_id", None) or "",
            away_team_name=calendar_event.away_team or "Unknown",
            league_name=calendar_event.league_name,
            scheduled_at=to_naive_utc(calendar_event.scheduled_at)
            if calendar_event.scheduled_at
            else datetime.now(timezone.utc).replace(tzinfo=None),
            timezone=calendar_event.timezone,
            is_ppv=True,
            data_completeness="basic",
            status=Event.STATUS_SCHEDULED,
        )
        db.session.add(event)
        return event, True

    except Exception as e:
        logger.error("Error creating event for %s: %s", calendar_event.event_id, e)
        return None, False


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
    if channel.is_ppv:
        channel.ppv_enrichment_status = "matched"
        channel.ppv_enrichment_error = None
    return link


def sync_enrichment_status_from_links(channel_ids: Optional[Iterable[int]] = None) -> int:
    """Set ppv_enrichment_status=matched on PPV channels that have event links."""
    query = db.session.query(EventChannelLink.channel_id).distinct()
    if channel_ids is not None:
        ids = list(channel_ids)
        if not ids:
            return 0
        query = query.filter(EventChannelLink.channel_id.in_(ids))

    linked_ids = [row[0] for row in query.all()]
    if not linked_ids:
        return 0

    return Channel.query.filter(
        Channel.id.in_(linked_ids),
        Channel.is_ppv.is_(True),
        Channel.ppv_enrichment_status != "matched",
    ).update(
        {
            Channel.ppv_enrichment_status: "matched",
            Channel.ppv_enrichment_error: None,
        },
        synchronize_session=False,
    )


def clear_event_links_for_channels(channel_ids: Iterable[int]) -> int:
    """Remove event links when channels are re-queued for enrichment."""
    ids = list(channel_ids)
    if not ids:
        return 0
    return EventChannelLink.query.filter(EventChannelLink.channel_id.in_(ids)).delete(synchronize_session=False)


def persist_match(
    channel: Channel,
    calendar_event: CalendarEvent,
    confidence: float,
    match_method: str,
) -> Tuple[Optional[Event], bool]:
    """
    Persist a calendar match for a channel.

    Returns:
        (event, was_created) — event is None if validation or persistence failed.
    """
    event, was_created = create_or_update_event(calendar_event)
    if not event:
        channel.ppv_enrichment_status = "no_match"
        channel.ppv_enrichment_error = None
        return None, False

    try:
        db.session.flush()
        link_channel_to_event(channel, event, confidence, match_method)
        channel.ppv_enrichment_status = "matched"
        channel.ppv_enrichment_error = None
        return event, was_created
    except Exception as e:
        logger.error(
            "Error persisting match for channel %s event %s: %s",
            channel.id,
            calendar_event.event_id,
            e,
        )
        db.session.rollback()
        channel.ppv_enrichment_status = "retry_pending"
        channel.ppv_enrichment_error = str(e)
        return None, False


def persist_enhanced_match(
    channel: Channel,
    match_result: Any,
) -> Tuple[Optional[Event], bool]:
    """
    Persist a match from EnhancedPPVMatcher (EnhancedMatchResult).

    Returns (event, was_created). No-op if match_result has no event.
    """
    if not match_result or not getattr(match_result, "event", None):
        return None, False

    cal_event = match_result.event
    if not isinstance(cal_event, CalendarEvent):
        return None, False

    confidence = float(getattr(match_result, "confidence", 0.0) or 0.0)
    method = str(getattr(match_result, "match_method", "enhanced") or "enhanced")
    return persist_match(channel, cal_event, confidence, method)
