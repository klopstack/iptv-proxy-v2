#!/usr/bin/env python3
"""
Clean up old/stale events from the database.

Removes events that are older than a specified threshold to prevent
incorrect matches to historical events.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from services.event_retention import cleanup_old_events, get_event_retention_days


def main():
    parser = argparse.ArgumentParser(description="Clean up old events from the database")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help=f"Remove events older than this many days (default: {get_event_retention_days()} from env/default)",
    )
    parser.add_argument("--execute", action="store_true", help="Actually delete events (default is dry run)")

    args = parser.parse_args()
    max_age_days = args.max_age_days if args.max_age_days is not None else get_event_retention_days()

    with app.app_context():
        if not args.execute:
            from datetime import datetime, timedelta, timezone

            from models import Event

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            cutoff = now - timedelta(days=max_age_days)
            count = Event.query.filter(Event.scheduled_at < cutoff).count()
            print(f"DRY RUN - Would delete {count} event(s) older than {max_age_days} days")
            print("Run with --execute to apply")
            return

        deleted = cleanup_old_events(max_age_days=max_age_days)
        print(f"Deleted {deleted} event(s)")


if __name__ == "__main__":
    main()
