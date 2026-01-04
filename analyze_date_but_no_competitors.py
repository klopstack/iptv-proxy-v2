#!/usr/bin/env python3
"""
Analyze DATE_BUT_NO_COMPETITORS.list to understand why competitor extraction is failing.

This script helps identify patterns that should be extractable but aren't being caught.
"""

import logging
import re
from collections import Counter

from services.sync_date_service import SyncDateService

logging.basicConfig(level=logging.WARNING, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def analyze_date_but_no_competitors():
    """Analyze channels that have dates but no competitor extraction."""

    # Get the sync reference date from database
    sync_date = SyncDateService.get_reference_date("data/iptv_proxy.db")
    print(f"Using sync reference date: {sync_date}")
    print()

    # Track patterns
    separator_patterns = Counter()
    provider_patterns = Counter()
    examples_by_separator = {}

    print("Reading DATE_BUT_NO_COMPETITORS.list...")
    with open("DATE_BUT_NO_COMPETITORS.list", "r", encoding="utf-8") as f:
        total = 0
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            total += 1
            parts = line.split("|")
            if len(parts) < 3:
                continue

            # Extract channel name
            if len(parts) >= 6:
                channel_name = "|".join(parts[2:-3])
            else:
                channel_name = parts[2]

            category = parts[-2] if len(parts) >= 6 else "Unknown"

            # Track provider/category
            provider_patterns[category] += 1

            # Look for potential separators in the channel name
            # Common separators: vs, v, at, @, -, x, :
            has_vs = bool(re.search(r"\bvs\.?\b", channel_name, re.IGNORECASE))
            has_v = bool(re.search(r"\bv\b", channel_name, re.IGNORECASE))
            has_at = bool(re.search(r"\bat\b|\b@\b", channel_name, re.IGNORECASE))
            has_dash = bool(re.search(r"\s-\s", channel_name))
            has_x = bool(re.search(r"\bx\b", channel_name, re.IGNORECASE))
            has_colon = bool(re.search(r":\s+[A-Z]", channel_name))

            separators = []
            if has_vs:
                separators.append("vs")
            if has_v and not has_vs:
                separators.append("v")
            if has_at:
                separators.append("at/@")
            if has_dash:
                separators.append("-")
            if has_x:
                separators.append("x")
            if has_colon:
                separators.append(":")

            if separators:
                sep_key = ",".join(separators)
                separator_patterns[sep_key] += 1

                # Save examples for each separator type
                if sep_key not in examples_by_separator:
                    examples_by_separator[sep_key] = []
                if len(examples_by_separator[sep_key]) < 3:
                    examples_by_separator[sep_key].append((channel_name, category))

    # Print analysis
    print("=" * 80)
    print(f"ANALYSIS OF {total} CHANNELS WITH DATE BUT NO COMPETITORS")
    print("=" * 80)
    print()

    print("TOP PROVIDERS/CATEGORIES:")
    print("-" * 80)
    for provider, count in provider_patterns.most_common(15):
        pct = count / total * 100
        print(f"  {count:5d} ({pct:5.1f}%)  {provider}")
    print()

    print("POTENTIAL SEPARATOR PATTERNS FOUND:")
    print("-" * 80)
    for separator, count in separator_patterns.most_common(10):
        pct = count / total * 100
        print(f"  {count:5d} ({pct:5.1f}%)  {separator}")
        if separator in examples_by_separator:
            print("           Examples:")
            for channel_name, category in examples_by_separator[separator][:2]:
                print(f"             • {channel_name[:70]}")
                print(f"               [{category}]")
        print()

    # Look for channels without obvious separators
    no_separator_count = total - sum(separator_patterns.values())
    if no_separator_count > 0:
        print(f"CHANNELS WITHOUT OBVIOUS SEPARATORS: {no_separator_count} ({no_separator_count / total * 100:.1f}%)")
        print("  (These may be event titles without team names, or use uncommon patterns)")
        print()

    print("=" * 80)
    print()
    print("RECOMMENDATIONS:")
    print("-" * 80)
    print("1. Add support for 'x' as a competitor separator (common in Spanish/Portuguese)")
    print("2. Improve handling of dash-separated teams (may be getting confused with prefixes)")
    print("3. Consider 'v' (single letter) as a separator in some contexts")
    print("4. Add better parsing for event titles with colons (e.g., 'League: Team1 x Team2')")
    print("=" * 80)


if __name__ == "__main__":
    analyze_date_but_no_competitors()
