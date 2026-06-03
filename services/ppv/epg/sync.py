"""Sync PPV events to EpgSource / EpgChannel records."""

import json
import logging
from datetime import datetime, timezone
from typing import Tuple

from models import Event, EventChannelLink, db

logger = logging.getLogger(__name__)


def create_epg_source_for_ppv_events(name: str = "PPV Events") -> int:
    """
    Create an EPG source entry for PPV events if it doesn't exist.

    Returns:
        EPG source ID
    """
    from models import EpgSource

    existing = EpgSource.query.filter_by(source_type="ppv_events", name=name).first()

    if existing:
        return existing.id

    epg_source = EpgSource(
        name=name,
        source_type="ppv_events",
        enabled=True,
        priority=50,
        last_sync_status="success",
        last_sync_message="PPV Events source created",
        channel_count=0,
    )

    db.session.add(epg_source)
    db.session.commit()

    logger.info(f"Created PPV events EPG source with ID {epg_source.id}")
    return epg_source.id


def sync_ppv_events_to_epg_channels(epg_source_id: int) -> Tuple[int, int]:
    """
    Sync Event records to EpgChannel entries for a PPV EPG source.

    Returns:
        Tuple of (created_count, updated_count)
    """
    from models import EpgChannel

    events = (
        db.session.query(Event)
        .join(EventChannelLink, Event.id == EventChannelLink.event_id)
        .filter(Event.is_ppv == True)  # noqa: E712
        .distinct()
        .all()
    )

    created = 0
    updated = 0

    for event in events:
        channel_id = f"ppv-event-{event.external_id}"

        epg_channel = EpgChannel.query.filter_by(source_id=epg_source_id, channel_id=channel_id).first()

        display_name = f"{event.home_team_name} vs {event.away_team_name}"

        display_names = [
            display_name,
            event.home_team_name,
            event.away_team_name,
        ]
        if event.league_name:
            display_names.append(event.league_name)

        if epg_channel:
            epg_channel.display_name = display_name
            epg_channel.display_names_json = json.dumps(display_names)
            epg_channel.icon_url = event.event_image or event.home_team_badge or event.away_team_badge
            epg_channel.program_count = 1
            epg_channel.first_program = event.scheduled_at
            epg_channel.last_program = event.end_at or event.scheduled_at
            epg_channel.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)
            updated += 1
        else:
            epg_channel = EpgChannel(
                source_id=epg_source_id,
                channel_id=channel_id,
                display_name=display_name,
                display_names_json=json.dumps(display_names),
                icon_url=(event.event_image or event.home_team_badge or event.away_team_badge),
                program_count=1,
                first_program=event.scheduled_at,
                last_program=event.end_at or event.scheduled_at,
            )
            db.session.add(epg_channel)
            created += 1

    db.session.commit()

    from models import EpgSource

    epg_source = db.session.get(EpgSource, epg_source_id)
    if epg_source:
        epg_source.channel_count = created + updated
        epg_source.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)
        epg_source.last_sync_status = "success"
        epg_source.last_sync_message = f"Synced {created + updated} PPV events"
        db.session.commit()

    logger.info(f"Synced PPV events to EPG channels: {created} created, {updated} updated")
    return (created, updated)


def sync_ppv_event_to_epg_channels(event: Event) -> bool:
    """Update a single ppv_events EPG channel when event timing or status changes."""
    from models import EpgChannel, EpgSource

    source = EpgSource.query.filter_by(source_type="ppv_events", enabled=True).first()
    if not source:
        return False

    channel_id = f"ppv-event-{event.external_id}"
    epg_channel = EpgChannel.query.filter_by(source_id=source.id, channel_id=channel_id).first()
    if not epg_channel:
        return False

    display_name = f"{event.home_team_name} vs {event.away_team_name}"
    display_names = [display_name, event.home_team_name, event.away_team_name]
    if event.league_name:
        display_names.append(event.league_name)

    epg_channel.display_name = display_name
    epg_channel.display_names_json = json.dumps(display_names)
    epg_channel.icon_url = event.event_image or event.home_team_badge or event.away_team_badge
    epg_channel.program_count = 1
    epg_channel.first_program = event.scheduled_at
    epg_channel.last_program = event.end_at or event.scheduled_at
    epg_channel.last_seen = datetime.now(timezone.utc).replace(tzinfo=None)

    db.session.commit()
    logger.debug("Updated ppv_events EPG channel for event %s", event.external_id)
    return True
