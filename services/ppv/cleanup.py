"""Cleanup helpers for PPV enrichment lifecycle."""

import logging
from typing import Iterable

from models import Channel, ChannelEpgMapping, EpgChannel, EpgSource, Event, EventChannelLink, db

logger = logging.getLogger(__name__)


def reset_channel_ppv_state(channel_id: int) -> None:
    """
    Clear PPV event links and PPV EPG mappings for a channel.

    Called when a PPV channel name changes and a fresh enrichment run is needed.
    """
    EventChannelLink.query.filter_by(channel_id=channel_id).delete(synchronize_session=False)

    ppv_source_ids = [
        row[0] for row in db.session.query(EpgSource.id).filter(EpgSource.source_type == "ppv_events").all()
    ]
    if not ppv_source_ids:
        return

    mapping_ids = [
        row[0]
        for row in db.session.query(ChannelEpgMapping.id)
        .join(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .filter(
            ChannelEpgMapping.channel_id == channel_id,
            EpgChannel.source_id.in_(ppv_source_ids),
        )
        .all()
    ]
    if mapping_ids:
        ChannelEpgMapping.query.filter(ChannelEpgMapping.id.in_(mapping_ids)).delete(synchronize_session=False)


def reset_channels_ppv_state(channel_ids: Iterable[int]) -> int:
    """Reset PPV state for multiple channels."""
    count = 0
    for channel_id in channel_ids:
        reset_channel_ppv_state(channel_id)
        count += 1
    return count


def prune_orphan_ppv_events() -> int:
    """Delete PPV events that no longer have any channel links."""
    linked_event_ids = {row[0] for row in db.session.query(EventChannelLink.event_id).distinct().all()}

    query = Event.query.filter(Event.is_ppv.is_(True))
    if linked_event_ids:
        query = query.filter(~Event.id.in_(linked_event_ids))
    orphans = query.all()

    removed = 0
    for event in orphans:
        epg_channel_ids = [
            row[0]
            for row in db.session.query(EpgChannel.id)
            .filter(EpgChannel.channel_id == f"ppv-event-{event.external_id}")
            .all()
        ]
        if epg_channel_ids:
            ChannelEpgMapping.query.filter(ChannelEpgMapping.epg_channel_id.in_(epg_channel_ids)).delete(
                synchronize_session=False
            )
            EpgChannel.query.filter(EpgChannel.id.in_(epg_channel_ids)).delete(synchronize_session=False)
        db.session.delete(event)
        removed += 1

    if removed:
        logger.info("Pruned %s orphan PPV event(s)", removed)
    return removed


def sync_ppv_epg_after_enrichment(matched_count: int = 0) -> dict:
    """Sync PPV events to EPG channels and map enriched channels (post-enrichment only)."""
    if matched_count <= 0:
        return {"epg_channels_created": 0, "epg_channels_updated": 0, "epg_mappings": 0}

    from services.epg.match_rules import EpgMatchRulesService
    from services.ppv.epg import PPVEpgService

    source_id = PPVEpgService.create_epg_source_for_ppv_events()
    created, updated = PPVEpgService.sync_ppv_events_to_epg_channels(source_id)
    match_stats = EpgMatchRulesService.match_ppv_channels_to_epg(source_id=source_id, batch_size=500)
    prune_orphan_ppv_events()

    return {
        "epg_channels_created": created,
        "epg_channels_updated": updated,
        "epg_mappings": match_stats.get("matched_count", 0),
    }


def remove_invalid_event_links() -> int:
    """
    Remove event links where extracted channel competitors do not match the event.

    Returns count of links removed.
    """
    from services.ppv.extraction import PPVEventExtractor
    from services.ppv.matching.validation import competitors_match_event

    extractor = PPVEventExtractor()
    removed = 0

    links = (
        db.session.query(EventChannelLink, Channel, Event)
        .join(Channel, EventChannelLink.channel_id == Channel.id)
        .join(Event, EventChannelLink.event_id == Event.id)
        .filter(Channel.is_ppv.is_(True))
        .all()
    )

    for link, channel, event in links:
        extraction = extractor.extract_all(channel.name)
        competitors = extraction.get("competitors")
        if not competitors or len(competitors) != 2:
            continue

        calendar_event = _event_to_calendar_event(event)
        if calendar_event and competitors_match_event(competitors, calendar_event):
            continue

        db.session.delete(link)
        channel.ppv_enrichment_status = "no_match"
        removed += 1

    return removed


def _event_to_calendar_event(event: Event):
    """Build a minimal CalendarEvent for validation."""
    from services.thesportsdb_calendar_scraper import CalendarEvent

    if not event.external_id:
        return None

    date_str = event.scheduled_at.strftime("%Y-%m-%d") if event.scheduled_at else ""
    time_str = event.scheduled_at.strftime("%H:%M") if event.scheduled_at else "00:00"

    return CalendarEvent(
        event_id=event.external_id,
        event_name=event.title or f"{event.home_team_name} vs {event.away_team_name}",
        league_name=event.league_name or "",
        time_utc=time_str,
        date=date_str,
        home_team=event.home_team_name,
        away_team=event.away_team_name,
    )
