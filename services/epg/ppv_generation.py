"""
Build XMLTV channel and programme elements from PPV Event records.

Shared by playlist EPG generation and Xtream short EPG fallback.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Tuple

from models import Channel, Event, EventChannelLink
from services.epg.programs import format_xmltv_time

DEFAULT_EVENT_DURATION_HOURS = 4


def event_programme_title(event: Event) -> str:
    """Return display title for an event programme."""
    if event.title:
        return event.title
    return f"{event.home_team_name} vs {event.away_team_name}"


def event_end_time(event: Event, default_duration_hours: int = DEFAULT_EVENT_DURATION_HOURS) -> datetime:
    """Return programme stop time from event end_at or default duration."""
    if event.end_at:
        return event.end_at
    return event.scheduled_at + timedelta(hours=default_duration_hours)


def build_event_description(event: Event, link: Optional[EventChannelLink] = None) -> str:
    """Build programme description from event metadata."""
    if getattr(event, "description", None):
        return event.description

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

    if link and link.match_confidence < 1.0:
        desc_parts.append(f"Match Confidence: {link.match_confidence * 100:.0f}%")

    return "\n".join(desc_parts) if desc_parts else "Pay-Per-View Sports Event"


def build_event_channel_element(
    channel: Channel,
    event: Event,
    output_channel_id: str,
) -> ET.Element:
    """Build an XMLTV <channel> element for a PPV event."""
    channel_elem = ET.Element("channel")
    channel_elem.set("id", output_channel_id)

    display_name = ET.SubElement(channel_elem, "display-name")
    display_name.text = event_programme_title(event)

    if channel.cleaned_name and channel.cleaned_name != display_name.text:
        display_name_alt = ET.SubElement(channel_elem, "display-name")
        display_name_alt.text = channel.cleaned_name

    if event.home_team_badge:
        ET.SubElement(channel_elem, "icon", src=event.home_team_badge)
    elif event.away_team_badge:
        ET.SubElement(channel_elem, "icon", src=event.away_team_badge)
    elif channel.stream_icon:
        ET.SubElement(channel_elem, "icon", src=channel.stream_icon)

    return channel_elem


def build_event_programme_element(
    channel: Channel,
    event: Event,
    output_channel_id: str,
    link: Optional[EventChannelLink] = None,
    default_duration_hours: int = DEFAULT_EVENT_DURATION_HOURS,
) -> ET.Element:
    """Build an XMLTV <programme> element for a PPV event."""
    start_dt = event.scheduled_at
    end_dt = event_end_time(event, default_duration_hours)

    programme = ET.Element("programme")
    programme.set("start", format_xmltv_time(start_dt))
    programme.set("stop", format_xmltv_time(end_dt))
    programme.set("channel", output_channel_id)

    title_elem = ET.SubElement(programme, "title", lang="en")
    title_elem.text = event_programme_title(event)

    if event.league_name:
        subtitle_elem = ET.SubElement(programme, "sub-title", lang="en")
        subtitle_elem.text = event.league_name

    desc_elem = ET.SubElement(programme, "desc", lang="en")
    desc_elem.text = build_event_description(event, link)

    category_elem = ET.SubElement(programme, "category", lang="en")
    category_elem.text = event.sport or "Sports"

    if event.external_id:
        episode_elem = ET.SubElement(programme, "episode-num", system="thesportsdb")
        episode_elem.text = event.external_id

    date_elem = ET.SubElement(programme, "date")
    date_elem.text = start_dt.strftime("%Y%m%d")

    if link and link.match_confidence >= 0.8:
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

    return programme


def build_event_epg_elements(
    channel: Channel,
    event: Event,
    output_channel_id: str,
    link: Optional[EventChannelLink] = None,
    default_duration_hours: int = DEFAULT_EVENT_DURATION_HOURS,
) -> Tuple[ET.Element, ET.Element]:
    """Build channel and programme XMLTV elements for a linked PPV event."""
    channel_elem = build_event_channel_element(channel, event, output_channel_id)
    programme_elem = build_event_programme_element(
        channel,
        event,
        output_channel_id,
        link=link,
        default_duration_hours=default_duration_hours,
    )
    return channel_elem, programme_elem
