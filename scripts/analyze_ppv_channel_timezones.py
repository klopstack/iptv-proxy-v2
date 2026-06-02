#!/usr/bin/env python3
"""
Analyze PPV channel title timezones against matched Event metadata.

Backtests candidate IANA zones per linked channel to measure match-rate impact
vs the legacy America/New_York default.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel, Event, EventChannelLink, db
from services.datetime_utils import to_naive_utc
from services.ppv.channel_matching import load_country_tags_for_channel
from services.ppv.constants import COUNTRY_PREFIX_TZ
from services.ppv.extraction import PPVEventExtractor
from services.ppv.timezone_resolution import local_channel_datetime_to_utc, resolve_channel_timezone

CANDIDATE_ZONES = sorted(
    set(COUNTRY_PREFIX_TZ.values())
    | {
        "America/New_York",
        "America/Chicago",
        "America/Denver",
        "America/Los_Angeles",
        "America/Phoenix",
        "America/Toronto",
        "America/Vancouver",
        "UTC",
    }
)


def _delta_hours(channel_utc: datetime, event_utc: datetime) -> float:
    return abs((channel_utc - event_utc).total_seconds()) / 3600


def analyze(account_id: int | None = None, csv_path: str | None = None) -> dict:
    extractor = PPVEventExtractor()
    rows = []

    query = (
        db.session.query(Channel, Event, EventChannelLink)
        .join(EventChannelLink, EventChannelLink.channel_id == Channel.id)
        .join(Event, Event.id == EventChannelLink.event_id)
        .filter(Channel.is_ppv.is_(True))
    )
    if account_id:
        query = query.filter(Channel.account_id == account_id)

    matches = query.all()
    summary = {
        "total": len(matches),
        "with_title_date": 0,
        "eastern_would_match_2h": 0,
        "best_zone_would_match_2h": 0,
        "eastern_fail_best_pass": 0,
        "by_prefix": defaultdict(lambda: {"count": 0, "best_zones": defaultdict(int)}),
    }

    for channel, event, link in matches:
        extraction = extractor.extract_all(channel.name)
        naive = extraction.get("date")
        if not isinstance(naive, datetime):
            continue
        summary["with_title_date"] += 1

        country_tags = load_country_tags_for_channel(channel)
        category = getattr(channel, "category", None)
        category_name = getattr(category, "category_name", None) if category else None

        resolution = resolve_channel_timezone(
            channel.name,
            category_name=category_name,
            country_tags=country_tags,
            sport=extraction.get("sport"),
            competitors=extraction.get("competitors"),
            matchup=extraction.get("matchup"),
        )
        event_utc = event.scheduled_at
        if event_utc.tzinfo is not None:
            event_utc = to_naive_utc(event_utc)
        else:
            event_utc = event_utc.replace(tzinfo=None)

        best_zone = None
        best_delta = 9999.0
        eastern_delta = None
        resolver_delta = None

        for zone in CANDIDATE_ZONES:
            ch_utc = local_channel_datetime_to_utc(
                naive,
                type(resolution)(timezone=zone, confidence=1.0, source="test"),
            )
            delta = _delta_hours(ch_utc, event_utc)
            if delta < best_delta:
                best_delta = delta
                best_zone = zone
            if zone == "America/New_York":
                eastern_delta = delta

        ch_resolver = local_channel_datetime_to_utc(naive, resolution)
        resolver_delta = _delta_hours(ch_resolver, event_utc)

        if eastern_delta is not None and eastern_delta <= 2:
            summary["eastern_would_match_2h"] += 1
        if best_delta <= 2:
            summary["best_zone_would_match_2h"] += 1
        if eastern_delta is not None and eastern_delta > 2 and best_delta <= 2:
            summary["eastern_fail_best_pass"] += 1

        prefix = extraction.get("country_prefix") or "none"
        summary["by_prefix"][prefix]["count"] += 1
        if best_zone:
            summary["by_prefix"][prefix]["best_zones"][best_zone] += 1

        rows.append(
            {
                "channel": channel.name,
                "event": event.display_title,
                "prefix": prefix,
                "resolver_zone": resolution.timezone,
                "resolver_source": resolution.source,
                "resolver_delta_h": round(resolver_delta, 2),
                "best_zone": best_zone,
                "best_delta_h": round(best_delta, 2),
                "eastern_delta_h": round(eastern_delta, 1) if eastern_delta is not None else "",
            }
        )

    if csv_path:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)

    return summary


def main():
    parser = argparse.ArgumentParser(description="Analyze PPV channel timezone signals")
    parser.add_argument("--account-id", type=int, default=None)
    parser.add_argument("--csv", type=str, default=None, help="Write per-channel CSV")
    args = parser.parse_args()

    with app.app_context():
        summary = analyze(account_id=args.account_id, csv_path=args.csv)

    print(f"Matched channels with title date: {summary['with_title_date']} / {summary['total']}")
    print(f"Within 2h using Eastern default: {summary['eastern_would_match_2h']}")
    print(f"Within 2h using best candidate zone: {summary['best_zone_would_match_2h']}")
    print(f"Eastern fail but best zone pass: {summary['eastern_fail_best_pass']}")
    print("\nBy country prefix:")
    for prefix, data in sorted(summary["by_prefix"].items()):
        top = sorted(data["best_zones"].items(), key=lambda x: -x[1])[:3]
        top_str = ", ".join(f"{z}({n})" for z, n in top)
        print(f"  {prefix}: n={data['count']} top={top_str}")


if __name__ == "__main__":
    main()
