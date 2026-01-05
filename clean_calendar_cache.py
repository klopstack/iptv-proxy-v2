#!/usr/bin/env python3
"""
Clean calendar cache by removing events with empty time_utc fields.

These events were cached by older code that didn't filter out invalid times.
They cause repeated warnings when accessed since scheduled_at can't be parsed.
"""
import json
import logging
import os
import sys
from typing import Any, Dict

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

CACHE_FILE = "data/calendar_cache.json"


def clean_calendar_cache(dry_run: bool = True) -> Dict[str, Any]:
    """
    Remove events with empty time_utc fields from calendar cache.

    Args:
        dry_run: If True, only report what would be removed without making changes

    Returns:
        Dict with statistics about the operation
    """
    if not os.path.exists(CACHE_FILE):
        logger.error(f"Cache file not found: {CACHE_FILE}")
        return {"error": "cache_not_found"}

    # Load cache
    with open(CACHE_FILE, "r") as f:
        cache = json.load(f)

    original_date_count = len(cache)
    original_event_count = sum(len(entry.get("events", [])) for entry in cache.values())

    # Clean events
    removed_events = []
    cleaned_cache = {}

    for date_key, entry in cache.items():
        events = entry.get("events", [])
        valid_events = []

        for event in events:
            time_utc = event.get("time_utc", "").strip()

            if not time_utc:
                # Event has empty time - remove it
                removed_events.append(
                    {
                        "date": date_key,
                        "event_id": event.get("event_id"),
                        "event_name": event.get("event_name"),
                        "time_utc": repr(event.get("time_utc")),
                    }
                )
            else:
                # Event has valid time - keep it
                valid_events.append(event)

        # Only keep date entries that still have events
        if valid_events:
            cleaned_cache[date_key] = {
                "timestamp": entry.get("timestamp"),
                "events": valid_events,
            }

    cleaned_date_count = len(cleaned_cache)
    cleaned_event_count = sum(len(entry.get("events", [])) for entry in cleaned_cache.values())

    # Report results
    stats = {
        "original_date_entries": original_date_count,
        "original_event_count": original_event_count,
        "removed_event_count": len(removed_events),
        "cleaned_date_entries": cleaned_date_count,
        "cleaned_event_count": cleaned_event_count,
        "removed_events": removed_events,
    }

    logger.info(f"Original cache: {original_date_count} dates, {original_event_count} events")
    logger.info(f"Found {len(removed_events)} events with empty time_utc")

    if removed_events:
        logger.info("\nEvents to be removed:")
        for ev in removed_events:
            logger.info(f"  [{ev['date']}] {ev['event_id']}: {ev['event_name']} (time={ev['time_utc']})")

    logger.info(f"\nCleaned cache: {cleaned_date_count} dates, {cleaned_event_count} events")

    if not dry_run:
        # Save cleaned cache
        with open(CACHE_FILE, "w") as f:
            json.dump(cleaned_cache, f, indent=2)
        logger.info(f"\n✅ Cache cleaned and saved to {CACHE_FILE}")
    else:
        logger.info("\n🔍 DRY RUN - No changes made. Run with --apply to clean the cache.")

    return stats


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Clean calendar cache by removing events with empty times")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes (default is dry-run mode)",
    )
    args = parser.parse_args()

    stats = clean_calendar_cache(dry_run=not args.apply)

    if stats.get("error"):
        sys.exit(1)

    sys.exit(0)
