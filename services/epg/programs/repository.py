"""EPG program database queries and maintenance."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import EpgChannel, EpgProgram, db
from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)


def get_current_program(epg_channel_id: int) -> Optional[EpgProgram]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return EpgProgram.query.filter(
        EpgProgram.epg_channel_id == epg_channel_id,
        EpgProgram.start_time <= now,
        EpgProgram.stop_time > now,
    ).first()


def get_current_programs_batch(epg_channel_ids: List[int]) -> Dict[int, EpgProgram]:
    if not epg_channel_ids:
        return {}
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    programs = EpgProgram.query.filter(
        EpgProgram.epg_channel_id.in_(epg_channel_ids),
        EpgProgram.start_time <= now,
        EpgProgram.stop_time > now,
    ).all()
    return {p.epg_channel_id: p for p in programs}


def get_upcoming_programs(epg_channel_id: int, hours: int = 24, limit: int = 20) -> List[EpgProgram]:
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
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    query = db.session.query(EpgProgram, EpgChannel).join(EpgChannel, EpgProgram.epg_channel_id == EpgChannel.id)
    for word in title_query.strip().split():
        query = query.filter(EpgProgram.title.ilike(f"%{word}%"))
    if source_id:
        query = query.filter(EpgChannel.source_id == source_id)
    if include_current_only:
        query = query.filter(EpgProgram.start_time <= now, EpgProgram.stop_time > now)
    else:
        query = query.filter(EpgProgram.stop_time > now)
    return query.order_by(EpgProgram.start_time).limit(limit).all()


def get_schedule_around_time(
    epg_channel_id: int,
    reference_time: Optional[datetime] = None,
    offset_hours: int = 0,
    hours_before: int = 2,
    hours_after: int = 4,
) -> Dict[str, Any]:
    if reference_time is None:
        reference_time = datetime.now(timezone.utc).replace(tzinfo=None)
    adjusted_time = reference_time + timedelta(hours=offset_hours)
    start_window = adjusted_time - timedelta(hours=hours_before)
    end_window = adjusted_time + timedelta(hours=hours_after)
    programs = (
        EpgProgram.query.filter(
            EpgProgram.epg_channel_id == epg_channel_id,
            EpgProgram.stop_time > start_window,
            EpgProgram.start_time < end_window,
        )
        .order_by(EpgProgram.start_time)
        .all()
    )
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
        "reference_time": serialize_utc_iso(reference_time),
        "adjusted_time": serialize_utc_iso(adjusted_time),
        "offset_hours": offset_hours,
        "current_program": current_program.to_dict() if current_program else None,
        "programs_before": [p.to_dict() for p in programs_before[-5:]],
        "programs_after": [p.to_dict() for p in programs_after[:5]],
    }


def cleanup_expired_programs(days_old: int = 1) -> int:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days_old)
    deleted = EpgProgram.query.filter(EpgProgram.stop_time < cutoff).delete(synchronize_session=False)
    db.session.commit()
    logger.info(f"Cleaned up {deleted} expired programs older than {days_old} days")
    return deleted


def get_programs_for_channels(
    epg_channel_ids: List[int],
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    batch_size: int = 500,
) -> Dict[int, List[EpgProgram]]:
    if not epg_channel_ids:
        return {}
    if start_time is None:
        start_time = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
    if end_time is None:
        end_time = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=24)
    result: Dict[int, List[EpgProgram]] = {cid: [] for cid in epg_channel_ids}
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


def has_programs_in_database(epg_channel_id: int) -> bool:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return (
        EpgProgram.query.filter(
            EpgProgram.epg_channel_id == epg_channel_id,
            EpgProgram.stop_time > now,
        ).first()
        is not None
    )


def get_database_coverage_stats(source_id: int) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
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
