"""XMLTV EPG generation from PPV event records."""

import logging
import xml.etree.ElementTree as ET
from datetime import timedelta
from typing import Dict, List, Optional, Set, Tuple

from models import Channel, Event, EventChannelLink, db
from services.filter_service import FilterService

logger = logging.getLogger(__name__)


def generate_ppv_epg_xmltv(
    account_id: Optional[int] = None,
    include_inactive: bool = False,
    event_duration_hours: int = 4,
) -> bytes:
    """
    Generate XMLTV EPG data from Event records linked to PPV channels.

    Creates proper XMLTV format with:
    - Channel definitions with proper display names and icons
    - Programme entries with event metadata from TheSportsDB
    - Proper time formatting and duration handling
    - Support for multiple feeds per event

    Args:
        account_id: Optional account ID to filter channels
        include_inactive: Whether to include channels without matched events
        event_duration_hours: Default duration for events without end time

    Returns:
        XMLTV XML data as bytes
    """
    root = ET.Element("tv")
    root.set("source-info-name", "IPTV Proxy PPV EPG")
    root.set("source-info-url", "https://github.com/klopstack/iptv-proxy-v2")
    root.set("generator-info-name", "iptv-proxy-v2/ppv-epg-service")

    query = (
        db.session.query(Channel, EventChannelLink, Event)
        .join(EventChannelLink, Channel.id == EventChannelLink.channel_id)
        .join(Event, EventChannelLink.event_id == Event.id)
        .filter(
            Channel.is_active == True,  # noqa: E712
        )
    )

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    matched_channels = query.all()

    if not matched_channels:
        logger.info("No PPV channels with matched events found")
        return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    channels_by_account: Dict[int, List[Tuple[Channel, EventChannelLink, Event]]] = {}
    for channel, link, event in matched_channels:
        if channel.account_id not in channels_by_account:
            channels_by_account[channel.account_id] = []
        channels_by_account[channel.account_id].append((channel, link, event))

    filtered_channels: List[Tuple[Channel, EventChannelLink, Event]] = []
    for acc_id, channels in channels_by_account.items():
        channel_objs = [ch for ch, _, _ in channels]
        visible_ids = {ch.id for ch in FilterService.apply_filters_to_channels(channel_objs, acc_id)}
        filtered_channels.extend((ch, link, evt) for ch, link, evt in channels if ch.id in visible_ids)

    if not filtered_channels:
        logger.info("No visible PPV channels after filtering")
        return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    added_channels: Set[str] = set()

    for channel, link, event in filtered_channels:
        channel_id = f"ppv-{channel.account_id}-{channel.stream_id}"

        if channel_id in added_channels:
            continue

        added_channels.add(channel_id)

        channel_elem = ET.SubElement(root, "channel", id=channel_id)

        display_name = ET.SubElement(channel_elem, "display-name")
        display_name.text = event.home_team_name + " vs " + event.away_team_name

        if channel.cleaned_name:
            display_name_alt = ET.SubElement(channel_elem, "display-name")
            display_name_alt.text = channel.cleaned_name

        if event.home_team_badge:
            ET.SubElement(channel_elem, "icon", src=event.home_team_badge)
        elif event.away_team_badge:
            ET.SubElement(channel_elem, "icon", src=event.away_team_badge)
        elif channel.stream_icon:
            ET.SubElement(channel_elem, "icon", src=channel.stream_icon)

    for channel, link, event in matched_channels:
        channel_id = f"ppv-{channel.account_id}-{channel.stream_id}"

        start_dt = event.scheduled_at
        if event.end_at:
            end_dt = event.end_at
        else:
            end_dt = start_dt + timedelta(hours=event_duration_hours)

        start_str = start_dt.strftime("%Y%m%d%H%M%S") + " +0000"
        end_str = end_dt.strftime("%Y%m%d%H%M%S") + " +0000"

        programme = ET.SubElement(root, "programme", start=start_str, stop=end_str, channel=channel_id)

        title_elem = ET.SubElement(programme, "title", lang="en")
        title_elem.text = f"{event.home_team_name} vs {event.away_team_name}"

        if event.league_name:
            subtitle_elem = ET.SubElement(programme, "sub-title", lang="en")
            subtitle_elem.text = event.league_name

        desc_elem = ET.SubElement(programme, "desc", lang="en")
        if getattr(event, "description", None):
            desc_elem.text = event.description
        else:
            desc_parts = []
            if event.sport:
                desc_parts.append(f"Sport: {event.sport}")
            if event.league_name:
                desc_parts.append(f"League: {event.league_name}")
            if event.venue_name:
                desc_parts.append(f"Venue: {event.venue_name}")
            if event.city and event.country:
                desc_parts.append(f"Location: {event.city}, {event.country}")
            elif event.country:
                desc_parts.append(f"Location: {event.country}")

            status_display = {
                Event.STATUS_SCHEDULED: "Scheduled",
                Event.STATUS_LIVE: "Live Now",
                Event.STATUS_FINISHED: "Finished",
                Event.STATUS_CANCELLED: "Cancelled",
            }
            if event.status in status_display:
                desc_parts.append(f"Status: {status_display[event.status]}")

            if link.match_confidence < 1.0:
                desc_parts.append(f"Match Confidence: {link.match_confidence * 100:.0f}%")

            desc_elem.text = "\n".join(desc_parts) if desc_parts else "Pay-Per-View Sports Event"

        category_elem = ET.SubElement(programme, "category", lang="en")
        category_elem.text = event.sport or "Sports"

        if event.external_id:
            episode_elem = ET.SubElement(programme, "episode-num", system="thesportsdb")
            episode_elem.text = event.external_id

        date_elem = ET.SubElement(programme, "date")
        date_elem.text = start_dt.strftime("%Y%m%d")

        if link.match_confidence >= 0.8:
            rating_elem = ET.SubElement(programme, "star-rating")
            value_elem = ET.SubElement(rating_elem, "value")
            stars = int(link.match_confidence * 5)
            value_elem.text = f"{stars}/5"

        if event.home_team_badge or event.away_team_badge or event.event_image:
            image_url = event.event_image or event.home_team_badge or event.away_team_badge
            ET.SubElement(programme, "icon", src=image_url)

        credits_elem = ET.SubElement(programme, "credits")
        if event.home_team_name:
            actor_elem = ET.SubElement(credits_elem, "actor")
            actor_elem.text = event.home_team_name
        if event.away_team_name:
            actor_elem = ET.SubElement(credits_elem, "actor")
            actor_elem.text = event.away_team_name

    logger.info(
        f"Generated PPV EPG with {len(added_channels)} channels " f"and {len(matched_channels)} programme entries"
    )

    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")
