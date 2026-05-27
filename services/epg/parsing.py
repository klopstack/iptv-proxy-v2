"""
EPG Parsing Module

Handles parsing XMLTV data and syncing EPG sources to the database.
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Set, Tuple

from models import EpgChannel, EpgSource, db
from services.epg.utils import get_decompressing_stream, parse_xmltv_time

logger = logging.getLogger(__name__)


def parse_xmltv_streaming(xml_content: bytes) -> Iterator[Tuple[str, Dict]]:
    """
    Parse XMLTV content using streaming parser for memory efficiency.
    Yields channel and programme elements one at a time.

    Args:
        xml_content: Raw XMLTV XML bytes (may be gzip-compressed)

    Yields:
        Tuples of (element_type, data) where element_type is 'channel' or 'programme'
    """
    stream = get_decompressing_stream(xml_content)

    try:
        # Use iterparse for memory-efficient parsing
        context = ET.iterparse(stream, events=("end",))

        for event, elem in context:
            if elem.tag == "channel":
                channel_id = elem.get("id")
                if channel_id:
                    display_names = []
                    for dn in elem.findall("display-name"):
                        if dn.text:
                            display_names.append(dn.text.strip())

                    icon_url = None
                    icon_elem = elem.find("icon")
                    if icon_elem is not None:
                        icon_url = icon_elem.get("src")

                    url = None
                    url_elem = elem.find("url")
                    if url_elem is not None and url_elem.text:
                        url = url_elem.text.strip()

                    yield (
                        "channel",
                        {
                            "channel_id": channel_id,
                            "display_names": display_names,
                            "display_name": display_names[0] if display_names else channel_id,
                            "icon_url": icon_url,
                            "url": url,
                        },
                    )

                # Clear element to free memory
                elem.clear()

            elif elem.tag == "programme":
                channel_id = elem.get("channel")
                if channel_id:
                    yield (
                        "programme",
                        {
                            "channel": channel_id,
                            "start": elem.get("start"),
                            "stop": elem.get("stop"),
                        },
                    )

                # Clear element to free memory
                elem.clear()

            # Also clear any ancestors to prevent memory buildup
            # This is needed because iterparse keeps a reference to parent elements
            if elem.tag in ("channel", "programme"):
                # Clear the element's tail text
                elem.tail = None

    except ET.ParseError as e:
        logger.error(f"Failed to parse XMLTV: {e}")
        raise ValueError(f"Invalid XMLTV XML: {e}")
    finally:
        stream.close()


def parse_xmltv(xml_content: bytes) -> Dict[str, Any]:
    """
    Parse XMLTV content and extract channel information.

    Uses streaming parser internally for memory efficiency with large files.

    Args:
        xml_content: Raw XMLTV XML bytes (may be gzip-compressed)

    Returns:
        Dict with 'channels' list and 'programs_by_channel' dict
    """
    channels: List[Dict[str, Any]] = []
    programs_by_channel: Dict[str, List[Dict]] = {}

    for element_type, data in parse_xmltv_streaming(xml_content):
        if element_type == "channel":
            channels.append(data)
            programs_by_channel[data["channel_id"]] = []
        elif element_type == "programme":
            channel_id = data["channel"]
            if channel_id in programs_by_channel:
                programs_by_channel[channel_id].append(
                    {
                        "start": data["start"],
                        "stop": data["stop"],
                    }
                )

    return {
        "channels": channels,
        "programs_by_channel": programs_by_channel,
    }


def sync_epg_source(source: EpgSource, xml_content: bytes) -> Dict[str, int]:
    """
    Sync EPG data from XMLTV content into the database.

    Uses streaming parser for memory efficiency with large files.

    Args:
        source: The EpgSource to sync
        xml_content: Raw XMLTV XML bytes

    Returns:
        Dict with sync statistics
    """
    stats = {
        "channels_added": 0,
        "channels_updated": 0,
        "channels_removed": 0,
        "total_programs": 0,
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seen_channel_ids: Set[str] = set()

    # Track channel data and program stats as we stream
    # We only keep essential info in memory, not all program details
    channel_data_map: Dict[str, Dict] = {}
    channel_program_stats: Dict[str, Dict] = {}  # channel_id -> {count, first_time, last_time}

    # Stream through the XMLTV content
    try:
        for element_type, data in parse_xmltv_streaming(xml_content):
            if element_type == "channel":
                channel_id = data["channel_id"]
                if channel_id in channel_data_map:
                    # Handle duplicate channel entries by merging display names
                    existing = channel_data_map[channel_id]
                    existing_names = existing.get("display_names", [])
                    new_names = data.get("display_names", [])
                    merged_names = list(dict.fromkeys(existing_names + new_names))
                    existing["display_names"] = merged_names
                    if not existing.get("icon_url") and data.get("icon_url"):
                        existing["icon_url"] = data.get("icon_url")
                    if not existing.get("url") and data.get("url"):
                        existing["url"] = data.get("url")
                    logger.debug(f"Merged duplicate channel ID '{channel_id}' in XMLTV data")
                else:
                    channel_data_map[channel_id] = data
                    channel_program_stats[channel_id] = {
                        "count": 0,
                        "first_time": None,
                        "last_time": None,
                    }
                seen_channel_ids.add(channel_id)

            elif element_type == "programme":
                channel_id = data["channel"]
                if channel_id in channel_program_stats:
                    prog_stats = channel_program_stats[channel_id]
                    prog_stats["count"] += 1
                    stats["total_programs"] += 1

                    # Track time range without storing all times
                    for time_field in ("start", "stop"):
                        time_str = data.get(time_field)
                        if time_str:
                            try:
                                t = parse_xmltv_time(time_str)
                                if t:
                                    if prog_stats["first_time"] is None or t < prog_stats["first_time"]:
                                        prog_stats["first_time"] = t
                                    if prog_stats["last_time"] is None or t > prog_stats["last_time"]:
                                        prog_stats["last_time"] = t
                            except (TypeError, ValueError) as e:
                                logger.debug(
                                    "Skipping invalid programme %s time %r for channel %s: %s",
                                    time_field,
                                    time_str,
                                    channel_id,
                                    e,
                                )

    except ValueError as e:
        source.last_sync_status = "error"
        source.last_sync_message = str(e)
        db.session.commit()
        raise

    # Track channels we've already processed in THIS sync
    processed_in_this_sync: Dict[str, EpgChannel] = {}

    # Get existing channels for this source
    existing = {ec.channel_id: ec for ec in EpgChannel.query.filter_by(source_id=source.id).all()}

    # Now update the database with collected channel data
    for channel_id, channel_data in channel_data_map.items():
        prog_stats = channel_program_stats.get(channel_id, {"count": 0, "first_time": None, "last_time": None})
        program_count = prog_stats["count"]
        first_program = prog_stats["first_time"]
        last_program = prog_stats["last_time"]

        if channel_id in existing:
            # Update existing channel from database
            ec = existing[channel_id]
            ec.display_name = channel_data["display_name"]
            ec.display_names_json = json.dumps(channel_data["display_names"])
            ec.icon_url = channel_data.get("icon_url")
            ec.url = channel_data.get("url")
            ec.program_count = program_count
            ec.first_program = first_program
            ec.last_program = last_program
            ec.last_seen = now
            ec.updated_at = now
            stats["channels_updated"] += 1
        else:
            # Create new channel
            ec = EpgChannel(
                source_id=source.id,
                channel_id=channel_id,
                display_name=channel_data["display_name"],
                display_names_json=json.dumps(channel_data["display_names"]),
                icon_url=channel_data.get("icon_url"),
                url=channel_data.get("url"),
                program_count=program_count,
                first_program=first_program,
                last_program=last_program,
                last_seen=now,
            )
            db.session.add(ec)
            processed_in_this_sync[channel_id] = ec
            stats["channels_added"] += 1

    # Mark channels not seen as removed (but don't delete - they may come back)
    for channel_id, ec in existing.items():
        if channel_id not in seen_channel_ids:
            stats["channels_removed"] += 1

    # Update source stats
    source.last_sync = now
    source.last_sync_status = "success"
    source.last_sync_message = f"Synced {len(seen_channel_ids)} channels, {stats['total_programs']} programs"
    source.channel_count = len(seen_channel_ids)
    source.updated_at = now

    db.session.commit()

    logger.info(
        f"EPG sync for source {source.id} ({source.name}): "
        f"added={stats['channels_added']}, updated={stats['channels_updated']}, "
        f"programs={stats['total_programs']}"
    )

    return stats
