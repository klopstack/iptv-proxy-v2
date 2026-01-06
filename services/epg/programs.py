"""
EPG Program Sync Service

Handles syncing EPG program data to the database from XMLTV sources.

Data Loading Strategy:
- For unmatched EPG channels: Load only the next X hours (configurable, default = EPG sync interval)
- For matched EPG channels: Load all available program data

This enables:
1. Efficient EPG generation without re-parsing large XML files
2. Display of current/upcoming programs in the UI for EPG matching verification
3. Search by program title when creating manual EPG mappings
"""
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterator, List, Optional, Set, Tuple

from models import ChannelEpgMapping, EpgChannel, EpgProgram, EpgSource, db
from services.epg.utils import get_decompressing_stream, parse_xmltv_time

logger = logging.getLogger(__name__)

# Default hours of data to store for unmatched channels
DEFAULT_PREVIEW_HOURS = 12

# Default batch size for database operations
DEFAULT_BATCH_SIZE = 500


def parse_xmltv_programs_streaming(
    xml_content: bytes,
    channel_filter: Optional[Set[str]] = None,
    start_after: Optional[datetime] = None,
    end_before: Optional[datetime] = None,
) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """
    Parse XMLTV content and yield programme elements as dictionaries.

    Args:
        xml_content: Raw XMLTV XML bytes (may be gzip-compressed)
        channel_filter: Optional set of channel IDs to include (None = all)
        start_after: Only include programs starting after this time
        end_before: Only include programs starting before this time

    Yields:
        Tuples of (channel_id, program_data_dict)
    """
    stream = get_decompressing_stream(xml_content)

    try:
        context = ET.iterparse(stream, events=("end",))

        for event, elem in context:
            if elem.tag == "programme":
                channel_id = elem.get("channel")

                # Apply channel filter
                if channel_filter and channel_id not in channel_filter:
                    elem.clear()
                    continue

                # Parse times
                start_str = elem.get("start")
                stop_str = elem.get("stop")

                start_time = parse_xmltv_time(start_str) if start_str else None
                stop_time = parse_xmltv_time(stop_str) if stop_str else None

                if not start_time or not stop_time:
                    elem.clear()
                    continue

                # Apply time filters
                if start_after and start_time < start_after:
                    elem.clear()
                    continue
                if end_before and start_time >= end_before:
                    elem.clear()
                    continue

                # Extract program data
                program = {
                    "channel_id": channel_id,
                    "start_time": start_time,
                    "stop_time": stop_time,
                }

                # Title (required)
                title_elem = elem.find("title")
                if title_elem is not None and title_elem.text:
                    program["title"] = title_elem.text.strip()[:500]
                else:
                    elem.clear()
                    continue  # Skip programs without title

                # Sub-title / episode title
                sub_elem = elem.find("sub-title")
                if sub_elem is not None and sub_elem.text:
                    program["sub_title"] = sub_elem.text.strip()[:500]

                # Description
                desc_elem = elem.find("desc")
                if desc_elem is not None and desc_elem.text:
                    program["description"] = desc_elem.text.strip()

                # Categories
                categories = []
                for cat_elem in elem.findall("category"):
                    if cat_elem.text:
                        categories.append(cat_elem.text.strip())
                if categories:
                    program["categories"] = categories

                # Episode numbers (try various formats)
                episode_num_elems = elem.findall("episode-num")
                for ep_elem in episode_num_elems:
                    system = ep_elem.get("system", "")
                    if system == "dd_progid" and ep_elem.text:
                        program["episode_id"] = ep_elem.text.strip()
                    elif system == "xmltv_ns" and ep_elem.text:
                        # Format: season.episode.part (e.g., "1.5.0/1")
                        parts = ep_elem.text.split(".")
                        if len(parts) >= 1 and parts[0]:
                            try:
                                # Season is 0-indexed
                                program["season"] = int(parts[0].split("/")[0]) + 1
                            except (ValueError, IndexError):
                                pass
                        if len(parts) >= 2 and parts[1]:
                            try:
                                # Episode is 0-indexed
                                program["episode"] = int(parts[1].split("/")[0]) + 1
                            except (ValueError, IndexError):
                                pass
                    elif system == "onscreen" and ep_elem.text:
                        # Onscreen format like "S1 E5"
                        text = ep_elem.text.upper()
                        import re

                        season_match = re.search(r"S(\d+)", text)
                        episode_match = re.search(r"E(\d+)", text)
                        if season_match:
                            program["season"] = int(season_match.group(1))
                        if episode_match:
                            program["episode"] = int(episode_match.group(1))

                # Rating
                rating_elem = elem.find("rating")
                if rating_elem is not None:
                    value_elem = rating_elem.find("value")
                    if value_elem is not None and value_elem.text:
                        program["rating"] = value_elem.text.strip()[:20]
                        system = rating_elem.get("system")
                        if system:
                            program["rating_system"] = system[:50]

                # Icon/image
                icon_elem = elem.find("icon")
                if icon_elem is not None:
                    src = icon_elem.get("src")
                    if src:
                        program["icon_url"] = src[:500]

                # Date / original air date
                date_elem = elem.find("date")
                if date_elem is not None and date_elem.text:
                    try:
                        date_str = date_elem.text.strip()[:8]
                        if len(date_str) == 8:
                            program["original_air_date"] = datetime.strptime(date_str, "%Y%m%d").date()
                    except ValueError:
                        pass

                # Flags
                if elem.find("new") is not None:
                    program["is_new"] = True
                if elem.find("premiere") is not None:
                    program["is_premiere"] = True
                if elem.find("live") is not None:
                    program["is_live"] = True

                # Check categories for sports-related info
                if categories:
                    cat_lower = [c.lower() for c in categories]
                    for sport_keyword in ["sports", "basketball", "football", "baseball", "hockey", "soccer"]:
                        if any(sport_keyword in c for c in cat_lower):
                            program["sport"] = next((c for c in categories if sport_keyword in c.lower()), None)
                            break

                yield (channel_id, program)

                elem.clear()

            # Clear tail text to prevent memory buildup
            if elem.tag in ("programme",):
                elem.tail = None

    except ET.ParseError as e:
        logger.error(f"Failed to parse XMLTV for programs: {e}")
        raise ValueError(f"Invalid XMLTV XML: {e}")
    finally:
        stream.close()


def get_matched_epg_channel_ids(source_id: int) -> Set[int]:
    """
    Get IDs of EPG channels that have at least one mapping.

    Args:
        source_id: The EPG source ID

    Returns:
        Set of epg_channel IDs that have mappings
    """
    # Get all EPG channel IDs for this source that have mappings
    result = (
        db.session.query(EpgChannel.id)
        .filter(EpgChannel.source_id == source_id)
        .join(ChannelEpgMapping, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .distinct()
        .all()
    )
    return {r[0] for r in result}


def get_epg_channel_id_map(source_id: int) -> Dict[str, int]:
    """
    Get mapping from XMLTV channel_id to database EpgChannel.id.

    Args:
        source_id: The EPG source ID

    Returns:
        Dict mapping channel_id string → EpgChannel.id
    """
    result = db.session.query(EpgChannel.channel_id, EpgChannel.id).filter(EpgChannel.source_id == source_id).all()
    return {channel_id: db_id for channel_id, db_id in result}


def sync_programs_for_source(
    source: EpgSource,
    xml_content: bytes,
    preview_hours: int = DEFAULT_PREVIEW_HOURS,
    load_all_for_matched: bool = True,
) -> Dict[str, int]:
    """
    Sync program data from XMLTV content to the database.

    Strategy:
    - For matched EPG channels (have ChannelEpgMapping): Load all available programs
    - For unmatched EPG channels: Load only next `preview_hours` of programs

    Args:
        source: The EpgSource being synced
        xml_content: Raw XMLTV XML bytes
        preview_hours: Hours of data to store for unmatched channels
        load_all_for_matched: If True, load all data for matched channels

    Returns:
        Dict with sync statistics
    """
    stats = {
        "programs_added": 0,
        "programs_updated": 0,
        "programs_deleted": 0,
        "channels_processed": 0,
        "matched_channels": 0,
        "preview_channels": 0,
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    preview_end = now + timedelta(hours=preview_hours)

    # Get channel ID mapping
    channel_id_map = get_epg_channel_id_map(source.id)
    if not channel_id_map:
        logger.warning(f"No EPG channels found for source {source.id}, skipping program sync")
        return stats

    # Get matched channel IDs
    matched_db_ids = get_matched_epg_channel_ids(source.id)

    # Create reverse map: XMLTV channel_id → is_matched
    matched_xmltv_ids = set()
    for xmltv_id, db_id in channel_id_map.items():
        if db_id in matched_db_ids:
            matched_xmltv_ids.add(xmltv_id)

    stats["matched_channels"] = len(matched_xmltv_ids)
    stats["preview_channels"] = len(channel_id_map) - len(matched_xmltv_ids)

    logger.info(
        f"Syncing programs for source {source.id} ({source.name}): "
        f"{len(matched_xmltv_ids)} matched channels (full data), "
        f"{stats['preview_channels']} preview channels ({preview_hours}h)"
    )

    # Collect programs by EPG channel
    programs_by_channel: Dict[int, List[Dict]] = {}

    for xmltv_channel_id, program_data in parse_xmltv_programs_streaming(xml_content):
        db_channel_id = channel_id_map.get(xmltv_channel_id)
        if not db_channel_id:
            continue

        is_matched = xmltv_channel_id in matched_xmltv_ids

        # Apply time filter for unmatched channels
        if not is_matched and not load_all_for_matched:
            start_time = program_data.get("start_time")
            if start_time and start_time >= preview_end:
                continue
            if start_time and start_time < now - timedelta(hours=1):
                # Skip programs that ended more than 1 hour ago for preview
                continue

        if db_channel_id not in programs_by_channel:
            programs_by_channel[db_channel_id] = []

        programs_by_channel[db_channel_id].append(program_data)

    stats["channels_processed"] = len(programs_by_channel)

    # Sync programs to database in batches
    batch_count = 0
    for db_channel_id, programs in programs_by_channel.items():
        is_matched = db_channel_id in matched_db_ids

        # Delete old programs for this channel
        if is_matched:
            # For matched channels, delete programs older than 1 hour ago
            deleted = EpgProgram.query.filter(
                EpgProgram.epg_channel_id == db_channel_id,
                EpgProgram.stop_time < now - timedelta(hours=1),
            ).delete(synchronize_session=False)
        else:
            # For unmatched channels, delete all programs outside preview window
            deleted = EpgProgram.query.filter(
                EpgProgram.epg_channel_id == db_channel_id,
                db.or_(
                    EpgProgram.stop_time < now - timedelta(hours=1),
                    EpgProgram.start_time >= preview_end,
                ),
            ).delete(synchronize_session=False)
        stats["programs_deleted"] += deleted

        # Get existing programs for this channel (by start time)
        existing = {p.start_time: p for p in EpgProgram.query.filter_by(epg_channel_id=db_channel_id).all()}

        for prog_data in programs:
            start_time = prog_data["start_time"]
            existing_prog = existing.get(start_time)

            if existing_prog:
                # Update existing program
                _update_program(existing_prog, prog_data)
                stats["programs_updated"] += 1
            else:
                # Create new program
                new_prog = _create_program(db_channel_id, prog_data)
                db.session.add(new_prog)
                stats["programs_added"] += 1

        batch_count += 1
        if batch_count % DEFAULT_BATCH_SIZE == 0:
            db.session.commit()

    db.session.commit()

    logger.info(
        f"Program sync complete for source {source.id}: "
        f"added={stats['programs_added']}, updated={stats['programs_updated']}, "
        f"deleted={stats['programs_deleted']}, channels={stats['channels_processed']}"
    )

    return stats


def _create_program(epg_channel_id: int, data: Dict[str, Any]) -> EpgProgram:
    """Create a new EpgProgram from parsed data."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    prog = EpgProgram(
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
    return prog


def _update_program(prog: EpgProgram, data: Dict[str, Any]):
    """Update an existing EpgProgram with new data."""
    prog.stop_time = data["stop_time"]
    prog.title = data["title"]
    prog.sub_title = data.get("sub_title")
    prog.description = data.get("description")
    prog.categories = json.dumps(data["categories"]) if data.get("categories") else None
    prog.season = data.get("season")
    prog.episode = data.get("episode")
    prog.episode_id = data.get("episode_id")
    prog.rating = data.get("rating")
    prog.rating_system = data.get("rating_system")
    prog.original_air_date = data.get("original_air_date")
    prog.is_new = data.get("is_new", False)
    prog.is_live = data.get("is_live", False)
    prog.is_premiere = data.get("is_premiere", False)
    prog.sport = data.get("sport")
    prog.team_home = data.get("team_home")
    prog.team_away = data.get("team_away")
    prog.icon_url = data.get("icon_url")
    prog.last_updated = datetime.now(timezone.utc).replace(tzinfo=None)


def get_current_program(epg_channel_id: int) -> Optional[EpgProgram]:
    """
    Get the currently airing program for an EPG channel.

    Args:
        epg_channel_id: The EpgChannel database ID

    Returns:
        The currently airing EpgProgram, or None
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return EpgProgram.query.filter(
        EpgProgram.epg_channel_id == epg_channel_id,
        EpgProgram.start_time <= now,
        EpgProgram.stop_time > now,
    ).first()


def get_current_programs_batch(epg_channel_ids: List[int]) -> Dict[int, EpgProgram]:
    """
    Get currently airing programs for multiple EPG channels efficiently.

    Args:
        epg_channel_ids: List of EpgChannel database IDs

    Returns:
        Dict mapping epg_channel_id → EpgProgram (for channels with current programs)
    """
    if not epg_channel_ids:
        return {}

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Query all current programs in one go
    programs = EpgProgram.query.filter(
        EpgProgram.epg_channel_id.in_(epg_channel_ids),
        EpgProgram.start_time <= now,
        EpgProgram.stop_time > now,
    ).all()

    return {p.epg_channel_id: p for p in programs}


def get_upcoming_programs(
    epg_channel_id: int,
    hours: int = 24,
    limit: int = 20,
) -> List[EpgProgram]:
    """
    Get upcoming programs for an EPG channel.

    Args:
        epg_channel_id: The EpgChannel database ID
        hours: Number of hours ahead to look
        limit: Maximum number of programs to return

    Returns:
        List of upcoming EpgProgram objects
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    end_time = now + timedelta(hours=hours)

    return (
        EpgProgram.query.filter(
            EpgProgram.epg_channel_id == epg_channel_id,
            EpgProgram.start_time >= now,
            EpgProgram.start_time < end_time,
        )
        .order_by(EpgProgram.start_time)
        .limit(limit)
        .all()
    )


def search_programs_by_title(
    title_query: str,
    source_id: Optional[int] = None,
    include_current_only: bool = False,
    limit: int = 100,
) -> list:
    """
    Search for programs by title.

    Args:
        title_query: Search string for program title
        source_id: Optional EPG source to limit search to
        include_current_only: If True, only return currently airing programs
        limit: Maximum results to return

    Returns:
        List of (EpgProgram, EpgChannel) rows
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    query = db.session.query(EpgProgram, EpgChannel).join(EpgChannel, EpgProgram.epg_channel_id == EpgChannel.id)

    # Apply title search (case-insensitive)
    search_words = title_query.strip().split()
    for word in search_words:
        search_term = f"%{word}%"
        query = query.filter(EpgProgram.title.ilike(search_term))

    # Apply source filter
    if source_id:
        query = query.filter(EpgChannel.source_id == source_id)

    # Apply time filter
    if include_current_only:
        query = query.filter(
            EpgProgram.start_time <= now,
            EpgProgram.stop_time > now,
        )
    else:
        # Include current and future programs (not past)
        query = query.filter(EpgProgram.stop_time > now)

    return query.order_by(EpgProgram.start_time).limit(limit).all()


def get_schedule_around_time(
    epg_channel_id: int,
    reference_time: Optional[datetime] = None,
    offset_hours: int = 0,
    hours_before: int = 2,
    hours_after: int = 4,
) -> Dict[str, Any]:
    """
    Get the program schedule around a reference time for an EPG channel.

    This is useful for displaying the schedule when adjusting time offsets,
    showing what's on before and after the "current" program.

    Args:
        epg_channel_id: The EpgChannel database ID
        reference_time: The time to center the schedule on (default: now)
        offset_hours: Time offset in hours to apply to the reference time
        hours_before: How many hours of past programs to include
        hours_after: How many hours of future programs to include

    Returns:
        Dict with current_program, programs_before, programs_after, and metadata
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc).replace(tzinfo=None)

    # Apply the time offset (positive offset means EPG is ahead of real time)
    adjusted_time = reference_time + timedelta(hours=offset_hours)
    start_window = adjusted_time - timedelta(hours=hours_before)
    end_window = adjusted_time + timedelta(hours=hours_after)

    # Get all programs in the window
    programs = (
        EpgProgram.query.filter(
            EpgProgram.epg_channel_id == epg_channel_id,
            EpgProgram.stop_time > start_window,
            EpgProgram.start_time < end_window,
        )
        .order_by(EpgProgram.start_time)
        .all()
    )

    # Split into before, current, and after
    current_program = None
    programs_before = []
    programs_after = []

    for prog in programs:
        if prog.start_time <= adjusted_time < prog.stop_time:
            current_program = prog
        elif prog.stop_time <= adjusted_time:
            programs_before.append(prog)
        else:
            programs_after.append(prog)

    return {
        "epg_channel_id": epg_channel_id,
        "reference_time": reference_time.isoformat(),
        "adjusted_time": adjusted_time.isoformat(),
        "offset_hours": offset_hours,
        "current_program": current_program.to_dict() if current_program else None,
        "programs_before": [p.to_dict() for p in programs_before[-5:]],  # Last 5 before
        "programs_after": [p.to_dict() for p in programs_after[:5]],  # Next 5 after
    }


def cleanup_expired_programs(days_old: int = 1) -> int:
    """
    Remove programs that ended more than `days_old` days ago.

    Args:
        days_old: Delete programs older than this many days

    Returns:
        Number of programs deleted
    """
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_old)
    deleted = EpgProgram.query.filter(EpgProgram.stop_time < cutoff).delete(synchronize_session=False)
    db.session.commit()
    logger.info(f"Cleaned up {deleted} expired programs older than {days_old} days")
    return deleted


# =============================================================================
# Database-Based EPG Generation Functions
# =============================================================================
#
# These functions generate XMLTV EPG data directly from the EpgProgram database
# records, avoiding the need to re-parse cached XMLTV XML files.
#


def get_programs_for_channels(
    epg_channel_ids: List[int],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    batch_size: int = 500,
) -> Dict[int, List[EpgProgram]]:
    """
    Get programs for multiple EPG channels from the database.

    Args:
        epg_channel_ids: List of EpgChannel database IDs
        start_time: Start of time range (default: now - 1 hour)
        end_time: End of time range (default: now + 24 hours)
        batch_size: Number of channel IDs to query at once

    Returns:
        Dict mapping epg_channel_id -> List[EpgProgram]
    """
    if not epg_channel_ids:
        return {}

    if start_time is None:
        start_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    if end_time is None:
        end_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24)

    result: Dict[int, List[EpgProgram]] = {cid: [] for cid in epg_channel_ids}

    # Query in batches to avoid memory issues with large channel lists
    for i in range(0, len(epg_channel_ids), batch_size):
        batch = epg_channel_ids[i : i + batch_size]

        programs = (
            EpgProgram.query.filter(
                EpgProgram.epg_channel_id.in_(batch),
                EpgProgram.stop_time > start_time,
                EpgProgram.start_time < end_time,
            )
            .order_by(EpgProgram.epg_channel_id, EpgProgram.start_time)
            .all()
        )

        for prog in programs:
            if prog.epg_channel_id in result:
                result[prog.epg_channel_id].append(prog)

    return result


def format_xmltv_time(dt: datetime, offset_hours: int = 0) -> str:
    """
    Format a datetime as XMLTV time string with optional offset.

    Args:
        dt: Datetime to format (should be UTC)
        offset_hours: Hours to offset (positive = later)

    Returns:
        XMLTV time string like "20260106120000 +0000"
    """
    if offset_hours != 0:
        dt = dt + timedelta(hours=offset_hours)
    return dt.strftime("%Y%m%d%H%M%S +0000")


def program_to_xmltv_element(
    program: EpgProgram,
    channel_id: str,
    time_offset_hours: int = 0,
) -> "ET.Element":
    """
    Convert an EpgProgram database record to an XMLTV programme element.

    This is a pure function that doesn't access the database, making it
    easily testable.

    Args:
        program: EpgProgram database record
        channel_id: Channel ID to use in the programme element
        time_offset_hours: Hours to offset program times

    Returns:
        ElementTree programme element
    """
    import xml.etree.ElementTree as ET

    prog_elem = ET.Element("programme")
    prog_elem.set("start", format_xmltv_time(program.start_time, time_offset_hours))
    prog_elem.set("stop", format_xmltv_time(program.stop_time, time_offset_hours))
    prog_elem.set("channel", channel_id)

    # Title (required)
    title_elem = ET.SubElement(prog_elem, "title")
    title_elem.set("lang", "en")
    title_elem.text = program.title

    # Sub-title / episode title
    if program.sub_title:
        sub_elem = ET.SubElement(prog_elem, "sub-title")
        sub_elem.set("lang", "en")
        sub_elem.text = program.sub_title

    # Description
    if program.description:
        desc_elem = ET.SubElement(prog_elem, "desc")
        desc_elem.set("lang", "en")
        desc_elem.text = program.description

    # Categories
    categories = program.get_categories_list()
    for cat in categories:
        cat_elem = ET.SubElement(prog_elem, "category")
        cat_elem.set("lang", "en")
        cat_elem.text = cat

    # Episode numbering
    if program.season or program.episode:
        # XMLTV NS format (0-indexed)
        season_part = str(program.season - 1) if program.season else ""
        episode_part = str(program.episode - 1) if program.episode else ""
        ep_num_elem = ET.SubElement(prog_elem, "episode-num")
        ep_num_elem.set("system", "xmltv_ns")
        ep_num_elem.text = f"{season_part}.{episode_part}."

        # Onscreen format (human readable)
        if program.season and program.episode:
            ep_num_elem2 = ET.SubElement(prog_elem, "episode-num")
            ep_num_elem2.set("system", "onscreen")
            ep_num_elem2.text = f"S{program.season:02d}E{program.episode:02d}"

    # Episode ID (dd_progid)
    if program.episode_id:
        ep_id_elem = ET.SubElement(prog_elem, "episode-num")
        ep_id_elem.set("system", "dd_progid")
        ep_id_elem.text = program.episode_id

    # Rating
    if program.rating:
        rating_elem = ET.SubElement(prog_elem, "rating")
        if program.rating_system:
            rating_elem.set("system", program.rating_system)
        value_elem = ET.SubElement(rating_elem, "value")
        value_elem.text = program.rating

    # Icon
    if program.icon_url:
        ET.SubElement(prog_elem, "icon", src=program.icon_url)

    # Original air date
    if program.original_air_date:
        date_elem = ET.SubElement(prog_elem, "date")
        date_elem.text = program.original_air_date.strftime("%Y%m%d")

    # Flags
    if program.is_new:
        ET.SubElement(prog_elem, "new")
    if program.is_premiere:
        ET.SubElement(prog_elem, "premiere")
    if program.is_live:
        ET.SubElement(prog_elem, "live")

    return prog_elem


def epg_channel_to_xmltv_element(
    epg_channel: "EpgChannel",
    output_channel_id: str,
) -> "ET.Element":
    """
    Convert an EpgChannel database record to an XMLTV channel element.

    Args:
        epg_channel: EpgChannel database record
        output_channel_id: Channel ID to use in the output

    Returns:
        ElementTree channel element
    """
    import xml.etree.ElementTree as ET

    channel_elem = ET.Element("channel")
    channel_elem.set("id", output_channel_id)

    # Display name (use display_name or channel_id)
    display_name_elem = ET.SubElement(channel_elem, "display-name")
    display_name_elem.text = epg_channel.display_name or epg_channel.channel_id or output_channel_id

    # Additional display names from JSON field
    if epg_channel.display_names_json:
        try:
            names = json.loads(epg_channel.display_names_json)
            for name in names:
                if name and name != display_name_elem.text:
                    extra_name = ET.SubElement(channel_elem, "display-name")
                    extra_name.text = name
        except (json.JSONDecodeError, TypeError):
            pass

    # Icon
    if epg_channel.icon_url:
        ET.SubElement(channel_elem, "icon", src=epg_channel.icon_url)

    return channel_elem


def generate_xmltv_from_database(
    channel_mappings: List[Tuple[int, str, int, Optional["EpgChannel"]]],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
) -> bytes:
    """
    Generate XMLTV XML directly from database program records.

    This is the main database-based EPG generation function. It retrieves
    programs from the EpgProgram table and generates XMLTV XML without
    needing to parse cached XML files.

    Args:
        channel_mappings: List of (epg_channel_id, output_channel_id, time_offset, epg_channel)
            - epg_channel_id: Database ID of the EpgChannel
            - output_channel_id: Channel ID to use in output XML (e.g., "ch-1-100")
            - time_offset: Hours to offset program times
            - epg_channel: Optional EpgChannel object for channel metadata
        start_time: Start of program range (default: now - 1 hour)
        end_time: End of program range (default: now + 24 hours)

    Returns:
        XMLTV XML as bytes
    """
    import xml.etree.ElementTree as ET

    if not channel_mappings:
        return b'<?xml version="1.0" encoding="UTF-8"?>\n<tv generator-info-name="iptv-proxy-v2"></tv>\n'

    # Build root element
    root = ET.Element("tv")
    root.set("generator-info-name", "iptv-proxy-v2")
    root.set("source-info-name", "database")

    # Get unique EPG channel IDs
    epg_channel_ids = list({cm[0] for cm in channel_mappings})

    # Fetch programs for all channels
    programs_by_channel = get_programs_for_channels(epg_channel_ids, start_time, end_time)

    # Track which channels have programs
    channels_with_programs: Set[int] = set()

    # Build lookup: epg_channel_id -> list of (output_id, offset, epg_channel)
    channel_lookup: Dict[int, List[Tuple[str, int, Optional[EpgChannel]]]] = {}
    for epg_channel_id, output_id, offset, epg_channel in channel_mappings:
        if epg_channel_id not in channel_lookup:
            channel_lookup[epg_channel_id] = []
        channel_lookup[epg_channel_id].append((output_id, offset, epg_channel))

    # Add channel elements first
    added_output_ids: Set[str] = set()
    for epg_channel_id, output_mappings in channel_lookup.items():
        for output_id, offset, epg_channel in output_mappings:
            if output_id in added_output_ids:
                continue
            added_output_ids.add(output_id)

            if epg_channel:
                channel_elem = epg_channel_to_xmltv_element(epg_channel, output_id)
            else:
                # Minimal channel element if no EpgChannel provided
                channel_elem = ET.Element("channel")
                channel_elem.set("id", output_id)
                display_name = ET.SubElement(channel_elem, "display-name")
                display_name.text = output_id

            root.append(channel_elem)

    # Add programme elements
    for epg_channel_id, programs in programs_by_channel.items():
        if not programs:
            continue

        channels_with_programs.add(epg_channel_id)

        output_mappings = channel_lookup.get(epg_channel_id, [])
        for program in programs:
            for output_id, offset, _ in output_mappings:
                prog_elem = program_to_xmltv_element(program, output_id, offset)
                root.append(prog_elem)

    # Log stats
    total_programs = sum(len(progs) for progs in programs_by_channel.values())
    logger.debug(
        f"Generated XMLTV from database: {len(channel_mappings)} channel mappings, "
        f"{len(channels_with_programs)} channels with programs, {total_programs} total programs"
    )

    return ET.tostring(root, encoding="unicode", xml_declaration=True).encode("utf-8")


def has_programs_in_database(epg_channel_id: int) -> bool:
    """
    Check if an EPG channel has any programs in the database.

    Args:
        epg_channel_id: EpgChannel database ID

    Returns:
        True if there are current/future programs for this channel
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (
        EpgProgram.query.filter(
            EpgProgram.epg_channel_id == epg_channel_id,
            EpgProgram.stop_time > now,
        ).first()
        is not None
    )


def get_database_coverage_stats(source_id: int) -> Dict[str, Any]:
    """
    Get statistics about program database coverage for an EPG source.

    Args:
        source_id: EpgSource database ID

    Returns:
        Dict with coverage statistics
    """
    from models import EpgChannel

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # Get all channels for this source
    channels = EpgChannel.query.filter_by(source_id=source_id).all()

    total_channels = len(channels)
    channels_with_programs = 0
    total_programs = 0
    channels_with_future_programs = 0

    for channel in channels:
        program_count = EpgProgram.query.filter(
            EpgProgram.epg_channel_id == channel.id,
            EpgProgram.stop_time > now,
        ).count()

        if program_count > 0:
            channels_with_programs += 1
            total_programs += program_count

            # Check if there are programs in the future
            future_count = EpgProgram.query.filter(
                EpgProgram.epg_channel_id == channel.id,
                EpgProgram.start_time > now,
            ).count()
            if future_count > 0:
                channels_with_future_programs += 1

    return {
        "source_id": source_id,
        "total_channels": total_channels,
        "channels_with_programs": channels_with_programs,
        "channels_with_future_programs": channels_with_future_programs,
        "total_programs": total_programs,
        "coverage_percent": (round(channels_with_programs / total_channels * 100, 1) if total_channels > 0 else 0),
    }
