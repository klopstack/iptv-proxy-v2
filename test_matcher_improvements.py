#!/usr/bin/env python3
"""
Test timestamp stripping improvements specifically.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flask

db_path = os.path.join(os.path.dirname(__file__), "data", "iptv_proxy.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from models import db
from services.reverse_event_matcher import ReverseEventMatcher, get_reverse_matcher

app = flask.Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
db.init_app(app)


def test_improvements():
    """Test the specific improvements we made."""
    with app.app_context():
        matcher = get_reverse_matcher()
        matcher.load_events_for_date_range(days_ahead=14, days_back=21)

        print("=" * 80)
        print("TESTING TIMESTAMP STRIPPING & GENERIC CHANNEL DETECTION")
        print("=" * 80)

        # Test cases that should improve
        test_cases = [
            # Timestamp-heavy channels
            {
                "name": "UFC 00 : CFFC BJJ 16 start:2025-12-28 01:55:00 stop:2025-12-28 07:00:00",
                "expected": "Should find MMA/UFC event or return nothing if generic",
            },
            {
                "name": "UFC 03: UFC VEGAS 112: POST-FIGHT PRESS CONFERENCE start:2025-12-14 06:55:00",
                "expected": "Should find UFC VEGAS event",
            },
            {
                "name": "LIVE EVENT 26 -Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK / 6PM ET / 3PM PT",
                "expected": "Should strip timezones and look for fighter names",
            },
            # Generic channels that should be skipped
            {
                "name": "Milb 02 :",
                "expected": "Should detect as generic and skip",
            },
            {
                "name": "US: NFL NETWORK ᴴᴰ",
                "expected": "Should detect as generic network channel",
            },
            {
                "name": "US: NFL REDZONE ᴴᴰ",
                "expected": "Should detect as generic network channel",
            },
            {
                "name": "NCAAF 51:",
                "expected": "Should detect as generic sport category",
            },
            # Should still work
            {
                "name": "NFL  | 07 - 1PM Titans at Jaguars",
                "expected": "Should still find Titans vs Jaguars",
            },
            {
                "name": "NBA 01: San Antonio Spurs @ Indiana Pacers // UK Fri 2 Jan 11:45pm // ET Fri 2 Jan 6:45pm",
                "expected": "Should strip timezones and find Spurs vs Pacers",
            },
        ]

        print("\nTesting timestamp stripping and generic detection:\n")

        generic_count = 0
        match_count = 0
        improved_count = 0

        for i, test in enumerate(test_cases, 1):
            name = test["name"]
            expected = test["expected"]

            print(f"\n{i}. Channel: {name[:70]}...")
            print(f"   Expected: {expected}")

            # Test generic detection
            is_generic = matcher._is_generic_channel(name)
            if is_generic:
                print(f"   Result: ✅ DETECTED AS GENERIC (skipped)")
                generic_count += 1
                continue

            # Try to match
            matches = matcher.find_matches(name, max_results=3, min_confidence=0.3)

            if matches:
                best = matches[0]
                print(f"   Result: ✅ MATCH FOUND")
                print(f"     Event: {best.event.event_name}")
                print(f"     League: {best.event.league_name}")
                print(f"     Confidence: {best.confidence:.2f}, Type: {best.match_type}")
                print(f"     Terms: {best.matched_terms}")
                match_count += 1

                # Check if this is an improvement (high confidence or good match type)
                if best.confidence >= 0.7 or best.match_type in ["both_teams", "both_last_names"]:
                    improved_count += 1
            else:
                print(f"   Result: ❌ NO MATCH (but not generic)")

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total test cases: {len(test_cases)}")
        print(f"Detected as generic (skipped): {generic_count}")
        print(f"Matches found: {match_count}")
        print(f"High quality matches: {improved_count}")

        # Test the normalization directly
        print("\n" + "=" * 80)
        print("TIMESTAMP STRIPPING EXAMPLES")
        print("=" * 80)

        examples = [
            "UFC 00 : CFFC BJJ 16 start:2025-12-28 01:55:00 stop:2025-12-28 07:00:00",
            "NBA 01: San Antonio Spurs @ Indiana Pacers // UK Fri 2 Jan 11:45pm // ET Fri 2 Jan 6:45pm",
            "LIVE EVENT 26 -Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK / 6PM ET / 3PM PT",
        ]

        for ex in examples:
            normalized = matcher._normalize_text(ex)
            print(f"\nOriginal : {ex[:75]}")
            print(f"Cleaned  : {normalized}")


if __name__ == "__main__":
    test_improvements()
