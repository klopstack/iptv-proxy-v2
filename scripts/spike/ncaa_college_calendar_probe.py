#!/usr/bin/env python3
"""Manual spike probe for TODO 130 — not used in production or CI.

Fetches SofaScore scheduled-events for college/amateur sport slugs and scores
sample Flo channel titles. Bypasses the live ±14-day window gate.

Usage:
    python scripts/spike/ncaa_college_calendar_probe.py
    python scripts/spike/ncaa_college_calendar_probe.py --date 2025-10-22 --slug ice-hockey
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_PATH = ROOT / "tests/ppv/fixtures/spike/flo_spike_sample_channels.json"
BASE_URL = "https://api.sofascore.com/api/v1/sport/{slug}/scheduled-events/{date}"


def http_get(url: str):
    try:
        from curl_cffi import requests as curl_requests

        return curl_requests.get(
            url,
            timeout=30,
            headers={"User-Agent": "iptv-proxy-v2/1.0"},
            impersonate="chrome",
        )
    except ImportError:
        import requests

        return requests.get(url, timeout=30, headers={"User-Agent": "iptv-proxy-v2/1.0"})


def norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def parse_competitors(title: str) -> tuple[str, str] | None:
    m = re.search(r"(\w[\w\s.'()-]*?)\s+vs\s+(\w[\w\s.'()-]*?)(?:\s+-|\s+\d{2}/\d{2}|\s+\|)", title, re.I)
    if not m:
        return None
    return m.group(1).strip(), m.group(2).strip()


def match_event(events: list, home_hint: str, away_hint: str):
    nh, na = norm(home_hint), norm(away_hint)
    for ev in events:
        ht = ev.get("homeTeam", {}) or {}
        at = ev.get("awayTeam", {}) or {}
        hname = ht.get("name") or ht.get("shortName") or ""
        aname = at.get("name") or at.get("shortName") or ""
        hn, an = norm(hname), norm(aname)
        if (nh in hn or hn in nh) and (na in an or an in na):
            return ev, hname, aname
        if (nh in an or an in nh) and (na in hn or hn in na):
            return ev, aname, hname
    return None, None, None


def probe(slug: str, date: str, channels: list) -> dict:
    url = BASE_URL.format(slug=slug, date=date)
    response = http_get(url)
    if response.status_code != 200:
        return {"slug": slug, "date": date, "error": response.status_code, "matches": []}

    events = response.json().get("events", [])
    matches = []
    for row in channels:
        title = row["title"]
        pair = parse_competitors(title)
        if not pair:
            continue
        home, away = pair
        ev, h, a = match_event(events, home, away)
        matches.append(
            {
                "id": row["id"],
                "title": title,
                "found": ev is not None,
                "home": h,
                "away": a,
                "event_id": (ev or {}).get("id"),
                "tournament": ((ev or {}).get("tournament") or {}).get("name"),
            }
        )
    return {"slug": slug, "date": date, "event_count": len(events), "matches": matches}


def main() -> int:
    parser = argparse.ArgumentParser(description="TODO 130 SofaScore college calendar spike probe")
    parser.add_argument("--date", action="append", default=["2025-10-22", "2025-10-23", "2025-11-01"])
    parser.add_argument(
        "--slug", action="append", default=["basketball", "ice-hockey", "american-football", "volleyball"]
    )
    args = parser.parse_args()

    sample = json.loads(SAMPLE_PATH.read_text())
    channels = sample["channels"]
    results = []
    for slug in args.slug:
        for date in args.date:
            subset = [c for c in channels if c.get("date") == date and c.get("sofascore_slug") == slug]
            if not subset:
                continue
            results.append(probe(slug, date, subset))

    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
