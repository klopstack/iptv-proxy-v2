#!/usr/bin/env python3
"""
Demo script showing last name matching and persistent caching.

This demonstrates:
1. Persistent cache loading from disk (avoiding server hits)
2. Last name matching (e.g., "SERRANO VS TELLEZ" → "Amanda Serrano vs Reina Tellez")
3. Performance improvement from caching
"""

import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from services.reverse_event_matcher import ReverseEventMatcher
from services.thesportsdb_calendar_scraper import TheSportsDBCalendarScraper


def main():
    """Run the demo."""
    print("=" * 80)
    print("Last Name Matching & Persistent Caching Demo")
    print("=" * 80)
    print()

    # Create scraper with persistent cache
    print("1. Creating scraper with persistent cache...")
    scraper = TheSportsDBCalendarScraper(cache_dir="data")
    print(f"   Cache file: {scraper._cache_file_path}")
    print()

    # Show cache stats before loading
    stats = scraper.get_cache_stats()
    print("2. Cache stats BEFORE loading events:")
    print(f"   Memory cache entries: {stats['total_entries']}")
    print(f"   Disk loads: {stats['disk_loads']}")
    if stats["persistent_cache_file"]:
        print(f"   Persistent cache exists: {stats['persistent_cache_file']}")
        print(f"   Persistent cache size: {stats['persistent_cache_size_bytes']:,} bytes")
    else:
        print("   No persistent cache file found")
    print()

    # Create matcher and load events
    print("3. Loading events (will use cache if available)...")
    start = time.time()
    matcher = ReverseEventMatcher(scraper)

    # Load events for a date range covering boxing events
    end_date = datetime.now()
    start_date = end_date - timedelta(days=14)  # Last 2 weeks
    matcher.load_events_for_date_range(start_date, end_date)
    elapsed = time.time() - start
    print(f"   Loaded {len(matcher._events)} events in {elapsed:.2f}s")
    print()

    # Show cache stats after loading
    stats = scraper.get_cache_stats()
    print("4. Cache stats AFTER loading events:")
    print(f"   Memory cache entries: {stats['total_entries']}")
    print(f"   Disk loads: {stats['disk_loads']}")
    print(f"   Hit rate: {stats['hit_rate']:.1%}")
    print()

    # Show index sizes
    print("5. Index sizes:")
    print(f"   Team index: {len(matcher._team_index)} teams")
    print(f"   Last name index: {len(matcher._last_name_index)} last names")
    print(f"   First name index: {len(matcher._first_name_index)} first names")
    print()

    # Test matching with abbreviated names
    test_channels = [
        "SERRANO VS TELLEZ",
        "PAUL VS JOSHUA",
        "serrano vs. tellez",
        "AMANDA SERRANO VS REINA TELLEZ",
    ]

    print("6. Testing last name matching:")
    print()
    for channel in test_channels:
        print(f"   Channel: '{channel}'")
        matches = matcher.find_matches(channel)
        if matches:
            for match in matches[:2]:  # Show top 2
                print(
                    f"      → Matched: {match.event_name} " f"(conf: {match.confidence:.2f}, type: {match.match_type})"
                )
        else:
            print("      → No matches found")
        print()

    # Show some example name parts
    print("7. Example name parts indexed:")
    for event_id in list(matcher._name_parts.keys())[:3]:
        parts = matcher._name_parts[event_id]
        print(f"   Event {event_id}: {parts}")
    print()

    print("=" * 80)
    print("Demo complete!")
    print()
    print("Key takeaways:")
    print("- Persistent cache survives script restarts (stored in data/calendar_cache.json)")
    print("- Last name matching works for abbreviated channel names")
    print("- First run fetches from web, subsequent runs use cache")
    print("- Cache has 12-hour TTL to keep data fresh")
    print("=" * 80)


if __name__ == "__main__":
    main()
