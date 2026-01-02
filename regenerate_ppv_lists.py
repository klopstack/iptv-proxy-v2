#!/usr/bin/env python3
"""
Regenerate EXTRACTABLE.list and NO_DATA.list using the database sync date as reference.

This script ensures that all date calculations (past/future checks) are made
relative to the actual sync date, not the current date.
"""

import logging

from services.ppv_event_extractor import PPVEventExtractor
from services.sync_date_service import SyncDateService

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def regenerate_ppv_lists():
    """Regenerate EXTRACTABLE.list and NO_DATA.list using sync date."""

    # Get the sync reference date from database
    sync_date = SyncDateService.get_reference_date("data/iptv_proxy.db")
    logger.info(f"Using sync reference date: {sync_date}")

    # Initialize extractor with sync date
    extractor = PPVEventExtractor(current_date=sync_date)

    extractable = []
    no_data = []

    logger.info("Reading PPV.list...")
    try:
        with open("PPV.list", "r", encoding="utf-8") as f:
            total_lines = 0
            for line in f:
                total_lines += 1
                line = line.strip()
                if not line:
                    continue

                parts = line.split("|")
                if len(parts) < 3:
                    continue

                # Format: id|stream_id|channel_name(possibly with pipes)|country|category|0
                # Extract everything between stream_id and the country code
                # Country is typically 2 letters and appears near the end
                # Find the channel name by taking from part[2] to part[-3] (before country|category|0)
                if len(parts) >= 6:
                    channel_name = "|".join(parts[2:-3])
                else:
                    channel_name = parts[2]

                # Try to extract event info
                event_info = extractor.extract_all(channel_name)

                # Check if we got meaningful data
                # Include any channel where we extracted competitors OR date (or both)
                # Past events are included too - they can be used for validation and may still be watched
                if event_info and (event_info.get("competitors") or event_info.get("date")):
                    # Has competitors and/or date - extractable
                    extractable.append(line)
                else:
                    # No extraction at all
                    no_data.append(line)

            logger.info(f"Processed {total_lines} total lines")

        # Write extractable
        logger.info(f"Writing EXTRACTABLE.list ({len(extractable)} channels)...")
        with open("EXTRACTABLE.list", "w", encoding="utf-8") as f:
            for line in extractable:
                f.write(line + "\n")

        # Write no_data
        logger.info(f"Writing NO_DATA.list ({len(no_data)} channels)...")
        with open("NO_DATA.list", "w", encoding="utf-8") as f:
            for line in no_data:
                f.write(line + "\n")

        # Summary
        logger.info("=" * 70)
        logger.info(f"✅ EXTRACTABLE.list: {len(extractable)} channels")
        logger.info(f"❌ NO_DATA.list: {len(no_data)} channels")
        logger.info(f"📊 Total: {len(extractable) + len(no_data)} channels")
        logger.info(f"📅 Reference date used: {sync_date}")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Error regenerating lists: {e}")
        raise


if __name__ == "__main__":
    regenerate_ppv_lists()
