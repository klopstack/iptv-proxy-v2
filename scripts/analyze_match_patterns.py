#!/usr/bin/env python3
"""
Analyze match patterns to identify improvement opportunities.

Examines successful and failed matches to find patterns that could
improve matching accuracy and reduce false positives.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel, Event, EventChannelLink, db
from services.reverse_event_matcher.text_processor import TextProcessor


def analyze_match_patterns(account_id=None):
    """Analyze patterns in matches to identify improvements."""

    text_processor = TextProcessor()

    # Get matched channels
    query = (
        db.session.query(Channel, Event, EventChannelLink)
        .join(EventChannelLink, EventChannelLink.channel_id == Channel.id)
        .join(Event, Event.id == EventChannelLink.event_id)
        .filter(Channel.is_ppv == True)  # noqa: E712
    )

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    matches = query.all()

    if not matches:
        print("No matches found to analyze.")
        return

    print(f"\nAnalyzing {len(matches)} matched channels...\n")
    print("=" * 120)

    # Analyze by confidence levels
    high_conf = []
    medium_conf = []
    low_conf = []

    for channel, event, link in matches:
        if link.match_confidence >= 0.7:
            high_conf.append((channel, event, link))
        elif link.match_confidence >= 0.6:
            medium_conf.append((channel, event, link))
        else:
            low_conf.append((channel, event, link))

    # Analyze low confidence matches for patterns
    print("\nLOW CONFIDENCE MATCHES (< 0.6)")
    print("-" * 120)

    if low_conf:
        print(f"Found {len(low_conf)} low confidence matches\n")

        # Common issues in low confidence
        issues = defaultdict(list)

        for channel, event, link in low_conf[:20]:  # Show first 20
            name_clean = text_processor.normalize_text(channel.name)
            competitors = text_processor.extract_competitors(channel.name)

            # Check for common issues
            if event.sport and event.sport.lower() not in name_clean.lower():
                issues["sport_missing"].append((channel, event, link))

            if event.league_name and event.league_name.lower() not in name_clean.lower():
                issues["league_missing"].append((channel, event, link))

            if len(competitors) < 2:
                issues["weak_competitor_extraction"].append((channel, event, link))

            # Show example
            print(f"[{link.match_confidence:.3f}] {channel.name[:80]}")
            print(f"       → {event.display_title[:80]}")
            if link.match_method:
                print(f"       Method: {link.match_method}")
            print()
    else:
        print("No low confidence matches found.\n")

    # Analyze by sport
    print("\nMATCHES BY SPORT")
    print("-" * 120)

    sport_stats = defaultdict(lambda: {"count": 0, "high": 0, "medium": 0, "low": 0, "avg_conf": 0})

    for channel, event, link in matches:
        sport = event.sport or "Unknown"
        sport_stats[sport]["count"] += 1
        sport_stats[sport]["avg_conf"] += link.match_confidence

        if link.match_confidence >= 0.7:
            sport_stats[sport]["high"] += 1
        elif link.match_confidence >= 0.6:
            sport_stats[sport]["medium"] += 1
        else:
            sport_stats[sport]["low"] += 1

    # Calculate averages
    for sport, stats in sport_stats.items():
        stats["avg_conf"] /= stats["count"]

    # Sort by count
    sorted_sports = sorted(sport_stats.items(), key=lambda x: x[1]["count"], reverse=True)

    print(f"{'Sport':<20} {'Count':>8} {'Avg Conf':>10} {'High':>8} {'Med':>8} {'Low':>8}")
    print("-" * 120)
    for sport, stats in sorted_sports:
        print(
            f"{sport:<20} {stats['count']:8d} {stats['avg_conf']:10.3f} "
            f"{stats['high']:8d} {stats['medium']:8d} {stats['low']:8d}"
        )

    # Recommendations
    print("\n" + "=" * 120)
    print("RECOMMENDATIONS")
    print("-" * 120)

    if low_conf:
        print(f"\n1. LOW CONFIDENCE IMPROVEMENTS ({len(low_conf)} matches < 0.6)")
        print("   " + "-" * 116)

        if issues["weak_competitor_extraction"]:
            print(f"   • {len(issues['weak_competitor_extraction'])} matches have weak competitor extraction")
            print("     → Review text_processor.py competitor extraction patterns")

        if issues["sport_missing"]:
            print(f"   • {len(issues['sport_missing'])} matches missing sport context in channel name")
            print("     → Consider sport-aware boosting in match_strategy.py")

        if issues["league_missing"]:
            print(f"   • {len(issues['league_missing'])} matches missing league context")
            print("     → Consider league-aware matching")

    # Sports with low average confidence
    low_avg_sports = [(s, st) for s, st in sorted_sports if st["avg_conf"] < 0.6]
    if low_avg_sports:
        print("\n2. SPORTS WITH LOW AVERAGE CONFIDENCE")
        print("   " + "-" * 116)
        for sport, stats in low_avg_sports:
            print(f"   • {sport}: avg {stats['avg_conf']:.3f} ({stats['count']} matches)")
        print("     → These sports may need specialized matching rules")

    # High performers
    high_avg_sports = [(s, st) for s, st in sorted_sports if st["avg_conf"] >= 0.7 and st["count"] >= 10]
    if high_avg_sports:
        print("\n3. HIGH PERFORMING SPORTS (Good Examples)")
        print("   " + "-" * 116)
        for sport, stats in high_avg_sports[:5]:
            print(f"   ✅ {sport}: avg {stats['avg_conf']:.3f} ({stats['count']} matches)")
        print("     → Study these patterns for other sports")


def main():
    parser = argparse.ArgumentParser(description="Analyze match patterns for improvements")
    parser.add_argument("--account-id", type=int, help="Filter by specific account ID")

    args = parser.parse_args()

    with app.app_context():
        analyze_match_patterns(args.account_id)


if __name__ == "__main__":
    main()
