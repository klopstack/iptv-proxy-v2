#!/usr/bin/env python3
"""
Show matched PPV channels with details.

Lists all channels that successfully matched to events,
including confidence scores and matched event details.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel, Event, EventChannelLink, db


def show_matched_channels(account_id=None, min_confidence=0.35, output_format="table"):
    """Show all matched PPV channels."""

    # Build query for matched channels
    query = (
        db.session.query(Channel, Event, EventChannelLink)
        .join(EventChannelLink, EventChannelLink.channel_id == Channel.id)
        .join(Event, Event.id == EventChannelLink.event_id)
        .filter(Channel.is_ppv == True, EventChannelLink.match_confidence >= min_confidence)  # noqa: E712
    )

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    results = query.order_by(EventChannelLink.match_confidence.desc(), Channel.name).all()

    if not results:
        print("No matched channels found.")
        return

    # Format output
    if output_format == "json":
        data = []
        for channel, event, link in results:
            data.append(
                {
                    "account_id": channel.account_id,
                    "stream_id": channel.stream_id,
                    "channel_name": channel.name,
                    "event_id": event.id,
                    "event_title": event.display_title,
                    "event_date": event.scheduled_at.isoformat() if event.scheduled_at else None,
                    "sport": event.sport,
                    "league": event.league_name,
                    "home_team": event.home_team_name,
                    "away_team": event.away_team_name,
                    "confidence": link.match_confidence,
                    "match_method": link.match_method,
                }
            )
        print(json.dumps(data, indent=2))

    elif output_format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow(
            [
                "Account ID",
                "Stream ID",
                "Channel Name",
                "Event ID",
                "Event Title",
                "Event Date",
                "Sport",
                "League",
                "Home Team",
                "Away Team",
                "Confidence",
                "Match Method",
            ]
        )
        for channel, event, link in results:
            writer.writerow(
                [
                    channel.account_id,
                    channel.stream_id,
                    channel.name,
                    event.id,
                    event.display_title,
                    event.scheduled_at.isoformat() if event.scheduled_at else "",
                    event.sport or "",
                    event.league_name or "",
                    event.home_team_name or "",
                    event.away_team_name or "",
                    f"{link.match_confidence:.3f}",
                    link.match_method or "",
                ]
            )

    else:  # table
        print(f"\nFound {len(results)} matched channels (confidence ≥ {min_confidence})\n")
        print("=" * 120)

        for channel, event, link in results:
            conf_indicator = "🟢" if link.match_confidence >= 0.7 else "🟡" if link.match_confidence >= 0.6 else "🔴"

            print(f"{conf_indicator} Confidence: {link.match_confidence:.3f}")
            print(f"   Channel:  [{channel.stream_id}] {channel.name}")
            print(f"   Event:    {event.display_title}")

            if event.home_team_name and event.away_team_name:
                print(f"   Teams:    {event.home_team_name} vs {event.away_team_name}")

            if event.scheduled_at:
                print(f"   Date:     {event.scheduled_at}")

            if event.sport:
                print(f"   Sport:    {event.sport}", end="")
                if event.league_name:
                    print(f" ({event.league_name})", end="")
                print()

            if link.match_method:
                print(f"   Method:   {link.match_method}")

            print("-" * 120)

        # Summary by confidence
        high = sum(1 for _, _, link in results if link.match_confidence >= 0.7)
        medium = sum(1 for _, _, link in results if 0.6 <= link.match_confidence < 0.7)
        low = sum(1 for _, _, link in results if min_confidence <= link.match_confidence < 0.6)

        print(f"\nSummary: {high} high, {medium} medium, {low} low confidence matches")


def main():
    parser = argparse.ArgumentParser(description="Show matched PPV channels")
    parser.add_argument("--account-id", type=int, help="Filter by specific account ID")
    parser.add_argument(
        "--min-confidence", type=float, default=0.35, help="Minimum confidence threshold (default: 0.35)"
    )
    parser.add_argument(
        "--output", choices=["table", "csv", "json"], default="table", help="Output format (default: table)"
    )

    args = parser.parse_args()

    with app.app_context():
        show_matched_channels(args.account_id, args.min_confidence, args.output)


if __name__ == "__main__":
    main()
