#!/usr/bin/env python3
"""
Spike probe: API-Tennis fixture counts for a date range.

Not wired to production. Requires PPV_API_TENNIS_KEY env var (or --key).

Usage:
  PPV_API_TENNIS_KEY=xxx python scripts/spike_tennis_calendar.py --date 2026-06-03
  python scripts/spike_tennis_calendar.py --date 2026-06-03 --search kalinskaya
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List

import requests

API_BASE = "https://api.api-tennis.com/tennis/"


def fetch_fixtures(api_key: str, date_start: str, date_stop: str) -> List[Dict[str, Any]]:
    resp = requests.get(
        API_BASE,
        params={
            "method": "get_fixtures",
            "APIkey": api_key,
            "date_start": date_start,
            "date_stop": date_stop,
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success"):
        print(f"API error: {json.dumps(data, indent=2)}", file=sys.stderr)
        return []
    result = data.get("result") or []
    return result if isinstance(result, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe API-Tennis fixtures for spike validation")
    parser.add_argument("--date", default="2026-06-03", help="UTC date YYYY-MM-DD")
    parser.add_argument("--search", default="", help="Filter fixtures by player name substring")
    parser.add_argument("--key", default=os.environ.get("PPV_API_TENNIS_KEY", ""), help="API-Tennis key")
    args = parser.parse_args()

    if not args.key:
        print("Set PPV_API_TENNIS_KEY or pass --key", file=sys.stderr)
        return 1

    fixtures = fetch_fixtures(args.key, args.date, args.date)
    if args.search:
        needle = args.search.lower()
        fixtures = [
            f
            for f in fixtures
            if needle in (f.get("event_first_player") or "").lower()
            or needle in (f.get("event_second_player") or "").lower()
        ]

    by_type: Dict[str, int] = {}
    for f in fixtures:
        t = f.get("event_type_type") or "unknown"
        by_type[t] = by_type.get(t, 0) + 1

    print(json.dumps({"date": args.date, "total": len(fixtures), "by_event_type": by_type}, indent=2))
    for f in fixtures[:20]:
        print(
            f"  {f.get('event_key')}: {f.get('event_first_player')} vs {f.get('event_second_player')} "
            f"({f.get('event_type_type')}) @ {f.get('event_time')} — {f.get('tournament_name')}"
        )
    if len(fixtures) > 20:
        print(f"  ... and {len(fixtures) - 20} more")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
