#!/usr/bin/env python3
"""
Compare traditional PPV extractor vs reverse event matcher.

This script tests what would happen if we replaced the traditional
extractor with the reverse matcher.
"""

import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flask

db_path = os.path.join(os.path.dirname(__file__), "data", "iptv_proxy.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from models import Channel, EventChannelLink, db
from services.ppv_event_extractor import PPVEventExtractor
from services.reverse_event_matcher import ReverseEventMatcher, get_reverse_matcher

app = flask.Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def compare_methods():
    """Compare traditional extractor vs reverse matcher."""
    with app.app_context():
        print("=" * 80)
        print("TRADITIONAL EXTRACTOR VS REVERSE MATCHER COMPARISON")
        print("=" * 80)

        # Initialize both services
        extractor = PPVEventExtractor()
        matcher = get_reverse_matcher()

        print("\nLoading calendar events for reverse matcher...")
        matcher.load_events_for_date_range(days_ahead=14, days_back=21)

        stats = matcher.get_stats()
        print(f"Calendar loaded: {stats['events_loaded']} events")

        # Get all PPV channels
        all_ppv = Channel.query.filter_by(is_ppv=True, is_active=True, is_visible=True).all()
        print(f"\nTotal PPV channels: {len(all_ppv)}")

        # Get existing links to see what's currently working
        linked_channel_ids = set(row[0] for row in db.session.query(EventChannelLink.channel_id).all())

        # Split channels
        currently_linked = [ch for ch in all_ppv if ch.id in linked_channel_ids]
        currently_unlinked = [ch for ch in all_ppv if ch.id not in linked_channel_ids]

        print(f"Channels with existing event links: {len(currently_linked)}")
        print(f"Channels without event links: {len(currently_unlinked)}")

        # Test 1: How well does extractor work on ALL channels?
        print("\n" + "=" * 80)
        print("TEST 1: TRADITIONAL EXTRACTOR ON ALL CHANNELS")
        print("=" * 80)

        extractor_success = 0
        extractor_has_date = 0
        extractor_has_competitors = 0
        extractor_placeholders = 0

        sample_size = min(1000, len(all_ppv))

        for ch in all_ppv[:sample_size]:
            ex = extractor.extract_all(ch.name)
            if ex.get("competitors"):
                extractor_success += 1
                extractor_has_competitors += 1
            if ex.get("date"):
                extractor_has_date += 1
            if ex.get("is_placeholder"):
                extractor_placeholders += 1
        print(f"\nSample size: {sample_size}")
        print(f"Found competitors: {extractor_has_competitors} ({extractor_has_competitors/sample_size*100:.1f}%)")
        print(f"Found dates: {extractor_has_date} ({extractor_has_date/sample_size*100:.1f}%)")
        print(f"Placeholders: {extractor_placeholders} ({extractor_placeholders/sample_size*100:.1f}%)")

        # Test 2: How well does reverse matcher work on ALL channels?
        print("\n" + "=" * 80)
        print("TEST 2: REVERSE MATCHER ON ALL CHANNELS")
        print("=" * 80)

        matcher_success = 0
        matcher_high_conf = 0
        matcher_medium_conf = 0
        matcher_low_conf = 0
        matcher_skipped_generic = 0

        confidence_dist = []
        match_types = Counter()

        print(f"Testing {sample_size} channels (this may take a few minutes)...")

        for i, ch in enumerate(all_ppv[:sample_size], 1):
            if i % 200 == 0:
                print(f"Progress: {i}/{sample_size}")

            # Check if generic first
            if matcher._is_generic_channel(ch.name):
                matcher_skipped_generic += 1
                continue

            matches = matcher.find_matches(ch.name, max_results=1, min_confidence=0.3)
            if matches:
                matcher_success += 1
                conf = matches[0].confidence
                confidence_dist.append(conf)
                match_types[matches[0].match_type] += 1

                if conf >= 0.7:
                    matcher_high_conf += 1
                elif conf >= 0.5:
                    matcher_medium_conf += 1
                else:
                    matcher_low_conf += 1

        print(f"\nSample size: {sample_size}")
        print(f"Skipped (generic): {matcher_skipped_generic} ({matcher_skipped_generic/sample_size*100:.1f}%)")
        print(f"Matches found: {matcher_success} ({matcher_success/sample_size*100:.1f}%)")
        print(f"  High confidence (≥0.7): {matcher_high_conf} ({matcher_high_conf/sample_size*100:.1f}%)")
        print(f"  Medium confidence (0.5-0.69): {matcher_medium_conf} ({matcher_medium_conf/sample_size*100:.1f}%)")
        print(f"  Low confidence (0.3-0.49): {matcher_low_conf} ({matcher_low_conf/sample_size*100:.1f}%)")

        if confidence_dist:
            print(f"Average confidence: {sum(confidence_dist)/len(confidence_dist):.2f}")

        print(f"\nMatch types:")
        for match_type, count in match_types.most_common():
            print(f"  {match_type}: {count}")

        # Test 3: Direct comparison on channels that extractor finds competitors
        print("\n" + "=" * 80)
        print("TEST 3: WOULD REVERSE MATCHER FIND EXTRACTOR'S SUCCESSES?")
        print("=" * 80)

        extractor_successes = []
        for ch in all_ppv[:sample_size]:
            ex = extractor.extract_all(ch.name)
            if ex.get("competitors"):
                extractor_successes.append(ch)

        print(f"\nExtractor found competitors in: {len(extractor_successes)} channels")
        print(f"Testing if reverse matcher would also find these...\n")

        matcher_also_found = 0
        matcher_high_conf_overlap = 0
        matcher_missed = 0
        matcher_skipped = 0

        missed_examples = []

        for i, ch in enumerate(extractor_successes, 1):
            if matcher._is_generic_channel(ch.name):
                matcher_skipped += 1
                continue

            matches = matcher.find_matches(ch.name, max_results=1, min_confidence=0.3)
            if matches:
                matcher_also_found += 1
                if matches[0].confidence >= 0.7:
                    matcher_high_conf_overlap += 1
            else:
                matcher_missed += 1
                if len(missed_examples) < 10:
                    ex = extractor.extract_all(ch.name)
                    missed_examples.append(
                        {
                            "name": ch.name,
                            "competitors": ex.get("competitors"),
                        }
                    )

        print(f"Results:")
        print(
            f"  Matcher also found: {matcher_also_found}/{len(extractor_successes)} ({matcher_also_found/len(extractor_successes)*100:.1f}%)"
        )
        print(
            f"  High confidence: {matcher_high_conf_overlap}/{len(extractor_successes)} ({matcher_high_conf_overlap/len(extractor_successes)*100:.1f}%)"
        )
        print(
            f"  Matcher missed: {matcher_missed}/{len(extractor_successes)} ({matcher_missed/len(extractor_successes)*100:.1f}%)"
        )
        print(
            f"  Matcher skipped (generic): {matcher_skipped}/{len(extractor_successes)} ({matcher_skipped/len(extractor_successes)*100:.1f}%)"
        )

        if missed_examples:
            print(f"\nExamples matcher missed (but extractor found):")
            for ex in missed_examples[:5]:
                print(f"  - {ex['name'][:70]}...")
                print(f"    Extractor found: {ex['competitors']}")

        # Test 4: What does matcher find that extractor doesn't?
        print("\n" + "=" * 80)
        print("TEST 4: WHAT DOES MATCHER FIND THAT EXTRACTOR DOESN'T?")
        print("=" * 80)

        extractor_failures = []
        for ch in all_ppv[:sample_size]:
            ex = extractor.extract_all(ch.name)
            if not ex.get("competitors") and not ex.get("is_placeholder"):
                extractor_failures.append(ch)

        print(f"\nExtractor failed to find competitors in: {len(extractor_failures)} channels")
        print(f"Testing if reverse matcher can find these...\n")

        matcher_rescue = 0
        matcher_rescue_high_conf = 0

        rescue_examples = []

        for ch in extractor_failures:
            if matcher._is_generic_channel(ch.name):
                continue

            matches = matcher.find_matches(ch.name, max_results=1, min_confidence=0.5)
            if matches:
                matcher_rescue += 1
                if matches[0].confidence >= 0.7:
                    matcher_rescue_high_conf += 1

                if len(rescue_examples) < 10:
                    rescue_examples.append(
                        {
                            "name": ch.name,
                            "event": matches[0].event.event_name,
                            "conf": matches[0].confidence,
                            "type": matches[0].match_type,
                        }
                    )

        print(f"Results:")
        print(
            f"  Matcher rescued: {matcher_rescue}/{len(extractor_failures)} ({matcher_rescue/len(extractor_failures)*100:.1f}%)"
        )
        print(
            f"  High confidence (≥0.7): {matcher_rescue_high_conf}/{len(extractor_failures)} ({matcher_rescue_high_conf/len(extractor_failures)*100:.1f}%)"
        )

        if rescue_examples:
            print(f"\nExamples matcher rescued (at ≥0.5 confidence):")
            for ex in rescue_examples[:5]:
                print(f"  - {ex['name'][:60]}...")
                print(f"    Matched: {ex['event'][:50]} (conf: {ex['conf']:.2f}, type: {ex['type']})")

        # Test 5: Overall comparison
        print("\n" + "=" * 80)
        print("FINAL COMPARISON: IF WE REPLACED EXTRACTOR WITH MATCHER")
        print("=" * 80)

        extractor_total = extractor_has_competitors
        matcher_total = matcher_success

        # Calculate overlap and unique
        both_found = matcher_also_found
        only_extractor = matcher_missed
        only_matcher = matcher_rescue

        print(f"\nCoverage Analysis (sample: {sample_size} channels):")
        print(f"  Extractor finds: {extractor_total} ({extractor_total/sample_size*100:.1f}%)")
        print(f"  Matcher finds: {matcher_total} ({matcher_total/sample_size*100:.1f}%)")
        print(f"\nOverlap & Unique:")
        print(f"  Both methods find: ~{both_found} channels")
        print(f"  Only extractor finds: ~{only_extractor} channels")
        print(f"  Only matcher finds: ~{only_matcher} channels (at ≥0.5 conf)")

        # Calculate combined coverage
        combined = extractor_total + only_matcher
        print(f"\nIf we use BOTH (extractor + matcher fallback):")
        print(f"  Total coverage: ~{combined} channels ({combined/sample_size*100:.1f}%)")
        print(f"  Improvement over extractor alone: +{only_matcher} channels (+{only_matcher/sample_size*100:.1f}%)")

        print(f"\nIf we REPLACE extractor with matcher:")
        print(f"  We'd lose: ~{only_extractor} channels ({only_extractor/sample_size*100:.1f}%)")
        print(f"  We'd gain: ~{only_matcher} channels ({only_matcher/sample_size*100:.1f}%)")
        print(f"  Net change: {only_matcher - only_extractor} channels")

        # Recommendation
        print("\n" + "=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)

        if only_extractor > only_matcher:
            print("\n⚠️  DON'T REPLACE - Keep extractor as primary")
            print(f"   Reason: Extractor finds {only_extractor - only_matcher} more channels")
            print(f"   Recommendation: Use matcher as FALLBACK for extractor failures")
        elif only_matcher > only_extractor * 2:
            print("\n✅ CONSIDER REPLACING - Matcher significantly better")
            print(f"   Reason: Matcher finds {only_matcher - only_extractor} more channels")
            print(f"   But validate quality of matcher's high-confidence matches first")
        else:
            print("\n⚖️  COMPARABLE PERFORMANCE")
            print(f"   Recommendation: Use BOTH methods in parallel or as fallback")
            print(f"   - Extractor for structured channel names")
            print(f"   - Matcher for messy/non-standard formats")


if __name__ == "__main__":
    compare_methods()
