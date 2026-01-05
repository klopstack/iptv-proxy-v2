"""
EPG PPV (Pay-Per-View) Module

Handles PPV channel detection, visibility management, and PPV-specific EPG generation.
"""
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import Channel, ChannelTag, Tag, db
from services.epg.constants import PPV_CATEGORY_PATTERNS, PPV_PLACEHOLDER_PATTERNS

logger = logging.getLogger(__name__)


def is_ppv_channel(channel: Channel) -> bool:
    """
    Determine if a channel is a Pay-Per-View (PPV) channel.

    PPV channels dynamically update their names when events are scheduled,
    so they should not have traditional EPG mappings. Instead, they should
    be excluded from automatic EPG matching.

    Detection is based on category name patterns.

    Args:
        channel: Channel to check

    Returns:
        True if the channel appears to be a PPV channel

    Examples:
        Category "PPV EVENTS" -> True
        Category "US| PAY-PER-VIEW" -> True
        Category "UFC EVENTS" -> True
        Category "US| ENTERTAINMENT" -> False
    """
    if not channel.category:
        return False

    category_name = channel.category.category_name.upper()

    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, category_name, re.IGNORECASE):
            logger.debug(
                f"Channel '{channel.name}' identified as PPV "
                f"(category='{channel.category.category_name}', pattern='{pattern}')"
            )
            return True

    return False


def is_ppv_category(category_name: str) -> bool:
    """
    Determine if a category name indicates a PPV (Pay-Per-View) category.

    PPV channels update their names dynamically when events are scheduled,
    so they should not have traditional EPG mappings. This function checks
    if a category name matches PPV patterns.

    Args:
        category_name: The category name to check

    Returns:
        True if the category appears to be a PPV category

    Examples:
        "UK| DAZN PPV" -> True
        "US| ESPN+ PPV ⱽᴵᴾ" -> True
        "NL| MAX PPV" -> True
        "UK| SPORTS" -> False
        "US| ENTERTAINMENT" -> False
    """
    if not category_name:
        return False

    upper_name = category_name.upper()

    for pattern in PPV_CATEGORY_PATTERNS:
        if re.search(pattern, upper_name, re.IGNORECASE):
            return True

    return False


def is_ppv_placeholder_name(name: str) -> bool:
    """
    Check if a channel name is a PPV placeholder (no event scheduled).

    PPV channels from providers have placeholder names like "PPV 1", "PPV EVENT 2"
    when no event is scheduled. When an event IS scheduled, the provider changes
    the channel name to the actual event title (e.g., "UFC 300: Main Event").

    This function detects placeholder names to determine if a PPV channel
    should be hidden (placeholder) or shown (actual event scheduled).

    Args:
        name: The channel name to check

    Returns:
        True if the name matches a placeholder pattern (no event)
        False if the name appears to be an actual event title

    Examples:
        "UK: DAZN PPV 1 - NO EVENT STREAMING -" -> True (placeholder)
        "UFC 09:" -> True (placeholder)
        "UK: DAZN PPV 1 - UFC 300: Jones vs Miocic" -> False (actual event)
        "BOXING: Fury vs Joshua" -> False (actual event)
    """
    if not name:
        return True  # Empty name is treated as placeholder

    # Normalize the name for comparison
    normalized = name.strip().upper()

    # Check against placeholder patterns
    # Use re.search() to find patterns anywhere in the string
    for pattern in PPV_PLACEHOLDER_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            logger.debug(f"Channel name '{name}' matches placeholder pattern '{pattern}'")
            return True

    return False


def get_ppv_event_title(channel: Channel) -> Optional[str]:
    """
    Extract the event title from a PPV channel that has an active event.

    When a PPV channel has an event scheduled, the channel name becomes
    the event title. This function returns that title for use in EPG generation.

    Args:
        channel: The PPV channel to extract the event title from

    Returns:
        The event title if the channel has an active event, None if placeholder

    Examples:
        Channel name "UFC 300: Main Event" -> "UFC 300: Main Event"
        Channel name "PPV 1" -> None (placeholder)
    """
    if not channel.name:
        return None

    if is_ppv_placeholder_name(channel.name):
        return None

    # The channel name IS the event title
    return channel.name.strip()


def update_ppv_channel_visibility(account_id: Optional[int] = None) -> Dict[str, int]:
    """
    Update visibility of PPV channels based on channel name changes.

    PPV channels from IPTV providers have placeholder names like "PPV 1" when no
    event is scheduled. When an event IS scheduled, the provider changes the
    channel name to the event title (e.g., "UFC 300: Main Event").

    This function:
    1. Finds all PPV channels (by tag or category)
    2. Checks if channel name is a placeholder (no event) or event title
    3. Hides placeholder channels, shows channels with event titles

    Note: PPV channels don't have external EPG data. Detection is purely based
    on the channel name in the playlist.

    Args:
        account_id: Optional account ID to limit updates to specific account

    Returns:
        Dict with statistics: {
            'total_ppv_channels': int,
            'channels_shown': int,
            'channels_hidden': int,
            'events_detected': int
        }
    """
    stats = {
        "total_ppv_channels": 0,
        "channels_shown": 0,
        "channels_hidden": 0,
        "events_detected": 0,
    }

    # Get all channels with PPV tag
    ppv_tag = Tag.query.filter_by(name="PPV").first()
    if not ppv_tag:
        logger.info("No PPV tag found, skipping PPV channel visibility update")
        return stats

    # Query for channels with PPV tag
    query = (
        db.session.query(Channel)
        .join(
            ChannelTag, db.and_(Channel.account_id == ChannelTag.account_id, Channel.stream_id == ChannelTag.stream_id)
        )
        .filter(ChannelTag.tag_id == ppv_tag.id, Channel.is_active == True)  # noqa: E712
    )

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    ppv_channels = query.all()
    stats["total_ppv_channels"] = len(ppv_channels)

    if not ppv_channels:
        logger.info("No PPV channels found")
        return stats

    logger.info(f"Checking {len(ppv_channels)} PPV channel(s) for visibility updates")

    # Update each PPV channel's visibility based on its name
    for channel in ppv_channels:
        # Check if channel name is a placeholder (no event) or actual event title
        is_placeholder = is_ppv_placeholder_name(channel.name)

        if is_placeholder:
            # Placeholder name - hide the channel
            if channel.is_visible:
                channel.is_visible = False
                stats["channels_hidden"] += 1
                logger.info(f"Hiding PPV channel '{channel.name}' (placeholder name)")
        else:
            # Actual event title - show the channel
            stats["events_detected"] += 1
            if not channel.is_visible:
                channel.is_visible = True
                stats["channels_shown"] += 1
                logger.info(f"Showing PPV channel with event: '{channel.name}'")

    # Commit all visibility changes
    try:
        db.session.commit()
        logger.info(
            f"PPV visibility update complete: "
            f"{stats['events_detected']} events detected, "
            f"{stats['channels_shown']} shown, {stats['channels_hidden']} hidden"
        )
    except Exception as e:
        logger.error(f"Error committing PPV visibility changes: {e}")
        db.session.rollback()

    return stats


def generate_ppv_epg_entries(account_id: Optional[int] = None, duration_hours: int = 8) -> List[Dict[str, Any]]:
    """
    Generate synthetic EPG entries for active PPV channels.

    Since PPV channels don't have external EPG data, we generate EPG entries
    using the channel name as the program title. This allows the EPG to show
    what event is currently scheduled on each PPV channel.

    Args:
        account_id: Optional account ID to limit to specific account
        duration_hours: How long each PPV event should appear in EPG (default: 8 hours)

    Returns:
        List of EPG program entries in XMLTV format:
        [
            {
                'channel_id': 'ppv-101-12345',
                'title': 'UFC 300: Main Event',
                'start': '20231215180000 +0000',
                'stop': '20231216020000 +0000',
                'desc': 'Pay-Per-View Event',
                'category': 'Sports'
            },
            ...
        ]
    """
    programs: List[Dict[str, Any]] = []

    # Get all visible PPV channels (only those with active events)
    ppv_tag = Tag.query.filter_by(name="PPV").first()
    if not ppv_tag:
        return programs

    query = (
        db.session.query(Channel)
        .join(
            ChannelTag, db.and_(Channel.account_id == ChannelTag.account_id, Channel.stream_id == ChannelTag.stream_id)
        )
        .filter(
            ChannelTag.tag_id == ppv_tag.id,
            Channel.is_active == True,  # noqa: E712
            Channel.is_visible == True,  # noqa: E712
        )
    )

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    active_ppv_channels = query.all()

    if not active_ppv_channels:
        return programs

    # Generate EPG entry for each active PPV channel
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end_time = now + timedelta(hours=duration_hours)

    # Format times in XMLTV format
    start_str = now.strftime("%Y%m%d%H%M%S") + " +0000"
    stop_str = end_time.strftime("%Y%m%d%H%M%S") + " +0000"

    for channel in active_ppv_channels:
        event_title = get_ppv_event_title(channel)
        if not event_title:
            continue

        # Generate a unique EPG channel ID for this PPV channel
        epg_channel_id = f"ppv-{channel.stream_id}-{channel.account_id}"

        program = {
            "channel_id": epg_channel_id,
            "title": event_title,
            "start": start_str,
            "stop": stop_str,
            "desc": "Pay-Per-View Event",
            "category": "Sports",  # Most PPV is sports-related
        }
        programs.append(program)

        logger.debug(f"Generated PPV EPG entry for '{event_title}' on channel {channel.stream_id}")

    logger.info(f"Generated {len(programs)} PPV EPG entries")
    return programs


def get_ppv_epg_xmltv(account_id: Optional[int] = None, duration_hours: int = 8) -> bytes:
    """
    Generate XMLTV data for active PPV channels.

    This creates a valid XMLTV document containing channel definitions
    and program entries for all active PPV events.

    Args:
        account_id: Optional account ID to limit to specific account
        duration_hours: How long each PPV event should appear in EPG

    Returns:
        XMLTV XML data as bytes
    """
    root = ET.Element("tv")
    root.set("source-info-name", "IPTV Proxy PPV EPG")
    root.set("generator-info-name", "iptv-proxy-v2")

    # Get active PPV channels
    ppv_tag = Tag.query.filter_by(name="PPV").first()
    if not ppv_tag:
        return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    query = (
        db.session.query(Channel)
        .join(
            ChannelTag, db.and_(Channel.account_id == ChannelTag.account_id, Channel.stream_id == ChannelTag.stream_id)
        )
        .filter(
            ChannelTag.tag_id == ppv_tag.id,
            Channel.is_active == True,  # noqa: E712
            Channel.is_visible == True,  # noqa: E712
        )
    )

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    active_ppv_channels = query.all()

    if not active_ppv_channels:
        return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")

    # Time for programs
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end_time = now + timedelta(hours=duration_hours)
    start_str = now.strftime("%Y%m%d%H%M%S") + " +0000"
    stop_str = end_time.strftime("%Y%m%d%H%M%S") + " +0000"

    # Add channels and programs
    for channel in active_ppv_channels:
        event_title = get_ppv_event_title(channel)
        if not event_title:
            continue

        epg_channel_id = f"ppv-{channel.stream_id}-{channel.account_id}"

        # Add channel element
        channel_elem = ET.SubElement(root, "channel", id=epg_channel_id)
        display_name = ET.SubElement(channel_elem, "display-name")
        display_name.text = event_title

        if channel.stream_icon:
            ET.SubElement(channel_elem, "icon", src=channel.stream_icon)

        # Add program element
        programme = ET.SubElement(root, "programme", start=start_str, stop=stop_str, channel=epg_channel_id)

        title_elem = ET.SubElement(programme, "title", lang="en")
        title_elem.text = event_title

        desc_elem = ET.SubElement(programme, "desc", lang="en")
        desc_elem.text = "Pay-Per-View Event"

        category_elem = ET.SubElement(programme, "category", lang="en")
        category_elem.text = "Sports"

    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")
