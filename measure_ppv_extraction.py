#!/usr/bin/env python3
"""
Measure PPV event extraction using the PPVEventExtractor service.
Shows extraction success rates and API call costs with smart date inference.
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path

from services.ppv_event_extractor import PPVEventExtractor


def load_and_measure_ppv():
    """Load PPV.list and measure extraction results with smart date inference."""
    ppv_file = Path("/home/benklop/repos/iptv-proxy-v2/PPV.list")

    if not ppv_file.exists():
        print(f"❌ PPV.list not found at {ppv_file}")
        return

    # Use a consistent "today" date for reproducible results
    reference_date = datetime(2026, 1, 2, 12, 0)  # Jan 2, 2026, noon
    extractor = PPVEventExtractor(current_date=reference_date)

    results = {
        "total_channels": 0,
        "placeholders_filtered": 0,
        "inactive_channels": 0,
        "far_future_dates": 0,
        "with_competitors": [],
        "with_date": [],
        "with_weekday": [],
        "with_time_only": [],
        "no_extraction": [],
        "unique_dates": set(),
        "competitor_pairs": defaultdict(int),
        "inference_methods": defaultdict(int),
    }

    print("Loading PPV.list and extracting event data with smart date inference...")
    with open(ppv_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue

            parts = line.split("|")
            if len(parts) < 3:
                continue

            results["total_channels"] += 1
            channel_name = parts[2]

            # Try extraction with smart inference
            extraction = extractor.extract_all(channel_name)

            if extraction["is_placeholder"]:
                results["placeholders_filtered"] += 1
                continue

            if extraction["is_inactive"]:
                results["inactive_channels"] += 1
                continue

            # Track what was extracted
            if extraction["competitors"]:
                results["with_competitors"].append(
                    {
                        "channel": channel_name,
                        "competitors": extraction["competitors"],
                    }
                )
                results["competitor_pairs"][extraction["competitors"]] += 1

            if extraction["inferred_how"] == "date_too_far_future":
                results["far_future_dates"] += 1
                continue

            if extraction["date"]:
                results["with_date"].append(
                    {
                        "channel": channel_name,
                        "date": extraction["date"],
                        "how": extraction["inferred_how"],
                    }
                )
                results["unique_dates"].add(extraction["date"].strftime("%Y-%m-%d"))
                results["inference_methods"][extraction["inferred_how"]] += 1

            if extraction["time_only"]:
                results["with_time_only"].append(
                    {
                        "channel": channel_name,
                        "time": extraction["time_only"],
                    }
                )

            if extraction["weekday"]:
                results["with_weekday"].append(
                    {
                        "channel": channel_name,
                        "weekday": extraction["weekday"],
                    }
                )

            # Track failures (channels with no extraction at all)
            if (
                not extraction["competitors"]
                and not extraction["date"]
                and not extraction["weekday"]
                and not extraction["time_only"]
            ):
                results["no_extraction"].append(channel_name)

    # Print summary
    print("\n" + "=" * 70)
    print("PPV EXTRACTION MEASUREMENT RESULTS (WITH SMART DATE INFERENCE)")
    print("=" * 70)

    print(f"\n📊 Total Channels: {results['total_channels']:,}")
    print(
        f"🗑️  Placeholders (NO EVENT): {results['placeholders_filtered']:,} ({results['placeholders_filtered']/results['total_channels']*100:.1f}%)"
    )
    print(
        f"🔌 Inactive channels: {results['inactive_channels']:,} ({results['inactive_channels']/results['total_channels']*100:.1f}%)"
    )
    print(
        f"📅 Far future dates (>1 year): {results['far_future_dates']:,} ({results['far_future_dates']/results['total_channels']*100:.1f}%)"
    )

    # Calculate active channels (not placeholders, not inactive)
    active = (
        results["total_channels"]
        - results["placeholders_filtered"]
        - results["inactive_channels"]
        - results["far_future_dates"]
    )
    print(f"✅ Actively broadcasting: {active:,} ({active/results['total_channels']*100:.1f}%)")

    matchable = active
    with_comp = len(results["with_competitors"])
    with_date = len(results["with_date"])
    with_weekday = len(results["with_weekday"])
    with_time = len(results["with_time_only"])

    total_with_date_info = len(
        set(
            [c["channel"] for c in results["with_date"]]
            + [c["channel"] for c in results["with_weekday"]]
            + [c["channel"] for c in results["with_time_only"]]
        )
    )

    print(f"\n📋 Matchable Channels (non-placeholder): {matchable:,}")
    print(f"\n✅ Extraction Results:")
    print(f"   With competitors: {with_comp:,} ({with_comp/matchable*100:.1f}%)")
    print(f"   With date info:   {total_with_date_info:,} ({total_with_date_info/matchable*100:.1f}%)")
    print(f"     - Full dates:   {with_date:,}")
    print(f"     - Weekday:      {with_weekday:,}")
    print(f"     - Time-only:    {with_time:,}")
    print(f"❌ No extraction:    {len(results['no_extraction']):,} ({len(results['no_extraction'])/matchable*100:.1f}%)")

    print(f"\n📅 Date Inference Methods:")
    for method, count in sorted(results["inference_methods"].items(), key=lambda x: x[1], reverse=True):
        print(f"   {method:30} {count:5,} channels ({count/with_date*100:5.1f}%)")

    print(f"\n📅 Unique Dates Found: {len(results['unique_dates'])}")
    if results["unique_dates"]:
        sorted_dates = sorted(results["unique_dates"])
        print(f"   First: {sorted_dates[0]}")
        print(f"   Last:  {sorted_dates[-1]}")

    # Show top extracted competitors
    print(f"\n🏆 Top 15 Extracted Competitor Pairs:")
    for (comp1, comp2), count in sorted(results["competitor_pairs"].items(), key=lambda x: x[1], reverse=True)[:15]:
        print(f"   {comp1:30} vs {comp2:30} [{count:4} channels]")

    # Show examples of successful extractions
    print(f"\n📌 Examples of Extracted Events (first 10):")
    for item in results["with_date"][:10]:
        date = item["date"].strftime("%Y-%m-%d %H:%M")
        how = item["how"]
        print(f"   {date} ({how:20}): {item['channel'][:55]}")

    print(f"\n📌 Examples of Weekday-only Extractions (first 5):")
    for item in results["with_weekday"][:5]:
        print(f"   {item['weekday']:3}: {item['channel'][:65]}")

    print(f"\n📌 Examples of Time-only Extractions (first 5):")
    for item in results["with_time_only"][:5]:
        h, m, ap = item["time"]
        time_str = f"{h}:{m:02d} {ap if ap else ''}"
        print(f"   {time_str:15}: {item['channel'][:55]}")

    # Show examples of failed extractions
    if results["no_extraction"]:
        print(f"\n⚠️  Examples of Failed Extractions (first 10):")
        for channel in results["no_extraction"][:10]:
            print(f"   {channel[:75]}")

    print("\n" + "=" * 70)
    print("\n🎯 COVERAGE ANALYSIS:")
    channels_with_competitors_and_date = len(
        [
            c
            for c in results["with_competitors"]
            if any(c["channel"] == d["channel"] for d in results["with_date"])
            or any(c["channel"] == w["channel"] for w in results["with_weekday"])
            or any(c["channel"] == t["channel"] for t in results["with_time_only"])
        ]
    )

    print(f"   Channels with BOTH competitors AND date info: {channels_with_competitors_and_date:,}")
    print(f"   → These can be matched directly to TheSportsDB")
    print(f"   → Confidence: 0.90+ (high)")

    potential_tier1 = with_comp
    print(f"\n📊 TIER 1 (Direct Search) Potential:")
    print(f"   Candidates: {potential_tier1:,} channels with team names")
    print(f"   API Calls: ~{potential_tier1:,} (1 per candidate)")
    print(f"   Verdict: {'✅ FEASIBLE' if potential_tier1 < 10000 else '⚠️  MODERATE'}")

    potential_tier2 = total_with_date_info
    print(f"\n📊 TIER 2 (Calendar Browse) Potential:")
    print(f"   Candidates with date info: {potential_tier2:,} channels")
    print(f"   Unique dates: {len(results['unique_dates']):,}")
    if results["unique_dates"]:
        print(f"   HTTP calls (browse_calendar): ~{len(results['unique_dates']):,}")
        print(f"   Verdict: {'✅ HIGHLY EFFICIENT' if len(results['unique_dates']) < 100 else '⚠️  CHECK DATES'}")

    overall_coverage = with_comp + potential_tier2
    print(f"\n💡 OVERALL COVERAGE:")
    print(f"   Extractable channels: {overall_coverage:,} ({overall_coverage/matchable*100:.1f}%)")
    print(f"   Expected API calls: ~{potential_tier1 + len(results['unique_dates']):,}")
    print(f"   Cost per matchable channel: {(potential_tier1 + len(results['unique_dates']))/matchable:.2f} API calls")

    print("\n" + "=" * 70)

    return results


if __name__ == "__main__":
    results = load_and_measure_ppv()
