"""Shared serializers for PPV event and channel preview APIs."""

from datetime import timezone
from typing import Any, Dict, Optional

from models import Event, EventChannelLink


def serialize_utc_iso(dt) -> Optional[str]:
    """Serialize datetime as explicit UTC ISO8601 string with Z suffix."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def serialize_event_summary(event: Event, channel_count: Optional[int] = None) -> Dict[str, Any]:
    """Serialize an Event for list/preview views."""
    result = {
        "id": event.id,
        "external_id": event.external_id,
        "title": event.title,
        "sport": event.sport,
        "league": event.league_name,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "scheduled_at": serialize_utc_iso(event.scheduled_at),
        "status": event.status,
        "venue": event.venue_name,
        "city": event.city,
        "country": event.country,
        "data_completeness": event.data_completeness,
        "event_image": event.event_image,
        "home_team_badge": event.home_team_badge,
        "away_team_badge": event.away_team_badge,
        "last_updated_at": serialize_utc_iso(event.last_updated_at),
    }
    if channel_count is not None:
        result["channel_count"] = channel_count
    return result


def serialize_event_detail(event: Event) -> Dict[str, Any]:
    """Serialize full event record for detail views."""
    data = serialize_event_summary(event)
    data.update(
        {
            "source": event.source,
            "league_id": event.league_id,
            "home_team_id": event.home_team_id,
            "away_team_id": event.away_team_id,
            "start_at": serialize_utc_iso(event.start_at),
            "end_at": serialize_utc_iso(event.end_at),
            "timezone": event.timezone,
            "venue_id": event.venue_id,
            "is_ppv": event.is_ppv,
            "created_at": serialize_utc_iso(event.created_at),
        }
    )
    return data


def serialize_linked_event_summary(event: Event, link: EventChannelLink) -> Dict[str, Any]:
    """Serialize linked event metadata for channel preview rows."""
    return {
        "id": event.id,
        "external_id": event.external_id,
        "home_team": event.home_team_name,
        "away_team": event.away_team_name,
        "scheduled_at": serialize_utc_iso(event.scheduled_at),
        "status": event.status,
        "match_confidence": link.match_confidence,
        "match_method": link.match_method,
    }
