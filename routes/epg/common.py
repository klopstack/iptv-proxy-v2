"""
Common helper functions for EPG routes
"""
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List

from models import EpgChannel, EpgSource, SdLineup, SdStation, db
from services.epg.utils import make_sd_xmltv_id
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError

logger = logging.getLogger(__name__)

__all__ = ["sync_sd_channels_to_epg", "sync_sd_lineup_impl"]


def sync_sd_channels_to_epg(source: EpgSource, channels: List[Dict]) -> Dict:
    """
    Sync Schedules Direct channels to EpgChannel records.

    Args:
        source: The EpgSource for Schedules Direct
        channels: List of channel dicts from SchedulesDirectClient.get_lineup_channels()

    Returns:
        Dict with sync statistics
    """
    stats = {
        "channels_added": 0,
        "channels_updated": 0,
        "channels_removed": 0,
    }

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    seen_channel_ids = set()

    # Get existing channels for this source
    existing = {ec.channel_id: ec for ec in EpgChannel.query.filter_by(source_id=source.id).all()}

    for channel in channels:
        station_id = channel.get("stationID")
        if not station_id:
            continue

        # Create XMLTV-style channel ID for SD stations
        channel_id = make_sd_xmltv_id(station_id)
        seen_channel_ids.add(channel_id)

        # Build display names list - include callsign and full name
        display_names = []
        callsign = channel.get("callsign")
        name = channel.get("name")
        if callsign:
            display_names.append(callsign)
        if name and name != callsign:
            display_names.append(name)

        primary_name = callsign or name or f"Station {station_id}"

        # Get logo URL if available
        logo_url = None
        logo_info = channel.get("logo")
        if logo_info and isinstance(logo_info, dict):
            logo_url = logo_info.get("url")

        if channel_id in existing:
            # Update existing channel
            ec = existing[channel_id]
            ec.display_name = primary_name
            ec.display_names_json = json.dumps(display_names) if display_names else None
            ec.icon_url = logo_url
            ec.last_seen = now
            ec.updated_at = now
            stats["channels_updated"] += 1
        else:
            # Create new channel
            ec = EpgChannel(
                source_id=source.id,
                channel_id=channel_id,
                display_name=primary_name,
                display_names_json=json.dumps(display_names) if display_names else None,
                icon_url=logo_url,
                program_count=0,  # Will be updated when schedules are fetched
                last_seen=now,
            )
            db.session.add(ec)
            stats["channels_added"] += 1

    # Count channels not seen (but don't delete them)
    for channel_id in existing:
        if channel_id not in seen_channel_ids:
            stats["channels_removed"] += 1

    db.session.commit()

    logger.info(
        f"SD sync for source {source.id} ({source.name}): "
        f"added={stats['channels_added']}, updated={stats['channels_updated']}, "
        f"not_seen={stats['channels_removed']}"
    )

    return stats


def sync_sd_lineup_impl(source: EpgSource, lineup: SdLineup) -> dict:
    """Implementation of SD lineup sync"""
    client = SchedulesDirectClient(source.sd_username, source.sd_password)
    client.authenticate()

    # Check if lineup is already on the SD account
    status = client.get_status()
    account_lineups = status.get("lineups", [])
    account_lineup_ids = [lineup_item.get("lineup") for lineup_item in account_lineups]

    # Only try to add if not already on account
    if lineup.lineup_id not in account_lineup_ids:
        # Check if we're at the limit before trying to add
        max_lineups = status.get("account", {}).get("maxLineups", 4)
        if len(account_lineups) >= max_lineups:
            raise SchedulesDirectError(
                f"Cannot add lineup: SD account limit reached ({len(account_lineups)}/{max_lineups}). "
                "Please remove a lineup from your account first.",
                code=2100,  # Use DUPLICATE_LINEUP code as a generic limit error
            )

        try:
            client.add_lineup(lineup.lineup_id)
            logger.info(f"Added lineup {lineup.lineup_id} to SD account")
        except SchedulesDirectError as e:
            # Code 2100 = DUPLICATE_LINEUP means it's already added, which is fine
            if e.code != 2100:
                logger.warning(f"Could not add lineup to SD account: {e}")
                # Re-raise if it's a more serious error
                if e.code not in (2100, 2102):  # 2102 = UNKNOWN_LINEUP (might work anyway)
                    raise
    else:
        logger.info(f"Lineup {lineup.lineup_id} already on SD account, skipping add")

    # Get channels from SD
    logger.info(f"Fetching channels for lineup {lineup.lineup_id} from Schedules Direct")
    channels = client.get_lineup_channels(lineup.lineup_id)
    logger.info(f"Received {len(channels)} channels from Schedules Direct")

    channels_synced = 0
    channels_updated = 0

    for ch in channels:
        # Find or create station record
        station = SdStation.query.filter_by(lineup_id=lineup.id, station_id=ch["stationID"]).first()

        logo_url = ch.get("logo", {}).get("url") if ch.get("logo") else None
        broadcast_lang = json.dumps(ch.get("broadcastLanguage", []))

        if station:
            # Update existing
            station.channel_number = ch.get("channel")
            station.callsign = ch.get("callsign")
            station.name = ch.get("name")
            station.affiliate = ch.get("affiliate")
            station.broadcast_language = broadcast_lang
            station.logo_url = logo_url
            channels_updated += 1
        else:
            # Create new
            station = SdStation(
                lineup_id=lineup.id,
                station_id=ch["stationID"],
                channel_number=ch.get("channel"),
                callsign=ch.get("callsign"),
                name=ch.get("name"),
                affiliate=ch.get("affiliate"),
                broadcast_language=broadcast_lang,
                logo_url=logo_url,
            )
            db.session.add(station)
            channels_synced += 1

    # Update lineup stats
    lineup.channel_count = len(channels)
    lineup.last_sync = datetime.now(timezone.utc).replace(tzinfo=None)

    db.session.commit()

    return {
        "channels_synced": channels_synced,
        "channels_updated": channels_updated,
        "total_channels": len(channels),
    }
