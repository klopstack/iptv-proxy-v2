"""EPG source sync helpers (Schedules Direct channel import)."""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from models import EpgChannel, EpgSource, db
from services.epg.utils import make_sd_xmltv_id

logger = logging.getLogger(__name__)

__all__ = ["sync_sd_channels_to_epg"]


def sync_sd_channels_to_epg(source: EpgSource, channels: List[Dict]) -> Dict:
    """
    Sync Schedules Direct channels to EpgChannel records.

    Args:
        source: The EpgSource for Schedules Direct
        channels: List of channel dicts from SchedulesDirectClient.get_lineup_channels()

    Returns:
        Dict with sync statistics
    """
    stats: Dict[str, Any] = {
        "channels_added": 0,
        "channels_updated": 0,
        "channels_removed": 0,
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seen_channel_ids = set()

    existing = {ec.channel_id: ec for ec in EpgChannel.query.filter_by(source_id=source.id).all()}

    for channel in channels:
        station_id = channel.get("stationID")
        if not station_id:
            continue

        channel_id = make_sd_xmltv_id(station_id)
        seen_channel_ids.add(channel_id)

        display_names = []
        callsign = channel.get("callsign")
        name = channel.get("name")
        if callsign:
            display_names.append(callsign)
        if name and name != callsign:
            display_names.append(name)

        primary_name = callsign or name or f"Station {station_id}"

        logo_url = None
        logo_info = channel.get("logo")
        if logo_info and isinstance(logo_info, dict):
            logo_url = logo_info.get("url")

        if channel_id in existing:
            ec = existing[channel_id]
            ec.display_name = primary_name
            ec.display_names_json = json.dumps(display_names) if display_names else None
            ec.icon_url = logo_url
            ec.last_seen = now
            ec.updated_at = now
            stats["channels_updated"] += 1
        else:
            ec = EpgChannel(
                source_id=source.id,
                channel_id=channel_id,
                display_name=primary_name,
                display_names_json=json.dumps(display_names) if display_names else None,
                icon_url=logo_url,
                program_count=0,
                last_seen=now,
            )
            db.session.add(ec)
            stats["channels_added"] += 1

    for channel_id in existing:
        if channel_id not in seen_channel_ids:
            stats["channels_removed"] += 1

    db.session.commit()

    try:
        from services.icon_prefetch import prefetch_epg_source_icons

        stats["icon_prefetch"] = prefetch_epg_source_icons(source.id)
    except Exception as e:
        logger.error("Icon prefetch after SD sync failed for source %s: %s", source.id, e)

    logger.info(
        f"SD sync for source {source.id} ({source.name}): "
        f"added={stats['channels_added']}, updated={stats['channels_updated']}, "
        f"not_seen={stats['channels_removed']}"
    )

    return stats
