#!/usr/bin/env python3
"""
Analyze PPV matching statistics.

Shows overall statistics about channel matching success rates,
confidence distributions, and failure reasons.
"""

import argparse
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Account, Channel, Event, EventChannelLink, db


def analyze_matching_stats(account_id=None, min_confidence=0.35):
    """Analyze PPV matching statistics."""

    print("=" * 80)
    print("PPV MATCHING STATISTICS")
    print("=" * 80)
    print()

    # Build base query
    query = Channel.query
    if account_id:
        query = query.filter_by(account_id=account_id)
        account = db.session.get(Account, account_id)
        print(f"Account: {account.name if account else 'Unknown'} (ID: {account_id})")
    else:
        print("Account: All accounts")

    # Get channels marked as PPV
    ppv_channels = query.filter(Channel.is_ppv == True).all()  # noqa: E712
    total_ppv = len(ppv_channels)

    print(f"Total PPV channels: {total_ppv}")
    print()

    if total_ppv == 0:
        print("No PPV channels found.")
        return

    # Analyze matches
    matched_count = 0
    confidence_buckets = defaultdict(int)
    unmatched_with_competitors = 0
    unmatched_no_competitors = 0

    for channel in ppv_channels:
        # Check if channel has matches via event_links relationship
        links = channel.event_links if hasattr(channel, "event_links") else []

        if links:
            matched_count += 1
            # Get highest confidence
            max_confidence = max(link.match_confidence for link in links)

            if max_confidence >= 0.7:
                confidence_buckets["high"] += 1
            elif max_confidence >= 0.6:
                confidence_buckets["medium"] += 1
            elif max_confidence >= min_confidence:
                confidence_buckets["low"] += 1
            else:
                confidence_buckets["very_low"] += 1
        else:
            # Unmatched - check if we extracted competitors
            # This is a heuristic: check if name contains "vs" or other indicators
            name = channel.name.lower()
            if "vs" in name or " v " in name or " @ " in name:
                unmatched_with_competitors += 1
            else:
                unmatched_no_competitors += 1

    unmatched_count = total_ppv - matched_count

    print("MATCHING RESULTS")
    print("-" * 80)
    print(f"Matched channels:   {matched_count:5d} ({matched_count / total_ppv * 100:5.1f}%)")
    print(f"Unmatched channels: {unmatched_count:5d} ({unmatched_count / total_ppv * 100:5.1f}%)")
    print()

    print("CONFIDENCE DISTRIBUTION (Matched Channels)")
    print("-" * 80)
    print(
        f"High confidence   (≥0.70): {confidence_buckets['high']:5d} ({confidence_buckets['high'] / total_ppv * 100:5.1f}%)"
    )
    print(
        f"Medium confidence (≥0.60): {confidence_buckets['medium']:5d} ({confidence_buckets['medium'] / total_ppv * 100:5.1f}%)"
    )
    print(
        f"Low confidence    (≥{min_confidence:.2f}): {confidence_buckets['low']:5d} ({confidence_buckets['low'] / total_ppv * 100:5.1f}%)"
    )
    print(
        f"Very low          (<{min_confidence:.2f}): {confidence_buckets['very_low']:5d} ({confidence_buckets['very_low'] / total_ppv * 100:5.1f}%)"
    )
    print()

    print("UNMATCHED BREAKDOWN")
    print("-" * 80)
    print(
        f"With competitors (vs/v/@): {unmatched_with_competitors:5d} ({unmatched_with_competitors / total_ppv * 100:5.1f}%)"
    )
    print(
        f"No competitors detected:   {unmatched_no_competitors:5d} ({unmatched_no_competitors / total_ppv * 100:5.1f}%)"
    )
    print()

    # Event statistics
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    recent_events = Event.query.filter(Event.scheduled_at >= now).count()

    # Count events with no links
    all_events = Event.query.all()
    unlinked_events = 0
    for event in all_events:
        link_count = EventChannelLink.query.filter_by(event_id=event.id).count()
        if link_count == 0:
            unlinked_events += 1

    total_events = len(all_events)
    linked_events = total_events - unlinked_events

    print("EVENT STATISTICS")
    print("-" * 80)
    print(f"Total events in database:     {total_events:5d}")
    print(
        f"Events with channel links:    {linked_events:5d} ({linked_events / total_events * 100 if total_events else 0:5.1f}%)"
    )
    print(
        f"Events with no channel links: {unlinked_events:5d} ({unlinked_events / total_events * 100 if total_events else 0:5.1f}%)"
    )
    print(f"Upcoming events (future):     {recent_events:5d}")
    print()

    # Recommendations
    print("RECOMMENDATIONS")
    print("-" * 80)
    if unmatched_with_competitors > matched_count * 0.2:
        print("⚠️  High number of unmatched channels with competitor info")
        print("   → Run show_unmatched_channels.py --reason no-match to investigate")

    if confidence_buckets["low"] + confidence_buckets["very_low"] > matched_count * 0.3:
        print("⚠️  Many matches have low confidence scores")
        print("   → Run analyze_match_patterns.py to find improvement opportunities")

    if unlinked_events > total_events * 0.5:
        print("⚠️  Many events have no channel matches")
        print("   → Run show_unmatched_events.py to review unused events")

    if not (
        unmatched_with_competitors > matched_count * 0.2
        or confidence_buckets["low"] + confidence_buckets["very_low"] > matched_count * 0.3
        or unlinked_events > total_events * 0.5
    ):
        print("✅ Matching performance looks healthy!")

    print()


def main():
    parser = argparse.ArgumentParser(description="Analyze PPV matching statistics")
    parser.add_argument("--account-id", type=int, help="Filter by specific account ID")
    parser.add_argument(
        "--min-confidence", type=float, default=0.35, help="Minimum confidence threshold (default: 0.35)"
    )

    args = parser.parse_args()

    with app.app_context():
        analyze_matching_stats(args.account_id, args.min_confidence)


if __name__ == "__main__":
    main()
