#!/usr/bin/env python3
"""
Analyze PPV channel names to understand extraction failures.

This script queries the database for PPV channels and examines:
1. Channels with successful matches (have EventChannelLink)
2. Channels with enrichment_status indicating failures
3. Random sample of all PPV channels
4. Test extraction on each to see what's being extracted
"""

import os
import sys
from collections import Counter, defaultdict

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import flask

# Must configure before importing models
db_path = os.path.join(os.path.dirname(__file__), "data", "iptv_proxy.db")
os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

from models import Channel, Event, EventChannelLink, db
from services.ppv_event_extractor import PPVEventExtractor

# Create Flask app
app = flask.Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db.init_app(app)


def analyze_channel_names():
    """Analyze PPV channel names and extraction results."""
    with app.app_context():
        print("=" * 80)
        print("PPV CHANNEL NAME ANALYSIS")
        print("=" * 80)

        # Get all PPV channels
        all_ppv_channels = Channel.query.filter_by(is_ppv=True, is_active=True, is_visible=True).all()

        print(f"\nTotal PPV channels: {len(all_ppv_channels)}")

        # Categorize by enrichment status
        status_counts = Counter([ch.ppv_enrichment_status for ch in all_ppv_channels])
        print("\nEnrichment status breakdown:")
        for status, count in status_counts.most_common():
            print(f"  {status or 'None'}: {count}")

        # Get channels with event links
        channels_with_events = (
            db.session.query(Channel)
            .join(EventChannelLink, Channel.id == EventChannelLink.channel_id)
            .filter(Channel.is_ppv == True)
            .all()
        )
        print(f"\nChannels with event links: {len(channels_with_events)}")

        # Initialize extractor
        extractor = PPVEventExtractor()

        # Analyze different categories
        categories = {
            "matched": [ch for ch in all_ppv_channels if ch.ppv_enrichment_status == "matched"],
            "no_match": [ch for ch in all_ppv_channels if ch.ppv_enrichment_status == "no_match"],
            "pending": [
                ch for ch in all_ppv_channels if not ch.ppv_enrichment_status or ch.ppv_enrichment_status == "pending"
            ],
        }

        print("\n" + "=" * 80)
        print("CATEGORY: SUCCESSFULLY MATCHED CHANNELS")
        print("=" * 80)
        print_channel_samples(categories["matched"][:20], extractor, show_extraction=True)

        print("\n" + "=" * 80)
        print("CATEGORY: CHANNELS THAT FAILED TO MATCH")
        print("=" * 80)
        print_channel_samples(categories["no_match"][:30], extractor, show_extraction=True)

        print("\n" + "=" * 80)
        print("CATEGORY: PENDING/NOT PROCESSED CHANNELS (Sample)")
        print("=" * 80)
        print_channel_samples(categories["pending"][:50], extractor, show_extraction=True)

        # Analyze extraction patterns
        print("\n" + "=" * 80)
        print("EXTRACTION PATTERN ANALYSIS")
        print("=" * 80)

        # Sample 500 random channels for pattern analysis
        import random

        sample_size = min(500, len(all_ppv_channels))
        sample_channels = random.sample(all_ppv_channels, sample_size)

        pattern_stats = {
            "has_competitors": 0,
            "has_date": 0,
            "has_time_only": 0,
            "is_placeholder": 0,
            "is_inactive": 0,
            "no_extraction": 0,
        }

        extraction_failures = defaultdict(list)

        for ch in sample_channels:
            extraction = extractor.extract_all(ch.name)

            if extraction.get("is_placeholder"):
                pattern_stats["is_placeholder"] += 1
            elif extraction.get("is_inactive"):
                pattern_stats["is_inactive"] += 1
            elif extraction.get("competitors"):
                pattern_stats["has_competitors"] += 1
            else:
                pattern_stats["no_extraction"] += 1
                # Categorize why no competitors
                if extraction.get("date"):
                    extraction_failures["has_date_no_competitors"].append(ch.name)
                elif extraction.get("time_only"):
                    extraction_failures["has_time_no_competitors"].append(ch.name)
                else:
                    extraction_failures["no_identifiable_info"].append(ch.name)

            if extraction.get("date"):
                pattern_stats["has_date"] += 1
            if extraction.get("time_only"):
                pattern_stats["has_time_only"] += 1

        print(f"\nPattern statistics (sample of {sample_size} channels):")
        for pattern, count in pattern_stats.items():
            percentage = (count / sample_size) * 100
            print(f"  {pattern}: {count} ({percentage:.1f}%)")

        print("\n" + "=" * 80)
        print("EXTRACTION FAILURE EXAMPLES")
        print("=" * 80)

        for failure_type, channel_names in extraction_failures.items():
            print(f"\n{failure_type.upper()} ({len(channel_names)} channels):")
            for name in channel_names[:15]:  # Show first 15
                print(f"  - {name}")

        # Check for common naming patterns
        print("\n" + "=" * 80)
        print("COMMON NAMING PATTERNS")
        print("=" * 80)
        analyze_naming_patterns(all_ppv_channels)


def print_channel_samples(channels, extractor, show_extraction=False):
    """Print sample of channels with optional extraction details."""
    if not channels:
        print("  (No channels in this category)")
        return

    print(f"\nShowing {len(channels)} channels:")
    for i, ch in enumerate(channels, 1):
        print(f"\n{i}. {ch.name}")
        print(f"   Account: {ch.account_id}, Stream ID: {ch.stream_id}")
        print(f"   Status: {ch.ppv_enrichment_status or 'None'}")

        if show_extraction:
            extraction = extractor.extract_all(ch.name)
            print(f"   Extraction:")
            print(f"     - competitors: {extraction.get('competitors')}")
            print(f"     - date: {extraction.get('date')}")
            print(f"     - time_only: {extraction.get('time_only')}")
            print(f"     - is_placeholder: {extraction.get('is_placeholder')}")
            print(f"     - is_inactive: {extraction.get('is_inactive')}")
            if extraction.get("inferred_how"):
                print(f"     - inferred_how: {extraction.get('inferred_how')}")


def analyze_naming_patterns(channels):
    """Analyze common patterns in channel names."""
    import re

    # Pattern categories
    patterns = {
        "has_parentheses": r"\([^)]+\)",
        "has_brackets": r"\[[^\]]+\]",
        "has_time": r"\d{1,2}:\d{2}",
        "has_vs": r"\bvs\.?\b",
        "has_at": r"\bat\.?\b",
        "has_dash_separator": r"\s+-\s+",
        "starts_with_ppv": r"^PPV\b",
        "starts_with_number": r"^\d+",
        "has_date_month": r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\b",
        "no_event_streaming": r"NO EVENT STREAMING",
    }

    pattern_counts = Counter()
    examples = defaultdict(list)

    for ch in channels:
        name = ch.name
        for pattern_name, pattern_regex in patterns.items():
            if re.search(pattern_regex, name, re.IGNORECASE):
                pattern_counts[pattern_name] += 1
                if len(examples[pattern_name]) < 5:  # Keep first 5 examples
                    examples[pattern_name].append(name)

    print("\nPattern frequency:")
    for pattern, count in pattern_counts.most_common():
        percentage = (count / len(channels)) * 100
        print(f"  {pattern}: {count} ({percentage:.1f}%)")
        print(f"    Examples:")
        for ex in examples[pattern][:3]:
            print(f"      - {ex}")


if __name__ == "__main__":
    analyze_channel_names()
