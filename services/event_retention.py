"""Retention helpers for finished PPV/sports events."""

import logging
import os
from datetime import datetime, timedelta, timezone

from models import Event, EventChannelLink, db
from services.scheduler_constants import DEFAULT_EVENT_RETENTION_DAYS

logger = logging.getLogger(__name__)


def get_event_retention_days() -> int:
    """Return max age in days for events (override via EVENT_RETENTION_DAYS)."""
    raw = os.getenv("EVENT_RETENTION_DAYS")
    if raw:
        try:
            return max(1, int(raw))
        except ValueError:
            logger.warning("Invalid EVENT_RETENTION_DAYS=%r; using default", raw)
    return DEFAULT_EVENT_RETENTION_DAYS


def cleanup_old_events(max_age_days: int | None = None) -> int:
    """Delete events with scheduled_at older than the retention cutoff.

    Removes EventChannelLink rows first to satisfy foreign keys.

    Args:
        max_age_days: Override retention days (default from get_event_retention_days)

    Returns:
        Number of events deleted
    """
    if max_age_days is None:
        max_age_days = get_event_retention_days()

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff = now - timedelta(days=max_age_days)

    old_events = Event.query.filter(Event.scheduled_at < cutoff).all()
    if not old_events:
        return 0

    event_ids = [event.id for event in old_events]
    links_deleted = EventChannelLink.query.filter(EventChannelLink.event_id.in_(event_ids)).delete(
        synchronize_session=False
    )
    events_deleted = Event.query.filter(Event.id.in_(event_ids)).delete(synchronize_session=False)
    db.session.commit()
    logger.info(
        "Cleaned up %s event(s) and %s channel link(s) older than %s days",
        events_deleted,
        links_deleted,
        max_age_days,
    )
    return events_deleted
