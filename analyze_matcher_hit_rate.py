#!/usr/bin/env python3
"""
Comprehensive analysis of reverse event matcher hit rate.

This script:
1. Tests the matcher against all unlinked PPV channels
2. Categorizes failure cases by pattern
3. Identifies improvement opportunities
4. Generates actionable recommendations
"""

import os
import sys
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

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


class FailureType:
    """Categories for matching failures."""

    NO_SPORTS_KEYWORDS = "no_sports_keywords"  # No recognizable team/league/sport names
    GENERIC_CHANNEL = "generic_channel"  # Generic channel name (ESPN HD, etc)
    FOREIGN_LEAGUE = "foreign_league"  # Non-English league not in calendar
    COLLEGE_SPORTS = "college_sports"  # College/university sports
    DATE_MISMATCH = "date_mismatch"  # Date in channel name doesn't match event date
    WRONG_MATCH = "wrong_match"  # Low confidence or clearly wrong match
    PARSING_ISSUE = "parsing_issue"  # Channel name is too messy to parse
    MINOR_LEAGUE = "minor_league"  # Minor league/lower division not in calendar
    INDIVIDUAL_SPORTS = "individual_sports"  # Tennis, golf, etc (person names)
    COMBAT_SPORTS = "combat_sports"  # Boxing, MMA with fighter names
    REPLAY_OLD_EVENT = "replay_old_event"  # Replay of event outside date range
    UNKNOWN = "unknown"  # Can't determine why it failed


def categorize_failure(channel_name: str, extraction: Dict) -> str:
    """Categorize why a channel failed to match."""
    name_lower = channel_name.lower()

    # Generic channel names
    if any(
        x in name_lower
        for x in [
            "bally sports",
            "espn hd",
            "fox sports",
            "paramount+",
            "mlb tv",
            "nhl tv",
            "nba tv",
            "milb ",
            "ncaaf ",
            "tennis  ",
        ]
    ):
        return FailureType.GENERIC_CHANNEL

    # Individual/combat sports
    if any(x in name_lower for x in ["jake paul", "anthony joshua", "ufc ", "boxing ", "mma "]):
        return FailureType.COMBAT_SPORTS

    # College sports indicators
    if any(x in name_lower for x in ["college", "university", "ncaa", "vs cedarville", "vs tiffin", "high school"]):
        return FailureType.COLLEGE_SPORTS

    # Foreign/non-major leagues
    if any(
        x in name_lower
        for x in [
            "antigua premier",
            "garden stars fc",
            "grenades fc",
            "cffc",
            "bjj ",
            "juco",
            "junior college",
        ]
    ):
        return FailureType.FOREIGN_LEAGUE

    # Minor leagues
    if any(x in name_lower for x in ["aeros", "swamp rabbits", "solar bears", "gladiators vs orlando"]):
        return FailureType.MINOR_LEAGUE

    # Parsing issues (too messy)
    if "paolini v bencic" in name_lower:
        return FailureType.INDIVIDUAL_SPORTS

    # Has some sports content but no clear match
    if any(x in name_lower for x in [" vs ", " v ", " at ", "nba", "nfl", "nhl", "mlb", "premier league", "football"]):
        return FailureType.NO_SPORTS_KEYWORDS

    return FailureType.UNKNOWN


def analyze_match_quality(channel_name: str, matches: List, extractor: PPVEventExtractor) -> Dict:
    """Analyze the quality of matches found."""
    result = {
        "has_match": False,
        "high_confidence": False,
        "correct_sport": False,
        "best_confidence": 0.0,
        "best_match_type": None,
        "extractor_would_match": False,
    }

    if not matches:
        return result

    best = matches[0]
    result["has_match"] = True
    result["best_confidence"] = best.confidence
    result["best_match_type"] = best.match_type

    # High confidence threshold
    if best.confidence >= 0.7:
        result["high_confidence"] = True

    # Check if extractor found something
    ex = extractor.extract_all(channel_name)
    if ex.get("competitors"):
        result["extractor_would_match"] = True

    return result


def main():
    """Run comprehensive matcher analysis."""
    with app.app_context():
        print("=" * 80)
        print("COMPREHENSIVE REVERSE EVENT MATCHER ANALYSIS")
        print("=" * 80)

        # Initialize services
        matcher = get_reverse_matcher()
        extractor = PPVEventExtractor()

        print("\nLoading calendar events...")
        num_events = matcher.load_events_for_date_range(days_ahead=14, days_back=21)

        stats = matcher.get_stats()
        print(f"\nCalendar Coverage:")
        print(f"  Events loaded: {stats['events_loaded']}")
        print(f"  Date range: {stats['date_range']}")
        print(f"  Teams indexed: {stats['team_index_size']}")
        print(f"  Leagues: {stats['league_index_size']}")

        # Get all PPV channels
        all_ppv = Channel.query.filter_by(is_ppv=True, is_active=True, is_visible=True).all()
        print(f"\nTotal PPV channels: {len(all_ppv)}")

        # Separate linked vs unlinked
        linked_channel_ids = set(row[0] for row in db.session.query(EventChannelLink.channel_id).all())
        unlinked_channels = [ch for ch in all_ppv if ch.id not in linked_channel_ids]
        linked_channels = [ch for ch in all_ppv if ch.id in linked_channel_ids]

        print(f"Channels with existing event links: {len(linked_channels)}")
        print(f"Channels without event links: {len(unlinked_channels)}")

        # Filter to channels that failed extraction
        failed_extraction = []
        for ch in unlinked_channels:
            ex = extractor.extract_all(ch.name)
            if not ex.get("competitors") and not ex.get("is_placeholder"):
                failed_extraction.append(ch)

        print(f"Channels that failed extraction: {len(failed_extraction)}")

        # Test ALL failed extraction channels (or sample if too many)
        test_limit = 500  # Test up to 500 channels
        test_channels = failed_extraction[:test_limit] if len(failed_extraction) > test_limit else failed_extraction

        print(f"\nTesting {len(test_channels)} channels with reverse matcher...")
        print("-" * 80)

        # Track results
        matches_found = 0
        high_confidence_matches = 0
        failure_categories = Counter()
        confidence_distribution = []
        match_type_distribution = Counter()

        # Detailed failure examples
        failure_examples = defaultdict(list)

        for i, ch in enumerate(test_channels, 1):
            if i % 100 == 0:
                print(f"Progress: {i}/{len(test_channels)} ({i/len(test_channels)*100:.1f}%)")

            matches = matcher.find_matches(ch.name, max_results=3, min_confidence=0.3)
            quality = analyze_match_quality(ch.name, matches, extractor)

            if quality["has_match"]:
                matches_found += 1
                confidence_distribution.append(quality["best_confidence"])
                match_type_distribution[quality["best_match_type"]] += 1

                if quality["high_confidence"]:
                    high_confidence_matches += 1
            else:
                # Categorize failure
                ex = extractor.extract_all(ch.name)
                failure_type = categorize_failure(ch.name, ex)
                failure_categories[failure_type] += 1

                # Save example if we don't have many yet
                if len(failure_examples[failure_type]) < 5:
                    failure_examples[failure_type].append(ch.name)

        # Print comprehensive results
        print("\n" + "=" * 80)
        print("RESULTS")
        print("=" * 80)

        print(f"\nOverall Hit Rate:")
        print(f"  Channels tested: {len(test_channels)}")
        print(f"  Matches found: {matches_found} ({matches_found/len(test_channels)*100:.1f}%)")
        print(
            f"  High confidence (>=0.7): {high_confidence_matches} ({high_confidence_matches/len(test_channels)*100:.1f}%)"
        )

        if confidence_distribution:
            print(f"\nConfidence Distribution:")
            print(f"  Average: {sum(confidence_distribution)/len(confidence_distribution):.2f}")
            print(f"  >= 0.9: {len([c for c in confidence_distribution if c >= 0.9])}")
            print(f"  0.7-0.89: {len([c for c in confidence_distribution if 0.7 <= c < 0.9])}")
            print(f"  0.5-0.69: {len([c for c in confidence_distribution if 0.5 <= c < 0.7])}")
            print(f"  0.3-0.49: {len([c for c in confidence_distribution if 0.3 <= c < 0.5])}")

        if match_type_distribution:
            print(f"\nMatch Type Distribution:")
            for match_type, count in match_type_distribution.most_common():
                print(f"  {match_type}: {count}")

        # Failure analysis
        failures = len(test_channels) - matches_found
        print(f"\n" + "=" * 80)
        print(f"FAILURE ANALYSIS ({failures} failures)")
        print("=" * 80)

        for failure_type, count in failure_categories.most_common():
            pct = count / failures * 100 if failures > 0 else 0
            print(f"\n{failure_type}: {count} ({pct:.1f}%)")
            if failure_examples[failure_type]:
                print(f"  Examples:")
                for ex in failure_examples[failure_type][:3]:
                    print(f"    - {ex[:70]}...")

        # Recommendations
        print(f"\n" + "=" * 80)
        print("RECOMMENDATIONS")
        print("=" * 80)

        print("\nHigh Priority Improvements:")

        # Check if generic channels are a problem
        generic_count = failure_categories[FailureType.GENERIC_CHANNEL]
        if generic_count > 10:
            print(f"\n1. Generic Channel Names ({generic_count} failures, {generic_count/failures*100:.1f}%)")
            print("   - These channels have no event info in the name")
            print("   - Recommendation: Skip these or use schedule-based matching")

        # Check college sports
        college_count = failure_categories[FailureType.COLLEGE_SPORTS]
        if college_count > 10:
            print(f"\n2. College Sports ({college_count} failures, {college_count/failures*100:.1f}%)")
            print("   - NCAA events not well covered in TheSportsDB")
            print("   - Recommendation: Add NCAA-specific calendar source")

        # Check minor leagues
        minor_count = failure_categories[FailureType.MINOR_LEAGUE]
        if minor_count > 10:
            print(f"\n3. Minor Leagues ({minor_count} failures, {minor_count/failures*100:.1f}%)")
            print("   - ECHL, AHL, minor soccer leagues")
            print("   - Recommendation: Extend calendar coverage or use fuzzy team matching")

        # Check combat sports
        combat_count = failure_categories[FailureType.COMBAT_SPORTS]
        if combat_count > 10:
            print(f"\n4. Combat Sports ({combat_count} failures, {combat_count/failures*100:.1f}%)")
            print("   - Boxing/MMA with fighter names instead of team names")
            print("   - Recommendation: Add fighter name index or boxing-specific source")

        # Check individual sports
        individual_count = failure_categories[FailureType.INDIVIDUAL_SPORTS]
        if individual_count > 10:
            print(f"\n5. Individual Sports ({individual_count} failures, {individual_count/failures*100:.1f}%)")
            print("   - Tennis, golf, etc with person names")
            print("   - Recommendation: Build player name index from calendar")

        print(f"\nNext Steps:")
        print(f"  1. Review failure examples above")
        print(f"  2. Decide which categories to prioritize")
        print(f"  3. Implement targeted improvements")
        print(f"  4. Re-test and measure improvement")


if __name__ == "__main__":
    main()
