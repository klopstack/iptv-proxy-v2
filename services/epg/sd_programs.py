"""
Schedules Direct Program Sync Service

Handles syncing EPG program data from Schedules Direct to the EpgProgram database.

Unlike XMLTV-based sources, Schedules Direct requires:
1. Fetching station schedules (list of program IDs per station)
2. Fetching program details (full program info by program ID)
3. Converting SD's data model to our EpgProgram model

This module provides functions to sync SD program data to the database,
enabling database-based EPG generation without re-fetching from SD.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from models import ChannelEpgMapping, EpgChannel, EpgProgram, EpgSource, db

logger = logging.getLogger(__name__)

# Default hours of data to fetch
DEFAULT_DAYS_AHEAD = 14
DEFAULT_BATCH_SIZE = 500


def get_sd_station_ids_for_source(source_id: int) -> Dict[str, int]:
    """
    Get Schedules Direct station IDs for an EPG source.

    SD EpgChannel records have channel_id in the format:
    "I{station_id}.json.schedulesdirect.org"

    Args:
        source_id: The EpgSource database ID

    Returns:
        Dict mapping station_id (string) -> epg_channel.id (int)
    """
    import re

    result = {}
    channels = EpgChannel.query.filter_by(source_id=source_id).all()

    for channel in channels:
        if not channel.channel_id:
            continue

        # Extract station ID from SD channel ID format
        match = re.match(r"I(\d+)\.json\.schedulesdirect\.org", channel.channel_id, re.IGNORECASE)
        if match:
            station_id = match.group(1)
            result[station_id] = channel.id
        else:
            # Fallback: might be just the station ID
            if channel.channel_id.isdigit():
                result[channel.channel_id] = channel.id

    return result


def parse_sd_schedule_time(time_str: str) -> Optional[datetime]:
    """
    Parse Schedules Direct schedule time format.

    SD uses ISO 8601 format: "2026-01-06T12:00:00Z"

    Args:
        time_str: Time string from SD schedule

    Returns:
        Parsed datetime (naive UTC) or None
    """
    if not time_str:
        return None

    try:
        # Remove Z suffix and parse
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        # Convert to naive UTC
        return dt.replace(tzinfo=None)
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse SD time: {time_str}")
        return None


def convert_sd_program_to_epg_data(
    schedule_entry: Dict[str, Any],
    program_details: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Convert Schedules Direct schedule and program data to EpgProgram fields.

    Args:
        schedule_entry: Schedule entry from get_schedules()
        program_details: Optional detailed program info from get_programs()

    Returns:
        Dict with EpgProgram field values, or None if conversion fails
    """
    air_time = schedule_entry.get("airDateTime")
    if not air_time:
        return None

    start_time = parse_sd_schedule_time(air_time)
    if not start_time:
        return None

    duration_minutes = schedule_entry.get("duration", 0)
    if not duration_minutes:
        return None

    stop_time = start_time + timedelta(minutes=duration_minutes)

    # Get program ID for episode tracking
    program_id = schedule_entry.get("programID", "")

    # Initialize data from schedule entry
    data: Dict[str, Any] = {
        "start_time": start_time,
        "stop_time": stop_time,
        "episode_id": program_id,
        "is_new": schedule_entry.get("new", False),
        "is_live": schedule_entry.get("liveTapeDelay") == "Live",
        "is_premiere": schedule_entry.get("premiere", False),
    }

    # Extract rating from schedule if present
    ratings = schedule_entry.get("ratings", [])
    if ratings:
        data["rating"] = ratings[0].get("code")
        data["rating_system"] = ratings[0].get("body")

    # If we have detailed program info, use it
    if program_details:
        # Title (required)
        titles = program_details.get("titles", [])
        if titles:
            data["title"] = titles[0].get("title120", "")[:500]
        else:
            data["title"] = schedule_entry.get("programID", "Unknown")

        # Episode title
        if program_details.get("episodeTitle150"):
            data["sub_title"] = program_details["episodeTitle150"][:500]

        # Description
        descriptions = program_details.get("descriptions", {})
        if "description1000" in descriptions:
            desc_list = descriptions["description1000"]
            if desc_list:
                data["description"] = desc_list[0].get("description", "")
        elif "description100" in descriptions:
            desc_list = descriptions["description100"]
            if desc_list:
                data["description"] = desc_list[0].get("description", "")

        # Genres -> Categories
        if program_details.get("genres"):
            data["categories"] = program_details["genres"]

        # Season/Episode from metadata
        if program_details.get("metadata"):
            for meta in program_details["metadata"]:
                for source, info in meta.items():
                    if info.get("season") is not None:
                        data["season"] = info["season"]
                        data["episode"] = info.get("episode")
                        break

        # Original air date
        if program_details.get("originalAirDate"):
            try:
                date_str = program_details["originalAirDate"][:10]  # YYYY-MM-DD
                data["original_air_date"] = datetime.strptime(date_str, "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

        # Content ratings (use first if not already set)
        if not data.get("rating") and program_details.get("contentRating"):
            cr = program_details["contentRating"][0]
            data["rating"] = cr.get("code")
            data["rating_system"] = cr.get("body")

        # Sports event details
        event_details = program_details.get("eventDetails", {})
        if event_details:
            data["sport"] = program_details.get("entityType")
            teams = event_details.get("teams", [])
            if len(teams) >= 2:
                # Find home/away or use first two
                for team in teams:
                    if team.get("isHome"):
                        data["team_home"] = team.get("name")
                    else:
                        if "team_away" not in data or not data["team_away"]:
                            data["team_away"] = team.get("name")
                if not data.get("team_home") and teams:
                    data["team_home"] = teams[0].get("name")
                if not data.get("team_away") and len(teams) > 1:
                    data["team_away"] = teams[1].get("name")
    else:
        # Minimal data from schedule entry only
        data["title"] = schedule_entry.get("programID", "Unknown")

    # Ensure title is set
    if not data.get("title"):
        data["title"] = schedule_entry.get("programID", "Unknown Program")

    return data


def sync_sd_programs_for_source(
    source: EpgSource,
    sd_client: Any,  # SchedulesDirectClient
    days_ahead: int = DEFAULT_DAYS_AHEAD,
    fetch_program_details: bool = True,
) -> Dict[str, int]:
    """
    Sync program data from Schedules Direct to the database.

    This is the main entry point for SD program syncing.

    Args:
        source: The EpgSource with type='schedules_direct'
        sd_client: Authenticated SchedulesDirectClient instance
        days_ahead: Number of days of schedule data to fetch
        fetch_program_details: Whether to fetch detailed program info

    Returns:
        Dict with sync statistics
    """
    from services.schedules_direct import MAX_PROGRAMS_PER_REQUEST

    stats = {
        "programs_added": 0,
        "programs_updated": 0,
        "programs_deleted": 0,
        "channels_processed": 0,
        "schedules_fetched": 0,
        "programs_fetched": 0,
    }

    # Get station ID -> epg_channel.id mapping
    station_map = get_sd_station_ids_for_source(source.id)
    if not station_map:
        logger.warning(f"No SD stations found for source {source.id}")
        return stats

    station_ids = list(station_map.keys())
    logger.info(f"Syncing SD programs for {len(station_ids)} stations in source {source.id} ({source.name})")

    # Build date list
    today = datetime.now(timezone.utc).replace(tzinfo=None)
    dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_ahead)]

    # Fetch schedules in batches (SD recommends not too many stations at once)
    batch_size = 500
    all_schedule_entries: List[Tuple[int, Dict]] = []  # (epg_channel_id, schedule_entry)
    program_ids_to_fetch: Set[str] = set()

    for i in range(0, len(station_ids), batch_size):
        batch = station_ids[i : i + batch_size]

        try:
            schedules = sd_client.get_schedules(batch, dates)
            stats["schedules_fetched"] += len(schedules)

            for schedule in schedules:
                station_id = schedule.get("stationID")
                epg_channel_id = station_map.get(station_id)
                if not epg_channel_id:
                    continue

                for entry in schedule.get("programs", []):
                    all_schedule_entries.append((epg_channel_id, entry))
                    if fetch_program_details:
                        prog_id = entry.get("programID")
                        if prog_id:
                            program_ids_to_fetch.add(prog_id)

        except Exception as e:
            logger.error(f"Failed to fetch SD schedules for batch: {e}")
            continue

    logger.info(f"Fetched {len(all_schedule_entries)} schedule entries, {len(program_ids_to_fetch)} unique programs")

    # Fetch program details (in batches of MAX_PROGRAMS_PER_REQUEST)
    program_details_map: Dict[str, Dict] = {}
    if fetch_program_details and program_ids_to_fetch:
        prog_ids = list(program_ids_to_fetch)
        for i in range(0, len(prog_ids), MAX_PROGRAMS_PER_REQUEST):
            batch = prog_ids[i : i + MAX_PROGRAMS_PER_REQUEST]
            try:
                programs = sd_client.get_programs(batch)
                stats["programs_fetched"] += len(programs)

                for prog in programs:
                    # Skip error responses
                    if "code" in prog and prog["code"] != 0:
                        continue
                    prog_id = prog.get("programID")
                    if prog_id:
                        program_details_map[prog_id] = prog

            except Exception as e:
                logger.error(f"Failed to fetch SD programs batch: {e}")
                continue

    logger.info(f"Fetched details for {len(program_details_map)} programs")

    # Group schedule entries by epg_channel_id
    entries_by_channel: Dict[int, List[Dict]] = {}
    for epg_channel_id, entry in all_schedule_entries:
        if epg_channel_id not in entries_by_channel:
            entries_by_channel[epg_channel_id] = []
        entries_by_channel[epg_channel_id].append(entry)

    stats["channels_processed"] = len(entries_by_channel)

    # Sync to database
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for epg_channel_id, entries in entries_by_channel.items():
        # Delete old programs for this channel
        deleted = EpgProgram.query.filter(
            EpgProgram.epg_channel_id == epg_channel_id,
            EpgProgram.stop_time < now - timedelta(hours=1),
        ).delete(synchronize_session=False)
        stats["programs_deleted"] += deleted

        # Get existing programs by start time
        existing = {p.start_time: p for p in EpgProgram.query.filter_by(epg_channel_id=epg_channel_id).all()}

        for entry in entries:
            prog_id = entry.get("programID")
            prog_details = program_details_map.get(prog_id)

            data = convert_sd_program_to_epg_data(entry, prog_details)
            if not data:
                continue

            start_time = data["start_time"]
            existing_prog = existing.get(start_time)

            if existing_prog:
                # Update existing
                _update_epg_program(existing_prog, data)
                stats["programs_updated"] += 1
            else:
                # Create new
                new_prog = _create_epg_program(epg_channel_id, data)
                db.session.add(new_prog)
                stats["programs_added"] += 1

        # Commit in batches
        if (stats["programs_added"] + stats["programs_updated"]) % DEFAULT_BATCH_SIZE == 0:
            db.session.commit()

    db.session.commit()

    logger.info(
        f"SD program sync complete for source {source.id}: "
        f"added={stats['programs_added']}, updated={stats['programs_updated']}, "
        f"deleted={stats['programs_deleted']}, channels={stats['channels_processed']}"
    )

    return stats


def _create_epg_program(epg_channel_id: int, data: Dict[str, Any]) -> EpgProgram:
    """Create a new EpgProgram from parsed SD data."""
    import json

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


def _update_epg_program(prog: EpgProgram, data: Dict[str, Any]):
    """Update an existing EpgProgram with new SD data."""
    import json

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
