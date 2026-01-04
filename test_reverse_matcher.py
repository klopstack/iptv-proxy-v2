#!/usr/bin/env python3
"""
Test the reverse event matcher against actual PPV channel data.

This script:
1. Loads calendar events for the next 14 days
2. Samples PPV channels from the database
3. Tests the reverse matcher against channels that failed extraction
4. Compares results with channels that successfully matched
"""

import os
import random
import sys

# Setup path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flask

# Configure database
db_path = os.path.join(os.path.dirname(__file__), "data", "iptv_proxy.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from models import Channel, EventChannelLink, db
from services.ppv_event_extractor import PPVEventExtractor
from services.reverse_event_matcher import ReverseEventMatcher, get_reverse_matcher

# Create Flask app
app = flask.Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def test_reverse_matcher():
    """Test the reverse matcher against real PPV channels."""
    with app.app_context():
        print("=" * 80)
        print("REVERSE EVENT MATCHER TEST")
        print("=" * 80)

        # Initialize matcher and load events
        matcher = get_reverse_matcher()

        print("\nLoading calendar events for next 14 days...")
        num_events = matcher.load_events_for_date_range(days_ahead=14, days_back=21)

        stats = matcher.get_stats()
        print(f"\nMatcher Statistics:")
        print(f"  Events loaded: {stats['events_loaded']}")
        print(f"  Date range: {stats['date_range']}")
        print(f"  Teams indexed: {stats['team_index_size']}")
        print(f"  Event names indexed: {stats['event_name_index_size']}")
        print(f"  Leagues indexed: {stats['league_index_size']}")
        print(f"  Words indexed: {stats['word_index_size']}")

        # Get PPV channels
        all_ppv = Channel.query.filter_by(is_ppv=True, is_active=True, is_visible=True).all()
        print(f"\nTotal PPV channels: {len(all_ppv)}")

        # Get channels that already have event links (for comparison)
        linked_channel_ids = set(row[0] for row in db.session.query(EventChannelLink.channel_id).all())

        linked_channels = [ch for ch in all_ppv if ch.id in linked_channel_ids]
        unlinked_channels = [ch for ch in all_ppv if ch.id not in linked_channel_ids]

        print(f"Channels with existing event links: {len(linked_channels)}")
        print(f"Channels without event links: {len(unlinked_channels)}")

        # Initialize extractor for comparison
        extractor = PPVEventExtractor()

        # Test 1: Channels that FAILED extraction but might match with reverse lookup
        print("\n" + "=" * 80)
        print("TEST 1: CHANNELS THAT FAILED EXTRACTION")
        print("=" * 80)

        # Find channels where extraction failed to get competitors
        failed_extraction = []
        for ch in unlinked_channels:
            ex = extractor.extract_all(ch.name)
            if not ex.get("competitors") and not ex.get("is_placeholder"):
                failed_extraction.append(ch)

        print(f"\nChannels that failed competitor extraction: {len(failed_extraction)}")

        # Sample and test
        sample_size = min(50, len(failed_extraction))
        sample = random.sample(failed_extraction, sample_size)

        matches_found = 0
        high_confidence_matches = 0

        print(f"\nTesting {sample_size} channels with reverse matcher:")
        print("-" * 80)

        for i, ch in enumerate(sample, 1):
            matches = matcher.find_matches(ch.name, max_results=3, min_confidence=0.3)

            if matches:
                matches_found += 1
                best = matches[0]
                if best.confidence >= 0.7:
                    high_confidence_matches += 1

                print(f"\n{i}. MATCH FOUND for: {ch.name[:70]}...")
                print(f"   Best match: {best.event.event_name} ({best.event.league_name})")
                print(f"   Confidence: {best.confidence:.2f}, Type: {best.match_type}")
                print(f"   Matched terms: {best.matched_terms}")
                if len(matches) > 1:
                    print(f"   Alt matches: {len(matches)-1}")
            else:
                if i <= 10 or i % 10 == 0:  # Show some failures
                    print(f"\n{i}. NO MATCH: {ch.name[:70]}...")

        print(f"\n--- Summary ---")
        print(f"Tested: {sample_size}")
        print(f"Matches found: {matches_found} ({matches_found/sample_size*100:.1f}%)")
        print(f"High confidence (>=0.7): {high_confidence_matches} ({high_confidence_matches/sample_size*100:.1f}%)")

        # Test 2: Verify reverse matcher works on channels that HAD extraction success
        print("\n" + "=" * 80)
        print("TEST 2: CHANNELS THAT HAD SUCCESSFUL EXTRACTION (verification)")
        print("=" * 80)

        sample_linked = random.sample(linked_channels, min(20, len(linked_channels)))

        linked_matches = 0
        for ch in sample_linked:
            matches = matcher.find_matches(ch.name, max_results=1, min_confidence=0.3)
            if matches:
                linked_matches += 1
                print(f"\n  ✓ {ch.name[:60]}...")
                print(f"    → {matches[0].event.event_name} (conf: {matches[0].confidence:.2f})")
            else:
                print(f"\n  ✗ {ch.name[:60]}... (NO MATCH)")

        print(f"\nLinked channels that also match with reverse: {linked_matches}/{len(sample_linked)}")

        # Test 3: Show some specific problem cases
        print("\n" + "=" * 80)
        print("TEST 3: SPECIFIC PROBLEM CASES")
        print("=" * 80)

        test_cases = [
            "Flo (FLSP) 229: 2025 Atlanta Gladiators vs Orlando Solar Bears Away - 23/10 19:00",
            "(FLSP 620) | flohoops: 2026 Cedarville vs Tiffin University _ Men`s (Cedarville vs Tiffin University) (2026-01-05 19:15:00)",
            "AU (STAN 51) | Crystal Palace v Aston Villa _ Premier League 2025/2026 (2026-01-08 06:20:12)",
            "NFL  | 07 - 1PM Titans at Jaguars",
            "Boxing 1: Jake Paul vs Anthony Joshua",
            "UFC 00 : CFFC BJJ 16 start:2025-12-28 01:55:00 stop:2025-12-28 07:00:00",
            "US: FIFA+ PPV 2 - GARDEN STARS FC V GRENADES FC | ANTIGUA PREMIER LEAGUE 2025/26",
        ]

        for name in test_cases:
            print(f"\nChannel: {name[:70]}...")

            # Traditional extraction
            ex = extractor.extract_all(name)
            print(f"  Extractor result: competitors={ex.get('competitors')}")

            # Reverse matching
            matches = matcher.find_matches(name, max_results=3, min_confidence=0.2)
            if matches:
                for j, m in enumerate(matches, 1):
                    print(f"  Reverse match {j}: {m.event.event_name[:50]}...")
                    print(f"    Confidence: {m.confidence:.2f}, Type: {m.match_type}, Terms: {m.matched_terms}")
            else:
                print(f"  Reverse match: NONE")


if __name__ == "__main__":
    test_reverse_matcher()
