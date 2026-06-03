"""Shared EpgProgram create/update for XMLTV and Schedules Direct sync paths."""

import json
from datetime import datetime, timezone
from typing import Any, Dict

from models import EpgProgram


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_epg_program(epg_channel_id: int, data: Dict[str, Any]) -> EpgProgram:
    """Create a new EpgProgram from parsed sync data."""
    now = _utc_now_naive()

    return EpgProgram(
        epg_channel_id=epg_channel_id,
        start_time=data["start_time"],
        stop_time=data["stop_time"],
        title=data["title"],
        sub_title=data.get("sub_title"),
        description=data.get("description"),
        categories=json.dumps(data["categories"]) if data.get("categories") else None,
        season=data.get("season"),
        episode=data.get("episode"),
        episode_id=data.get("episode_id"),
        rating=data.get("rating"),
        rating_system=data.get("rating_system"),
        original_air_date=data.get("original_air_date"),
        is_new=data.get("is_new", False),
        is_live=data.get("is_live", False),
        is_premiere=data.get("is_premiere", False),
        sport=data.get("sport"),
        team_home=data.get("team_home"),
        team_away=data.get("team_away"),
        icon_url=data.get("icon_url"),
        last_updated=now,
        created_at=now,
    )


def update_epg_program(prog: EpgProgram, data: Dict[str, Any]) -> bool:
    """
    Update an existing EpgProgram with new sync data.

    Returns:
        True if any field was modified, False if unchanged.
    """
    changed = False
    new_categories = json.dumps(data["categories"]) if data.get("categories") else None

    field_updates = (
        ("stop_time", data["stop_time"]),
        ("title", data["title"]),
        ("sub_title", data.get("sub_title")),
        ("description", data.get("description")),
        ("categories", new_categories),
        ("season", data.get("season")),
        ("episode", data.get("episode")),
        ("episode_id", data.get("episode_id")),
        ("rating", data.get("rating")),
        ("rating_system", data.get("rating_system")),
        ("original_air_date", data.get("original_air_date")),
        ("is_new", data.get("is_new", False)),
        ("is_live", data.get("is_live", False)),
        ("is_premiere", data.get("is_premiere", False)),
        ("sport", data.get("sport")),
        ("team_home", data.get("team_home")),
        ("team_away", data.get("team_away")),
        ("icon_url", data.get("icon_url")),
    )

    for attr, new_value in field_updates:
        if getattr(prog, attr) != new_value:
            setattr(prog, attr, new_value)
            changed = True

    if changed:
        prog.last_updated = _utc_now_naive()

    return changed
