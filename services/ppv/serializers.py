"""Shared serializers for PPV event and channel preview APIs."""

from typing import Any, Dict, Optional

from models import Event, EventChannelLink


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
        "scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
        "status": event.status,
        "venue": event.venue_name,
        "city": event.city,
        "country": event.country,
        "data_completeness": event.data_completeness,
        "event_image": event.event_image,
        "home_team_badge": event.home_team_badge,
        "away_team_badge": event.away_team_badge,
        "last_updated_at": event.last_updated_at.isoformat() if event.last_updated_at else None,
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
            "start_at": event.start_at.isoformat() if event.start_at else None,
            "end_at": event.end_at.isoformat() if event.end_at else None,
            "timezone": event.timezone,
            "venue_id": event.venue_id,
            "is_ppv": event.is_ppv,
            "created_at": event.created_at.isoformat() if event.created_at else None,
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
        "scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
        "status": event.status,
        "match_confidence": link.match_confidence,
        "match_method": link.match_method,
    }
