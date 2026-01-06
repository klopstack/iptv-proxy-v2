#!/usr/bin/env python3
"""
Show unmatched events.

Lists events in the database that have no channel matches.
Helps identify gaps in channel coverage or events that need better matching.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Event, EventChannelLink


def show_unmatched_events(min_age_days=0, max_age_days=30):
    """Show events with no channel matches."""

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    min_date = now - timedelta(days=max_age_days)
    max_date = now + timedelta(days=max_age_days)

    # Get events in date range
    events = (
        Event.query.filter(Event.scheduled_at >= min_date, Event.scheduled_at <= max_date)
        .order_by(Event.scheduled_at)
        .all()
    )

    # Filter to unmatched
    unmatched = []
    for event in events:
        link_count = EventChannelLink.query.filter_by(event_id=event.id).count()
        if link_count == 0:
            unmatched.append(event)

    if not unmatched:
        print(f"No unmatched events found in date range ({min_date.date()} to {max_date.date()})")
        return

    print(f"\nFound {len(unmatched)} unmatched events (out of {len(events)} total)\n")
    print("=" * 120)

    # Group by sport
    by_sport = {}
    for event in unmatched:
        sport = event.sport or "Unknown"
        if sport not in by_sport:
            by_sport[sport] = []
        by_sport[sport].append(event)

    for sport, sport_events in sorted(by_sport.items()):
        print(f"\n{sport.upper()} ({len(sport_events)} events)")
        print("-" * 120)

        for event in sport_events:
            # Date indicator
            days_diff = (event.scheduled_at - now).days
            if days_diff < -7:
                date_indicator = "📅 Past"
            elif days_diff < 0:
                date_indicator = "📅 Recent"
            elif days_diff < 1:
                date_indicator = "🔴 Today"
            elif days_diff < 7:
                date_indicator = "🟡 Soon"
            else:
                date_indicator = "🟢 Future"

            print(f"{date_indicator} [{event.id}] {event.display_title}")
            print(f"   Date: {event.scheduled_at}")

            if event.home_team_name and event.away_team_name:
                print(f"   Teams: {event.home_team_name} vs {event.away_team_name}")

            if event.league_name:
                print(f"   League: {event.league_name}")

            if event.source:
                print(f"   Source: {event.source}")

            print()

    # Summary
    print("\n" + "=" * 120)
    print("SUMMARY BY SPORT")
    print("-" * 120)
    for sport, sport_events in sorted(by_sport.items(), key=lambda x: len(x[1]), reverse=True):
        pct = len(sport_events) / len(unmatched) * 100
        print(f"{sport:20s}: {len(sport_events):5d} ({pct:5.1f}%)")

    # Time distribution
    past = sum(1 for e in unmatched if e.scheduled_at < now)
    future = len(unmatched) - past

    print("\nTIME DISTRIBUTION")
    print("-" * 120)
    print(f"Past events:   {past:5d} ({past / len(unmatched) * 100:5.1f}%)")
    print(f"Future events: {future:5d} ({future / len(unmatched) * 100:5.1f}%)")

    # Recommendations
    print("\nRECOMMENDATIONS")
    print("-" * 120)

    if past > len(unmatched) * 0.5:
        print("⚠️  Many past events have no matches")
        print("   → These may have been missed during their active period")
        print("   → Consider cleaning up old events if they're no longer relevant")

    if future > len(unmatched) * 0.5:
        print("ℹ️  Many upcoming events have no matches yet")
        print("   → Channels may not be available until closer to event time")
        print("   → Monitor as event date approaches")

    print("\nTo investigate why these events didn't match:")
    print("   1. Check if channels exist with similar names")
    print("   2. Review text_processor competitor extraction")
    print("   3. Verify event titles match common channel naming patterns")


def main():
    parser = argparse.ArgumentParser(description="Show unmatched events")
    parser.add_argument(
        "--min-age-days", type=int, default=0, help="Minimum age in days (negative for past, default: 0)"
    )
    parser.add_argument("--max-age-days", type=int, default=30, help="Maximum age in days (future events, default: 30)")

    args = parser.parse_args()

    with app.app_context():
        show_unmatched_events(args.min_age_days, args.max_age_days)


if __name__ == "__main__":
    main()
