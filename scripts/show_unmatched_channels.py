#!/usr/bin/env python3
"""
Show unmatched PPV channels.

Lists channels that failed to match to events,
grouped by failure reason to help identify improvement opportunities.
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel
from services.ppv_event_extractor import PPVEventExtractor
from services.reverse_event_matcher.date_extractor import DateExtractor


def analyze_unmatched_channels(account_id=None, reason_filter="all"):
    """Analyze unmatched PPV channels."""

    # Get PPV channels
    query = Channel.query.filter(Channel.is_ppv == True)  # noqa: E712
    if account_id:
        query = query.filter_by(account_id=account_id)

    ppv_channels = query.all()

    # Filter to unmatched only
    unmatched = []
    for channel in ppv_channels:
        # Use the event_links relationship from Channel model
        if not channel.event_links:
            unmatched.append(channel)

    if not unmatched:
        print("No unmatched channels found.")
        return

    # Categorize by reason
    date_extractor = DateExtractor()
    event_extractor = PPVEventExtractor()

    categories = {
        "no_competitors": [],  # No competitors extracted
        "no_date": [],  # No date extracted
        "no_match": [],  # Had competitors and date but no match
    }

    for channel in unmatched:
        name = channel.name

        # Try to extract competitors
        competitors = event_extractor.extract_competitors(name)

        # Try to extract date
        date = date_extractor.extract_date(name)

        if not competitors:
            categories["no_competitors"].append((channel, None, None))
        elif not date:
            categories["no_date"].append((channel, competitors, None))
        else:
            categories["no_match"].append((channel, competitors, date))

    # Filter by reason if specified
    if reason_filter != "all":
        categories = {reason_filter: categories.get(reason_filter, [])}

    # Display results
    print(f"\nFound {len(unmatched)} unmatched PPV channels\n")
    print("=" * 120)

    for category, items in categories.items():
        if not items:
            continue

        print(f"\n{category.upper().replace('_', ' ')} ({len(items)} channels)")
        print("-" * 120)

        for channel, competitors, date in items:
            print(f"Channel: [{channel.stream_id}] {channel.name}")

            if competitors:
                print(f"  Competitors: {', '.join(competitors)}")

            if date:
                print(f"  Date: {date}")

            # Show category name for context
            if channel.category:
                print(f"  Category: {channel.category.category_name}")

            print()

    # Summary
    print("\n" + "=" * 120)
    print("SUMMARY")
    print("-" * 120)
    total = sum(len(items) for items in categories.values())
    for category, items in categories.items():
        if items:
            pct = len(items) / total * 100 if total > 0 else 0
            print(f"{category.replace('_', ' ').title():20s}: {len(items):5d} ({pct:5.1f}%)")

    # Recommendations
    print("\nRECOMMENDATIONS")
    print("-" * 120)

    if categories.get("no_match"):
        print("⚠️  Channels with competitors and dates but no match:")
        print("   → These are the best candidates for improving the matching algorithm")
        print("   → Consider reviewing event database coverage for these sports/leagues")

    if categories.get("no_competitors"):
        print("⚠️  Channels with no competitor extraction:")
        print("   → Review text_processor.py extraction patterns")
        print("   → These may be non-event channels (highlights, documentaries, etc.)")

    if categories.get("no_date"):
        print("⚠️  Channels with competitors but no date:")
        print("   → Review date_extractor.py patterns")
        print("   → Some may be upcoming events without scheduled times")


def main():
    parser = argparse.ArgumentParser(description="Show unmatched PPV channels")
    parser.add_argument("--account-id", type=int, help="Filter by specific account ID")
    parser.add_argument(
        "--reason",
        choices=["all", "no-competitors", "no-date", "no-match"],
        default="all",
        help="Filter by failure reason (default: all)",
    )

    args = parser.parse_args()

    # Convert hyphen to underscore for internal use
    reason_filter = args.reason.replace("-", "_")

    with app.app_context():
        analyze_unmatched_channels(args.account_id, reason_filter)


if __name__ == "__main__":
    main()
