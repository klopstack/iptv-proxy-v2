#!/usr/bin/env python3
"""
Quick comparison: Traditional extractor vs reverse matcher.
Tests only 200 channels for speed.
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flask

db_path = os.path.join(os.path.dirname(__file__), "data", "iptv_proxy.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from models import Channel, EventChannelLink, db
from services.ppv_event_extractor import PPVEventExtractor
from services.reverse_event_matcher import get_reverse_matcher

app = flask.Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def quick_compare():
    """Fast comparison on small sample."""
    with app.app_context():
        print("=" * 80)
        print("QUICK COMPARISON: EXTRACTOR VS MATCHER (200 channel sample)")
        print("=" * 80)

        # Initialize
        extractor = PPVEventExtractor()
        matcher = get_reverse_matcher()

        print("\nLoading calendar...")
        matcher.load_events_for_date_range(days_ahead=14, days_back=21)
        print(f"✓ Loaded {matcher.get_stats()['events_loaded']} events")

        # Get channels
        all_ppv = Channel.query.filter_by(is_ppv=True, is_active=True, is_visible=True).all()

        # Sample 200 channels
        import random

        random.seed(42)  # Reproducible
        sample = random.sample(all_ppv, min(200, len(all_ppv)))

        print(f"\n📊 Testing {len(sample)} channels...")
        print("=" * 80)

        # Test both methods
        extractor_found = []
        matcher_found = []
        both_found = []
        neither_found = []

        extractor_only = []
        matcher_only = []

        for i, ch in enumerate(sample, 1):
            if i % 50 == 0:
                print(f"Progress: {i}/{len(sample)}...")

            # Test extractor
            ex = extractor.extract_all(ch.name)
            ex_success = bool(ex.get("competitors"))

            # Test matcher (skip generics, use higher min confidence)
            if matcher._is_generic_channel(ch.name):
                ma_success = False
                matches = []
            else:
                matches = matcher.find_matches(ch.name, max_results=1, min_confidence=0.5)
                ma_success = bool(matches)

            # Categorize
            if ex_success and ma_success:
                both_found.append((ch, ex, matches[0]))
            elif ex_success and not ma_success:
                extractor_only.append((ch, ex))
                extractor_found.append(ch)
            elif not ex_success and ma_success:
                matcher_only.append((ch, matches[0]))
                matcher_found.append(ch)
            else:
                neither_found.append(ch)

            if ex_success:
                extractor_found.append(ch)
            if ma_success:
                matcher_found.append(ch)

        # Results
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)

        total = len(sample)
        print(f"\nSample size: {total} channels")
        print(f"\nExtractor success: {len(extractor_found)} ({len(extractor_found)/total*100:.1f}%)")
        print(f"Matcher success:   {len(matcher_found)} ({len(matcher_found)/total*100:.1f}%) [min conf 0.5]")

        print(f"\nOverlap Analysis:")
        print(f"  Both found:         {len(both_found)} ({len(both_found)/total*100:.1f}%)")
        print(f"  Only extractor:     {len(extractor_only)} ({len(extractor_only)/total*100:.1f}%)")
        print(f"  Only matcher:       {len(matcher_only)} ({len(matcher_only)/total*100:.1f}%)")
        print(f"  Neither found:      {len(neither_found)} ({len(neither_found)/total*100:.1f}%)")

        # Combined coverage
        combined = len(extractor_found) + len([ch for ch, _ in matcher_only])
        unique_combined = len(set([ch.id for ch in extractor_found] + [ch.id for ch, _ in matcher_only]))

        print(f"\nCombined Coverage (extractor + matcher fallback):")
        print(f"  Total: {unique_combined} ({unique_combined/total*100:.1f}%)")
        print(f"  Improvement: +{len(matcher_only)} channels (+{len(matcher_only)/total*100:.1f}%)")

        # Show examples
        if extractor_only:
            print(f"\n" + "=" * 80)
            print("EXAMPLES: Extractor found, Matcher missed (first 5)")
            print("=" * 80)
            for ch, ex in extractor_only[:5]:
                print(f"\n• {ch.name[:70]}...")
                print(f"  Extractor: {ex['competitors']}")
                print(f"  Matcher: NO MATCH at 0.5+ confidence")

        if matcher_only:
            print(f"\n" + "=" * 80)
            print("EXAMPLES: Matcher found, Extractor missed (first 5)")
            print("=" * 80)
            for ch, match in matcher_only[:5]:
                print(f"\n• {ch.name[:70]}...")
                print(f"  Extractor: NO COMPETITORS FOUND")
                print(f"  Matcher: {match.event.event_name}")
                print(f"    Confidence: {match.confidence:.2f}, Type: {match.match_type}")
                print(f"    League: {match.event.league_name}")

        if both_found:
            print(f"\n" + "=" * 80)
            print("EXAMPLES: Both found (first 3)")
            print("=" * 80)
            for ch, ex, match in both_found[:3]:
                print(f"\n• {ch.name[:70]}...")
                print(f"  Extractor: {ex['competitors']}")
                print(f"  Matcher: {match.event.event_name} (conf: {match.confidence:.2f})")

        # Recommendation
        print(f"\n" + "=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)

        if len(extractor_only) > len(matcher_only):
            print(f"\n⚠️  DON'T REPLACE")
            print(f"   Extractor finds {len(extractor_only)} unique matches")
            print(f"   Matcher finds {len(matcher_only)} unique matches")
            print(f"   Net: Extractor finds {len(extractor_only) - len(matcher_only)} more")
            print(f"\n   ✅ Best approach: Keep extractor, use matcher as FALLBACK")
            print(f"      This would give {unique_combined} total matches ({unique_combined/total*100:.1f}%)")
        elif len(matcher_only) > len(extractor_only):
            print(f"\n✅ MATCHER IS BETTER")
            print(f"   Matcher finds {len(matcher_only)} unique matches")
            print(f"   Extractor finds {len(extractor_only)} unique matches")
            print(f"   Net: Matcher finds {len(matcher_only) - len(extractor_only)} more")
            print(f"\n   Consider replacing, but validate match quality first")
        else:
            print(f"\n⚖️  SIMILAR PERFORMANCE")
            print(f"   Both find similar numbers of unique matches")
            print(f"   ✅ Best approach: Use BOTH (extractor + matcher fallback)")


if __name__ == "__main__":
    quick_compare()
