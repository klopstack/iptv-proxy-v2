#!/usr/bin/env python3
"""
Deep dive analysis of matcher failures to identify fixable patterns.

Focuses on the "no_sports_keywords" category which represents 44.6% of failures
but likely has extractable sports content.
"""

import os
import re
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


def has_sports_indicators(name: str) -> bool:
    """Check if channel name has sports-related content."""
    name_lower = name.lower()
    indicators = [
        " vs ",
        " v ",
        " at ",
        " @ ",
        "nba",
        "nfl",
        "nhl",
        "mlb",
        "mls",
        "ufc",
        "boxing",
        "premier league",
        "bundesliga",
        "la liga",
        "serie a",
        "champions league",
        "tennis",
        "golf",
        "formula",
        "race",
        "fight",
        "match",
        "game",
        "tournament",
    ]
    return any(ind in name_lower for ind in indicators)


def has_team_like_words(name: str) -> bool:
    """Check if name contains words that could be team names."""
    # Remove common prefixes/metadata
    clean = re.sub(r"^(US|UK|CA|AU)[\s:|\-]+", "", name, flags=re.IGNORECASE)
    clean = re.sub(r"\(.*?\)", "", clean)  # Remove parentheses
    clean = re.sub(r"\[.*?\]", "", clean)  # Remove brackets
    clean = re.sub(r"start:.*", "", clean, flags=re.IGNORECASE)  # Remove timestamps

    # Look for capitalized words that could be team names (excluding common words)
    words = re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b", clean)

    # Filter out common metadata words
    metadata = {
        "Premier",
        "League",
        "Away",
        "Home",
        "Live",
        "Event",
        "Network",
        "Sports",
        "Channel",
        "Redzone",
        "Plus",
    }
    potential_teams = [w for w in words if w not in metadata and len(w) > 3]

    return len(potential_teams) >= 2


def analyze_no_sports_keywords_failures():
    """Analyze channels that have sports content but didn't match."""
    with app.app_context():
        print("=" * 80)
        print("DEEP DIVE: 'NO SPORTS KEYWORDS' FAILURES")
        print("=" * 80)

        # Initialize
        matcher = get_reverse_matcher()
        extractor = PPVEventExtractor()

        matcher.load_events_for_date_range(days_ahead=14, days_back=21)

        # Get failed extraction channels
        all_ppv = Channel.query.filter_by(is_ppv=True, is_active=True, is_visible=True).all()
        linked_ids = set(row[0] for row in db.session.query(EventChannelLink.channel_id).all())
        unlinked = [ch for ch in all_ppv if ch.id not in linked_ids]

        failed_extraction = []
        for ch in unlinked:
            ex = extractor.extract_all(ch.name)
            if not ex.get("competitors") and not ex.get("is_placeholder"):
                failed_extraction.append(ch)

        # Test and find "no sports keywords" that didn't match
        print(f"\nTesting {len(failed_extraction[:500])} channels...")

        no_match_with_sports = []
        for ch in failed_extraction[:500]:
            matches = matcher.find_matches(ch.name, max_results=1, min_confidence=0.3)
            if not matches and has_sports_indicators(ch.name):
                no_match_with_sports.append(ch)

        print(f"\nChannels with sports indicators but no match: {len(no_match_with_sports)}")

        # Analyze patterns
        print("\n" + "=" * 80)
        print("PATTERN ANALYSIS")
        print("=" * 80)

        # Group by patterns
        patterns = {
            "last_names_only": [],
            "abbreviated_teams": [],
            "foreign_teams": [],
            "fighter_names": [],
            "tournament_format": [],
            "date_time_heavy": [],
            "network_branded": [],
            "unclear": [],
        }

        for ch in no_match_with_sports:
            name = ch.name
            name_lower = name.lower()

            # Classify
            if " vs " in name_lower and not any(word[0].isupper() for word in name.split()):
                patterns["last_names_only"].append(name)
            elif re.search(r"\b[A-Z]{2,5}\b", name) and (" at " in name_lower or " vs " in name_lower):
                patterns["abbreviated_teams"].append(name)
            elif any(x in name_lower for x in ["danny garcia", "daniel gonzalez", "jake paul", "anthony joshua"]):
                patterns["fighter_names"].append(name)
            elif any(x in name_lower for x in ["tournament", "championship", "cup", "open"]):
                patterns["tournament_format"].append(name)
            elif re.search(r"\d{1,2}[/\-:]\d{1,2}", name) and len(re.findall(r"\d{1,2}[/\-:]\d{1,2}", name)) > 1:
                patterns["date_time_heavy"].append(name)
            elif any(x in name_lower for x in ["nfl network", "nfl redzone", "mlb network", "nba tv"]):
                patterns["network_branded"].append(name)
            elif not has_team_like_words(name):
                patterns["unclear"].append(name)
            else:
                patterns["foreign_teams"].append(name)

        # Print results
        for pattern_name, channels in patterns.items():
            if channels:
                print(f"\n{pattern_name.upper()}: {len(channels)} channels")
                for i, name in enumerate(channels[:5], 1):
                    print(f"  {i}. {name[:75]}...")
                    # Show what matcher sees
                    matches = matcher.find_matches(name, max_results=1, min_confidence=0.2)
                    if matches:
                        print(
                            f"     → Low conf match: {matches[0].event.event_name[:40]} (conf: {matches[0].confidence:.2f})"
                        )
                    else:
                        print(f"     → No matches even at 0.2 threshold")

        # Specific improvement recommendations
        print("\n" + "=" * 80)
        print("SPECIFIC IMPROVEMENT OPPORTUNITIES")
        print("=" * 80)

        last_name_count = len(patterns["last_names_only"])
        if last_name_count > 0:
            print(f"\n1. Last Names Only ({last_name_count} channels)")
            print("   Problem: Channel uses last names but matcher can't find them")
            print("   Examples:")
            for ex in patterns["last_names_only"][:3]:
                print(f"     - {ex}")
            print("   Solution: Enhance last name matching in ReverseEventMatcher")
            print("   - Extract last names more aggressively")
            print("   - Match even if only last names present")

        abbrev_count = len(patterns["abbreviated_teams"])
        if abbrev_count > 0:
            print(f"\n2. Abbreviated Team Names ({abbrev_count} channels)")
            print("   Problem: Teams abbreviated (LAL vs GSW, etc)")
            print("   Examples:")
            for ex in patterns["abbreviated_teams"][:3]:
                print(f"     - {ex}")
            print("   Solution: Build abbreviation index")
            print("   - Map common team abbreviations to full names")
            print("   - E.g., LAL -> Los Angeles Lakers, GSW -> Golden State Warriors")

        fighter_count = len(patterns["fighter_names"])
        if fighter_count > 0:
            print(f"\n3. Fighter Names ({fighter_count} channels)")
            print("   Problem: Boxing/MMA events use person names, not teams")
            print("   Examples:")
            for ex in patterns["fighter_names"][:3]:
                print(f"     - {ex}")
            print("   Solution: Build fighter name index from combat sports events")
            print("   - Extract fighter names from Boxing/MMA events in calendar")
            print("   - Match on 'FirstName LastName' patterns")

        network_count = len(patterns["network_branded"])
        if network_count > 0:
            print(f"\n4. Network-Branded Channels ({network_count} channels)")
            print("   Problem: Generic network names without specific event info")
            print("   Examples:")
            for ex in patterns["network_branded"][:3]:
                print(f"     - {ex}")
            print("   Solution: Skip or use schedule-based matching")
            print("   - These channels need EPG schedule data to identify events")
            print("   - Not suitable for name-based matching")

        # Test specific problematic examples
        print("\n" + "=" * 80)
        print("TEST: SPECIFIC PROBLEMATIC EXAMPLES")
        print("=" * 80)

        test_cases = [
            "NFL  | 07 - 1PM Titans at Jaguars",
            "LIVE EVENT 26 -Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK / 6PM ET / 3PM PT",
            "NBA: PHOENIX SUNS",
            "US: DALLAS STARS",
            "AU (STAN 29) | Paolini v Bencic: Group C _ United Cup 2025/26",
        ]

        for name in test_cases:
            print(f"\nChannel: {name}")

            # Try different confidence levels
            for conf in [0.7, 0.5, 0.3, 0.2, 0.1]:
                matches = matcher.find_matches(name, max_results=1, min_confidence=conf)
                if matches:
                    m = matches[0]
                    print(
                        f"  @ conf {conf}: {m.event.event_name[:40]} (actual: {m.confidence:.2f}, type: {m.match_type})"
                    )
                    print(f"            Matched terms: {m.matched_terms}")
                    break
            else:
                print(f"  No matches at any confidence level")

            # Show extraction result
            ex = extractor.extract_all(name)
            if ex.get("competitors"):
                print(f"  Extractor found: {ex['competitors']}")


if __name__ == "__main__":
    analyze_no_sports_keywords_failures()
