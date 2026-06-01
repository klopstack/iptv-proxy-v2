from datetime import datetime, timezone
from types import SimpleNamespace

from services.ppv.serializers import (
    serialize_event_detail,
    serialize_event_summary,
    serialize_linked_event_summary,
    serialize_utc_iso,
)


def _build_event(**overrides):
    data = {
        "id": 1,
        "external_id": "E123",
        "title": "Event",
        "sport": "Soccer",
        "league_name": "League",
        "home_team_name": "Home",
        "away_team_name": "Away",
        "scheduled_at": datetime(2026, 6, 1, 12, 0, 0),
        "status": "scheduled",
        "venue_name": "Venue",
        "city": "City",
        "country": "Country",
        "data_completeness": "full",
        "event_image": None,
        "home_team_badge": None,
        "away_team_badge": None,
        "last_updated_at": datetime(2026, 6, 1, 10, 0, 0),
        "source": "thesportsdb",
        "league_id": "L1",
        "home_team_id": "H1",
        "away_team_id": "A1",
        "start_at": datetime(2026, 6, 1, 12, 0, 0),
        "end_at": datetime(2026, 6, 1, 14, 0, 0),
        "timezone": "America/New_York",
        "venue_id": "V1",
        "is_ppv": True,
        "created_at": datetime(2026, 5, 30, 8, 0, 0),
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_serialize_utc_iso_naive_becomes_z():
    result = serialize_utc_iso(datetime(2026, 6, 1, 12, 0, 0))
    assert result == "2026-06-01T12:00:00Z"


def test_serialize_utc_iso_aware_converts_to_utc_z():
    dt = datetime(2026, 6, 1, 8, 0, 0, tzinfo=timezone.utc)
    result = serialize_utc_iso(dt)
    assert result == "2026-06-01T08:00:00Z"


def test_serialize_event_summary_uses_explicit_utc():
    event = _build_event()
    data = serialize_event_summary(event)
    assert data["scheduled_at"].endswith("Z")
    assert data["last_updated_at"].endswith("Z")


def test_serialize_event_detail_uses_explicit_utc():
    event = _build_event()
    data = serialize_event_detail(event)
    assert data["start_at"].endswith("Z")
    assert data["end_at"].endswith("Z")
    assert data["created_at"].endswith("Z")


def test_serialize_linked_event_summary_uses_explicit_utc():
    event = _build_event()
    link = SimpleNamespace(match_confidence=0.9, match_method="exact")
    data = serialize_linked_event_summary(event, link)
    assert data["scheduled_at"].endswith("Z")
