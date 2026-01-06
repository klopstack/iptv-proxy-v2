#!/usr/bin/env python3
"""
Clean up old/stale events from the database.

Removes events that are older than a specified threshold to prevent
incorrect matches to historical events.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Event, EventChannelLink, db


def cleanup_old_events(max_age_days=30, dry_run=True):
    """Remove events older than max_age_days."""

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cutoff_date = now - timedelta(days=max_age_days)

    print(f"Cleaning up events older than {cutoff_date.date()}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will delete)'}")
    print("=" * 80)

    # Find old events
    old_events = Event.query.filter(Event.scheduled_at < cutoff_date).all()

    if not old_events:
        print("No old events found.")
        return

    print(f"\nFound {len(old_events)} old events:\n")

    # Group by year for summary
    by_year = {}
    for event in old_events:
        year = event.scheduled_at.year
        if year not in by_year:
            by_year[year] = []
        by_year[year].append(event)

    for year in sorted(by_year.keys()):
        events = by_year[year]
        print(f"Year {year}: {len(events)} events")
        for event in events[:5]:
            # Count links to this event
            link_count = EventChannelLink.query.filter_by(event_id=event.id).count()
            print(f"  [{event.id}] {event.display_title} @ {event.scheduled_at} ({link_count} links)")
        if len(events) > 5:
            print(f"  ... and {len(events) - 5} more")

    print()

    if dry_run:
        print("DRY RUN - No changes made.")
        print(f"Run with --execute to delete {len(old_events)} events")
    else:
        # Delete links first (due to foreign key constraints)
        link_count = 0
        for event in old_events:
            links = EventChannelLink.query.filter_by(event_id=event.id).all()
            link_count += len(links)
            for link in links:
                db.session.delete(link)

        # Delete events
        for event in old_events:
            db.session.delete(event)

        db.session.commit()
        print(f"✅ Deleted {len(old_events)} events and {link_count} channel links")


def main():
    parser = argparse.ArgumentParser(description="Clean up old events from the database")
    parser.add_argument(
        "--max-age-days", type=int, default=30, help="Remove events older than this many days (default: 30)"
    )
    parser.add_argument("--execute", action="store_true", help="Actually delete events (default is dry run)")

    args = parser.parse_args()

    with app.app_context():
        cleanup_old_events(args.max_age_days, dry_run=not args.execute)


if __name__ == "__main__":
    main()
