"""
Common helper functions for EPG routes
"""
import json
import logging
from datetime import datetime, timezone

from models import EpgSource, SdLineup, SdStation, db
from services.schedules_direct import SchedulesDirectClient, SchedulesDirectError

logger = logging.getLogger(__name__)

__all__ = ["sync_sd_lineup_impl"]


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
