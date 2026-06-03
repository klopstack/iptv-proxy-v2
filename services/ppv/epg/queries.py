"""PPV event listing and detail queries."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, or_

from models import Channel, Event, EventChannelLink, db
from services.ppv.serializers import serialize_event_detail, serialize_event_summary, serialize_utc_iso


def list_ppv_events(
    mode: str = "all",
    account_id: Optional[int] = None,
    days_ahead: int = 7,
    status: Optional[str] = None,
    data_completeness: Optional[str] = None,
    search: Optional[str] = None,
    page: int = 1,
    per_page: int = 50,
) -> Dict[str, Any]:
    """List PPV events with filtering, pagination, and summary statistics."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    query = db.session.query(Event).filter(Event.is_ppv == True)  # noqa: E712

    if account_id:
        query = (
            query.join(EventChannelLink, Event.id == EventChannelLink.event_id)
            .join(Channel, EventChannelLink.channel_id == Channel.id)
            .filter(Channel.account_id == account_id)
            .distinct()
        )

    if mode == "upcoming":
        future = now + timedelta(days=days_ahead)
        query = query.filter(Event.scheduled_at >= now, Event.scheduled_at <= future)
    elif mode == "past":
        query = query.filter(Event.scheduled_at < now)

    if status:
        query = query.filter(Event.status == status)

    if data_completeness:
        query = query.filter(Event.data_completeness == data_completeness)

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Event.title.ilike(term),
                Event.home_team_name.ilike(term),
                Event.away_team_name.ilike(term),
                Event.league_name.ilike(term),
                Event.sport.ilike(term),
            )
        )

    total = query.count()

    status_rows = query.with_entities(Event.status, func.count(Event.id)).group_by(Event.status).all()
    by_status = {row[0] or "unknown": row[1] for row in status_rows}

    completeness_rows = (
        query.with_entities(Event.data_completeness, func.count(Event.id)).group_by(Event.data_completeness).all()
    )
    by_completeness = {row[0] or "unknown": row[1] for row in completeness_rows}

    per_page = max(1, min(per_page, 200))
    page = max(1, page)
    total_pages = max(1, (total + per_page - 1) // per_page) if total else 1
    if page > total_pages:
        page = total_pages

    offset = (page - 1) * per_page
    events = query.order_by(Event.scheduled_at.desc()).offset(offset).limit(per_page).all()

    event_ids = [event.id for event in events]
    channel_counts: Dict[int, int] = {}
    if event_ids:
        counts = (
            db.session.query(EventChannelLink.event_id, func.count(EventChannelLink.id))
            .filter(EventChannelLink.event_id.in_(event_ids))
            .group_by(EventChannelLink.event_id)
            .all()
        )
        channel_counts = {event_id: count for event_id, count in counts}

    return {
        "events": [
            serialize_event_summary(event, channel_count=channel_counts.get(event.id, 0)) for event in events
        ],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
        },
        "summary": {
            "total": total,
            "by_status": by_status,
            "by_completeness": by_completeness,
        },
    }


def get_ppv_event_detail(event_id: int) -> Optional[Dict[str, Any]]:
    """Return full event detail with linked channels."""
    event = db.session.get(Event, event_id)
    if not event:
        return None

    return {
        "event": serialize_event_detail(event),
        "channels": get_event_channels(event_id),
    }


def get_ppv_events_for_account(account_id: int) -> List[Dict]:
    """Get all PPV events for a specific account with channel links."""
    query = (
        db.session.query(Event, EventChannelLink, Channel)
        .join(EventChannelLink, Event.id == EventChannelLink.event_id)
        .join(Channel, EventChannelLink.channel_id == Channel.id)
        .filter(Channel.account_id == account_id)
        .order_by(Event.scheduled_at.desc())
    )

    results = []
    for event, link, channel in query.all():
        results.append(
            {
                "event_id": event.id,
                "external_id": event.external_id,
                "sport": event.sport,
                "league": event.league_name,
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "scheduled_at": serialize_utc_iso(event.scheduled_at),
                "status": event.status,
                "venue": event.venue_name,
                "city": event.city,
                "country": event.country,
                "channel_id": channel.id,
                "channel_name": channel.name,
                "channel_stream_id": channel.stream_id,
                "match_confidence": link.match_confidence,
                "match_method": link.match_method,
                "feed_type": link.feed_type,
            }
        )

    return results


def get_upcoming_ppv_events(days_ahead: int = 7) -> List[Dict]:
    """Get upcoming PPV events within a date range."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    future = now + timedelta(days=days_ahead)

    query = (
        db.session.query(Event)
        .filter(
            Event.scheduled_at >= now,
            Event.scheduled_at <= future,
            Event.is_ppv == True,  # noqa: E712
        )
        .order_by(Event.scheduled_at.asc())
    )

    results = []
    for event in query.all():
        channel_count = db.session.query(EventChannelLink).filter_by(event_id=event.id).count()

        results.append(
            {
                "id": event.id,
                "external_id": event.external_id,
                "sport": event.sport,
                "league": event.league_name,
                "home_team": event.home_team_name,
                "away_team": event.away_team_name,
                "scheduled_at": serialize_utc_iso(event.scheduled_at),
                "status": event.status,
                "venue": event.venue_name,
                "channel_count": channel_count,
            }
        )

    return results


def get_event_channels(event_id: int) -> List[Dict]:
    """Get all channels broadcasting a specific event."""
    query = (
        db.session.query(Channel, EventChannelLink)
        .join(EventChannelLink, Channel.id == EventChannelLink.channel_id)
        .filter(EventChannelLink.event_id == event_id)
        .order_by(Channel.account_id, Channel.stream_id)
    )

    results = []
    for channel, link in query.all():
        results.append(
            {
                "channel_id": channel.id,
                "channel_name": channel.name,
                "account_id": channel.account_id,
                "stream_id": channel.stream_id,
                "match_confidence": link.match_confidence,
                "match_method": link.match_method,
                "feed_type": link.feed_type,
                "region": link.region,
                "provider": link.provider,
            }
        )

    return results
