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
    date_but_no_competitors = []  # Suspicious category

    # Statistics tracking
    stats = {
        "total_lines": 0,
        "with_competitors": 0,
        "with_date": 0,
        "with_both": 0,
        "date_but_no_competitors": 0,
        "placeholders": 0,
        "inactive": 0,
        "no_extraction": 0,
    }

    logger.info("Reading PPV.list...")
    try:
        with open("PPV.list", "r", encoding="utf-8") as f:
            for line in f:
                stats["total_lines"] += 1
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

                # Track placeholders and inactive channels
                if event_info and event_info.get("is_placeholder"):
                    stats["placeholders"] += 1
                    no_data.append(line)
                    continue

                if event_info and event_info.get("is_inactive"):
                    stats["inactive"] += 1
                    no_data.append(line)
                    continue

                # Check for far-future placeholder dates (2098-12-31, 2099-01-01)
                if event_info and event_info.get("inferred_how") == "date_too_far_future":
                    stats["placeholders"] += 1
                    no_data.append(line)
                    continue

                # Check if we got meaningful data
                has_competitors = event_info and event_info.get("competitors")
                has_date = event_info and (event_info.get("date") or event_info.get("time_only"))

                if has_competitors:
                    stats["with_competitors"] += 1
                if has_date:
                    stats["with_date"] += 1
                if has_competitors and has_date:
                    stats["with_both"] += 1

                # Suspicious case: date but no competitors
                # Most PPV channels include event info if they include a date
                if has_date and not has_competitors:
                    stats["date_but_no_competitors"] += 1
                    date_but_no_competitors.append(line)
                    # Still add to extractable since we have date info
                    extractable.append(line)
                elif has_competitors or has_date:
                    # Has competitors and/or date - extractable
                    extractable.append(line)
                else:
                    # No extraction at all
                    stats["no_extraction"] += 1
                    no_data.append(line)

            logger.info(f"Processed {stats['total_lines']} total lines")

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

        # Write date_but_no_competitors (suspicious cases for analysis)
        if date_but_no_competitors:
            logger.info(f"Writing DATE_BUT_NO_COMPETITORS.list ({len(date_but_no_competitors)} channels)...")
            with open("DATE_BUT_NO_COMPETITORS.list", "w", encoding="utf-8") as f:
                f.write("# Channels that have date/time info but no competitor extraction\n")
                f.write("# These are suspicious because most PPV channels with dates include event info\n")
                f.write("# Format: id|stream_id|channel_name|country|category|0\n")
                f.write("#\n")
                for line in date_but_no_competitors:
                    f.write(line + "\n")

        # Summary with detailed statistics
        logger.info("=" * 70)
        logger.info("EXTRACTION STATISTICS:")
        logger.info("=" * 70)
        logger.info(f"📊 Total channels processed: {stats['total_lines']}")
        logger.info("")
        logger.info(f"✅ EXTRACTABLE.list: {len(extractable)} channels")
        logger.info(f"   - With competitors: {stats['with_competitors']}")
        logger.info(f"   - With date/time: {stats['with_date']}")
        logger.info(f"   - With both: {stats['with_both']}")
        logger.info("")
        logger.info(f"⚠️  DATE_BUT_NO_COMPETITORS.list: {stats['date_but_no_competitors']} channels")
        logger.info("   (Included in EXTRACTABLE but flagged for analysis)")
        logger.info("")
        logger.info(f"❌ NO_DATA.list: {len(no_data)} channels")
        logger.info(f"   - Placeholders: {stats['placeholders']}")
        logger.info(f"   - Inactive: {stats['inactive']}")
        logger.info(f"   - No extraction: {stats['no_extraction']}")
        logger.info("")
        logger.info(f"📅 Reference date used: {sync_date}")
        logger.info("=" * 70)

    except Exception as e:
        logger.error(f"Error regenerating lists: {e}")
        raise


if __name__ == "__main__":
    regenerate_ppv_lists()
