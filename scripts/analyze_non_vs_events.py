#!/usr/bin/env python3
"""
Analyze unmatched PPV channels to identify non-vs events.

Categorizes unmatched channels by likely event type to understand
what they actually are. This helps identify which channels should
be matched to vs events vs other content types.

Categories:
- Tournament/League: Tournaments, leagues, cups (e.g., "World Cup", "Premier League")
- Highlight/Recap: Highlights, recaps, reviews, replays
- Documentary: Documentaries, specials, features
- Training/Practice: Training sessions, practices, friendlies
- Show/Program: Talk shows, news, magazines
- Series/Season: Series events, seasons, rounds
- Player Profile: Player/athlete focused content
- Other: Everything else (potential vs events)
"""

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel

# Patterns for identifying non-vs event types
NON_VS_PATTERNS = {
    "tournament": [
        r"\b(world\s+cup|cup\s+\d+|championship|tournament|league|playoff|finals?|semi[- ]?finals?|round\s+\d+)\b",
        r"\b(open|masters|invitational|qualif(ier|ying)?|knockout|bracket)\b",
        r"\b(season\s+\d+|series\s+\d+|week\s+\d+|day\s+\d+)\b",
    ],
    "highlight": [
        r"\b(highlight|recap|review|roundup|summary|replay|rerun|best\s+of|goals?|moments?)\b",
        r"\b(extended\s+highlights?|full\s+match|match\s+highlights?)\b",
    ],
    "documentary": [
        r"\b(documentary|special|feature|biography|profile|story|behind[- ]?the[- ]?scenes)\b",
        r"\b(30\s+for\s+30|history\s+of|untold|legends?|icons?|heroes?)\b",
    ],
    "training": [
        r"\b(training|practice|practice\s+session|friendly|friendly\s+match|preseason|warm[- ]?up)\b",
        r"\b(open\s+practice|media\s+day|press\s+conference)\b",
    ],
    "show": [
        r"\b(talk\s+show|news|magazine|interview|analysis|podcast|radio|show|program|live\s+coverage)\b",
        r"\b(pre[- ]?game|post[- ]?game|game\s+day|preview|kickoff|spotlight)\b",
    ],
    "series": [
        r"\b(episode|ep\.\s+\d+|season\s+\d+\s+episode|series|chapter|part\s+\d+)\b",
        r"\b(game\s+\d+|match\s+\d+|day\s+\d+|week\s+\d+|round\s+\d+)\b",
    ],
    "player": [
        r"\b(player\s+profile|athlete\s+profile|focus\s+on|featuring|starring|interview\s+with)\b",
        r"\b(all\s+access|locker\s+room|exclusive|behind[- ]?the[- ]?scenes)\b",
    ],
}


def is_placeholder_channel(channel_name: str) -> bool:
    """
    Check if a channel name is clearly a placeholder/non-event.

    Returns True if channel is:
    - A section header (starts with #)
    - Explicitly marked as no event streaming
    - Contains only generic/empty content markers
    """
    name = channel_name.strip()

    # Section headers with ###
    if name.startswith("#"):
        return True

    # Explicit no event markers
    if re.search(r"\bNO\s+EVENT\s+STREAMING\b", name, re.IGNORECASE):
        return True

    # Generic "PPV X" or "EVENT X" with no other info
    if re.match(r"^[A-Za-z0-9\s\-]*(?:PPV|Event|Game|Channel|Match)\s+\d+\s*$", name, re.IGNORECASE):
        return True

    return False


def get_base_name(channel_name: str) -> str:
    """
    Get the base name by removing trailing numbers.

    Examples:
    - "UK: SKY SPORTS+ EVENT 1" -> "UK: SKY SPORTS+ EVENT"
    - "PPV Event 42" -> "PPV Event"
    - "Game 5 (Fanatiz)" -> "Game (Fanatiz)"
    - "DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE" -> "DAZN PPV - NO EVENT STREAMING - | 8K EXCLUSIVE"
    """
    # Remove numbers that appear after non-numeric content
    # Match: any content, then optional whitespace, then a single number or small sequence, then optional whitespace + junk
    return re.sub(r"\s+\d+(?:\s+[-|]|$)", "", channel_name.strip())


def categorize_channel(channel_name: str) -> tuple[str, str]:
    """
    Categorize a channel name by likely event type.

    Returns: (category, matched_pattern)
    """
    name_lower = channel_name.lower()

    for category, patterns in NON_VS_PATTERNS.items():
        for pattern in patterns:
            match = re.search(pattern, name_lower, re.IGNORECASE)
            if match:
                return (category, match.group(0))

    return ("other", "")


def analyze_non_vs_events(account_id=None, show_examples=True):
    """Analyze unmatched channels to identify non-vs events."""

    # Get unmatched PPV channels
    query = Channel.query.filter(Channel.is_ppv == True)  # noqa: E712
    if account_id:
        query = query.filter_by(account_id=account_id)

    channels = query.all()

    # Filter to unmatched
    unmatched = []
    for channel in channels:
        if not channel.event_links:
            unmatched.append(channel)

    if not unmatched:
        print("No unmatched channels found.")
        return

    print(f"\nAnalyzing {len(unmatched)} unmatched PPV channels\n")
    print("=" * 120)

    # First, identify placeholder patterns (same base name with different numbers)
    placeholder_channels = set()
    base_name_groups = defaultdict(list)
    for channel in unmatched:
        # Skip channels that are explicitly placeholders
        if is_placeholder_channel(channel.name):
            placeholder_channels.add(channel)
            continue

        base = get_base_name(channel.name)
        base_name_groups[base].append(channel)

    # Find groups with 2+ channels with same base name (lowered threshold)
    for base, group in base_name_groups.items():
        if len(group) >= 2:
            placeholder_channels.update(group)

    # Categorize all channels
    categories = defaultdict(list)

    for channel in unmatched:
        # Check if it's a placeholder first
        if channel in placeholder_channels:
            base = get_base_name(channel.name)
            categories["placeholder"].append((channel, base))
            continue

        # Otherwise categorize by pattern
        category, pattern = categorize_channel(channel.name)
        categories[category].append((channel, pattern))

    # Sort by frequency
    sorted_categories = sorted(categories.items(), key=lambda x: len(x[1]), reverse=True)

    # Display results
    for category, items in sorted_categories:
        pct = len(items) / len(unmatched) * 100
        print(f"\n{category.upper()} ({len(items)} channels, {pct:.1f}%)")
        print("-" * 120)

        if show_examples and items:
            # Show up to 10 examples
            for channel, pattern in items[:10]:
                print(f"  [{channel.stream_id}] {channel.name}")
                if pattern:
                    print(f"        → {pattern}")

            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")

    # Summary
    print("\n" + "=" * 120)
    print("SUMMARY")
    print("-" * 120)

    likely_vs_events = len(categories.get("other", []))
    likely_non_vs = len(unmatched) - likely_vs_events
    placeholder_count = len(categories.get("placeholder", []))

    print(
        f"Placeholder channels (generic + numbered):  {placeholder_count:5d} ({placeholder_count / len(unmatched) * 100:5.1f}%)"
    )
    print(
        f"Likely vs events (no match found):          {likely_vs_events:5d} ({likely_vs_events / len(unmatched) * 100:5.1f}%)"
    )
    print(
        f"Likely non-vs content (identified):         {likely_non_vs:5d} ({likely_non_vs / len(unmatched) * 100:5.1f}%)"
    )
    print()

    # Breakdown of non-vs
    if likely_non_vs > 0:
        print("NON-VS CONTENT BREAKDOWN")
        print("-" * 120)
        for category, items in sorted_categories:
            if category not in ("other", "placeholder"):
                pct = len(items) / likely_non_vs * 100
                print(f"  {category.title():20s}: {len(items):5d} ({pct:5.1f}%)")

    # Recommendations
    print("\n" + "=" * 120)
    print("RECOMMENDATIONS")
    print("-" * 120)

    if placeholder_count > len(unmatched) * 0.1:
        print(f"⚠️  Found {placeholder_count} placeholder/generic numbered channels")
        print("   → These channels have generic names like 'EVENT 1', 'EVENT 2', etc.")
        print("   → Consider filtering these out or investigating their actual content")
        print("   → They typically don't contain specific match information")

    if likely_vs_events > len(unmatched) * 0.5:
        print(f"\n⚠️  {likely_vs_events} channels likely contain vs events but didn't match")
        print("   → These are candidates for improving the matching algorithm")
        print("   → Run: python scripts/show_unmatched_channels.py --reason no-match | head -50")

    if len(categories.get("tournament", [])) > 0:
        print(f"\n🏆 Found {len(categories['tournament'])} tournament/league channels")
        print("   → These may not be individual match events")
        print("   → Consider creating separate PPV categories for tournaments")

    if len(categories.get("highlight", [])) > 0:
        print(f"\n🎬 Found {len(categories['highlight'])} highlight/recap channels")
        print("   → These are post-match content, not live events")
        print("   → Mark as non-PPV or separate category")

    if len(categories.get("documentary", [])) > 0:
        print(f"\n📺 Found {len(categories['documentary'])} documentary/special channels")
        print("   → These are non-sports-event content")
        print("   → Consider filtering out from PPV matching")

    if len(categories.get("show", [])) > 0:
        print(f"\n📻 Found {len(categories['show'])} show/program channels")
        print("   → These are commentary/analysis, not events")
        print("   → Filter from PPV channel set")

    print()


def main():
    parser = argparse.ArgumentParser(description="Analyze unmatched channels to identify non-vs events")
    parser.add_argument("--account-id", type=int, help="Filter by specific account ID")
    parser.add_argument("--no-examples", action="store_true", help="Don't show example channels")

    args = parser.parse_args()

    with app.app_context():
        analyze_non_vs_events(args.account_id, show_examples=not args.no_examples)


if __name__ == "__main__":
    main()
