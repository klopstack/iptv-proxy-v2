"""XMLTV program parsing and database sync."""

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

from models import ChannelEpgMapping, EpgChannel, EpgProgram, EpgSource, db
from services.epg.program_persistence import create_epg_program as _create_program
from services.epg.program_persistence import update_epg_program as _update_program
from services.epg.utils import get_decompressing_stream, parse_xmltv_time

ProgressCallback = Optional[Callable[..., None]]

logger = logging.getLogger(__name__)

DEFAULT_PREVIEW_HOURS = 12
DEFAULT_BATCH_SIZE = 500
CHANNEL_PROGRAM_BUFFER_FLUSH = 250


def parse_xmltv_programs_streaming(
    xml_content: bytes,
    channel_filter: Optional[Set[str]] = None,
    start_after: Optional[datetime] = None,
    end_before: Optional[datetime] = None,
) -> Iterator[Tuple[str, Dict[str, Any]]]:
    """Parse XMLTV content and yield programme elements as dictionaries."""
    stream = get_decompressing_stream(xml_content)

    try:
        context = ET.iterparse(stream, events=("end",))

        for event, elem in context:
            if elem.tag == "programme":
                channel_id = elem.get("channel")

                if channel_filter and channel_id not in channel_filter:
                    elem.clear()
                    continue

                start_str = elem.get("start")
                stop_str = elem.get("stop")

                start_time = parse_xmltv_time(start_str) if start_str else None
                stop_time = parse_xmltv_time(stop_str) if stop_str else None

                if not start_time or not stop_time:
                    elem.clear()
                    continue

                if start_after and start_time < start_after:
                    elem.clear()
                    continue
                if end_before and start_time >= end_before:
                    elem.clear()
                    continue

                program = {
                    "channel_id": channel_id,
                    "start_time": start_time,
                    "stop_time": stop_time,
                }

                title_elem = elem.find("title")
                if title_elem is not None and title_elem.text:
                    program["title"] = title_elem.text.strip()[:500]
                else:
                    elem.clear()
                    continue

                sub_elem = elem.find("sub-title")
                if sub_elem is not None and sub_elem.text:
                    program["sub_title"] = sub_elem.text.strip()[:500]

                desc_elem = elem.find("desc")
                if desc_elem is not None and desc_elem.text:
                    program["description"] = desc_elem.text.strip()

                categories = []
                for cat_elem in elem.findall("category"):
                    if cat_elem.text:
                        categories.append(cat_elem.text.strip())
                if categories:
                    program["categories"] = categories

                episode_num_elems = elem.findall("episode-num")
                for ep_elem in episode_num_elems:
                    system = ep_elem.get("system", "")
                    if system == "dd_progid" and ep_elem.text:
                        program["episode_id"] = ep_elem.text.strip()
                    elif system == "xmltv_ns" and ep_elem.text:
                        parts = ep_elem.text.split(".")
                        if len(parts) >= 1 and parts[0]:
                            try:
                                program["season"] = int(parts[0].split("/")[0]) + 1
                            except (ValueError, IndexError):
                                pass
                        if len(parts) >= 2 and parts[1]:
                            try:
                                program["episode"] = int(parts[1].split("/")[0]) + 1
                            except (ValueError, IndexError):
                                pass
                    elif system == "onscreen" and ep_elem.text:
                        text = ep_elem.text.upper()
                        season_match = re.search(r"S(\d+)", text)
                        episode_match = re.search(r"E(\d+)", text)
                        if season_match:
                            program["season"] = int(season_match.group(1))
                        if episode_match:
                            program["episode"] = int(episode_match.group(1))

                rating_elem = elem.find("rating")
                if rating_elem is not None:
                    value_elem = rating_elem.find("value")
                    if value_elem is not None and value_elem.text:
                        program["rating"] = value_elem.text.strip()[:20]
                        system = rating_elem.get("system")
                        if system:
                            program["rating_system"] = system[:50]

                icon_elem = elem.find("icon")
                if icon_elem is not None:
                    src = icon_elem.get("src")
                    if src:
                        program["icon_url"] = src[:500]

                date_elem = elem.find("date")
                if date_elem is not None and date_elem.text:
                    try:
                        date_str = date_elem.text.strip()[:8]
                        if len(date_str) == 8:
                            program["original_air_date"] = datetime.strptime(date_str, "%Y%m%d").date()
                    except ValueError:
                        pass

                if elem.find("new") is not None:
                    program["is_new"] = True
                if elem.find("premiere") is not None:
                    program["is_premiere"] = True
                if elem.find("live") is not None:
                    program["is_live"] = True

                if categories:
                    cat_lower = [c.lower() for c in categories]
                    for sport_keyword in ["sports", "basketball", "football", "baseball", "hockey", "soccer"]:
                        if any(sport_keyword in c for c in cat_lower):
                            program["sport"] = next((c for c in categories if sport_keyword in c.lower()), None)
                            break

                yield (channel_id, program)
                elem.clear()

            if elem.tag in ("programme",):
                elem.tail = None

    except ET.ParseError as e:
        logger.error(f"Failed to parse XMLTV for programs: {e}")
        raise ValueError(f"Invalid XMLTV XML: {e}")
    finally:
        stream.close()


def get_matched_epg_channel_ids(source_id: int) -> Set[int]:
    """Get IDs of EPG channels that have at least one mapping."""
    result = (
        db.session.query(EpgChannel.id)
        .filter(EpgChannel.source_id == source_id)
        .join(ChannelEpgMapping, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
        .distinct()
        .all()
    )
    return {r[0] for r in result}


def get_epg_channel_id_map(source_id: int) -> Dict[str, int]:
    """Get mapping from XMLTV channel_id to database EpgChannel.id."""
    result = db.session.query(EpgChannel.channel_id, EpgChannel.id).filter(EpgChannel.source_id == source_id).all()
    return {channel_id: db_id for channel_id, db_id in result}


def _flush_channel_programs(
    db_channel_id: int,
    programs: List[Dict[str, Any]],
    *,
    is_matched: bool,
    matched_db_ids: Set[int],
    now: datetime,
    preview_end: datetime,
    stats: Dict[str, int],
) -> None:
    """Write accumulated programmes for one channel and clear the in-memory buffer."""
    if not programs:
        return

    if is_matched:
        deleted = EpgProgram.query.filter(
            EpgProgram.epg_channel_id == db_channel_id,
            EpgProgram.stop_time < now - timedelta(hours=1),
        ).delete(synchronize_session=False)
    else:
        deleted = EpgProgram.query.filter(
            EpgProgram.epg_channel_id == db_channel_id,
            db.or_(
                EpgProgram.stop_time < now - timedelta(hours=1),
                EpgProgram.start_time >= preview_end,
            ),
        ).delete(synchronize_session=False)
    stats["programs_deleted"] += deleted
    db.session.flush()

    existing = {p.start_time: p for p in EpgProgram.query.filter_by(epg_channel_id=db_channel_id).all()}
    unique_programs = {prog_data["start_time"]: prog_data for prog_data in programs}

    for prog_data in unique_programs.values():
        start_time = prog_data["start_time"]
        existing_prog = existing.get(start_time)
        if existing_prog:
            if _update_program(existing_prog, prog_data):
                stats["programs_updated"] += 1
            else:
                stats["programs_unchanged"] += 1
        else:
            db.session.add(_create_program(db_channel_id, prog_data))
            stats["programs_added"] += 1


def sync_programs_for_source(
    source: EpgSource,
    xml_content: bytes,
    preview_hours: int = DEFAULT_PREVIEW_HOURS,
    load_all_for_matched: bool = True,
    progress_callback: ProgressCallback = None,
) -> Dict[str, int]:
    """Sync program data from XMLTV content to the database."""
    stats = {
        "programs_added": 0,
        "programs_updated": 0,
        "programs_deleted": 0,
        "programs_unchanged": 0,
        "channels_processed": 0,
        "matched_channels": 0,
        "preview_channels": 0,
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    preview_end = now + timedelta(hours=preview_hours)

    channel_id_map = get_epg_channel_id_map(source.id)
    if not channel_id_map:
        logger.warning(f"No EPG channels found for source {source.id}, skipping program sync")
        return stats

    matched_db_ids = get_matched_epg_channel_ids(source.id)

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

    programs_by_channel: Dict[int, List[Dict]] = {}
    channels_touched: Set[int] = set()
    programmes_parsed = 0
    commit_every = 0

    def _report_progress(message: str = "") -> None:
        if progress_callback:
            progress_callback(
                programmes_parsed=programmes_parsed,
                programs_added=stats["programs_added"],
                programs_updated=stats["programs_updated"],
                channels_processed=len(channels_touched),
                message=message or f"Parsed {programmes_parsed} programmes",
            )

    for xmltv_channel_id, program_data in parse_xmltv_programs_streaming(xml_content):
        db_channel_id = channel_id_map.get(xmltv_channel_id)
        if not db_channel_id:
            continue

        is_matched_xml = xmltv_channel_id in matched_xmltv_ids

        if not is_matched_xml and not load_all_for_matched:
            start_time = program_data.get("start_time")
            if start_time and start_time >= preview_end:
                continue
            if start_time and start_time < now - timedelta(hours=1):
                continue

        if db_channel_id not in programs_by_channel:
            programs_by_channel[db_channel_id] = []

        programs_by_channel[db_channel_id].append(program_data)
        programmes_parsed += 1
        channels_touched.add(db_channel_id)

        if len(programs_by_channel[db_channel_id]) >= CHANNEL_PROGRAM_BUFFER_FLUSH:
            is_matched_db = db_channel_id in matched_db_ids
            _flush_channel_programs(
                db_channel_id,
                programs_by_channel.pop(db_channel_id),
                is_matched=is_matched_db,
                matched_db_ids=matched_db_ids,
                now=now,
                preview_end=preview_end,
                stats=stats,
            )
            commit_every += 1
            if commit_every % 20 == 0:
                db.session.commit()
                _report_progress()

        if programmes_parsed % 50000 == 0:
            _report_progress()

    stats["channels_processed"] = len(channels_touched)

    for db_channel_id, programs in programs_by_channel.items():
        is_matched_db = db_channel_id in matched_db_ids
        _flush_channel_programs(
            db_channel_id,
            programs,
            is_matched=is_matched_db,
            matched_db_ids=matched_db_ids,
            now=now,
            preview_end=preview_end,
            stats=stats,
        )

    db.session.commit()
    _report_progress("Program sync complete")

    logger.info(
        f"Program sync complete for source {source.id}: "
        f"added={stats['programs_added']}, updated={stats['programs_updated']}, "
        f"unchanged={stats['programs_unchanged']}, deleted={stats['programs_deleted']}, "
        f"channels={stats['channels_processed']}"
    )

    return stats
