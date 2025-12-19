#!/usr/bin/env python3
"""
Test tag extraction logic
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services.tag_service import TagService


def test_tag_extraction():
    """Test tag extraction with sample data"""

    print("Testing Tag Extraction Service")
    print("=" * 60)

    # Create mock tag rules
    class MockRule:
        def __init__(self, pattern, pattern_type, tag_name, source, remove_from_name, priority):
            self.pattern = pattern
            self.pattern_type = pattern_type
            self.tag_name = tag_name
            self.source = source
            self.remove_from_name = remove_from_name
            self.priority = priority
            self.enabled = True

    # Sample rules matching the default rules
    rules = [
        MockRule("US|", "prefix", "US", "both", True, 10),
        MockRule(r"^US:\s*", "regex", "US", "channel_name", True, 10),
        MockRule(r"^GO:\s*", "regex", "GO", "channel_name", True, 10),
        MockRule("PRIME:", "prefix", "PRIME", "both", True, 15),
        MockRule("ᵁᴴᴰ", "contains", "UHD", "both", True, 17),
        MockRule("ᴴᴰ", "contains", "HD", "both", True, 18),
        MockRule("ᴴᴰ/ᴿᴬᵂ", "contains", "HD", "both", True, 18),
        MockRule("ᴿᴬᵂ", "contains", "RAW", "both", True, 20),
        MockRule("⁶⁰ᶠᵖˢ", "contains", "60FPS", "both", True, 20),
        MockRule(r"\b4K\b", "regex", "4K", "both", True, 20),
        MockRule(r"\b3840P?\b", "regex", "4K", "both", True, 20),
        MockRule(r"\b2160P?\b", "regex", "4K", "both", True, 20),
        MockRule(r"\b1080P?\b", "regex", "FHD", "both", True, 20),
        MockRule(r"\bHD\b", "regex", "HD", "both", True, 22),
        MockRule("NEWS", "contains", "NEWS", "category_name", False, 30),
        MockRule("SPORT", "contains", "SPORTS", "category_name", False, 30),
        MockRule(r"\[([^\]]+)\]", "regex", "__LOCATION__", "channel_name", True, 85),
        MockRule(r"\(([^\)]+)\)", "regex", "__CALLSIGN__", "channel_name", True, 86),
    ]

    # Test cases
    test_cases = [
        {
            "channel_name": "PRIME: SHADES OF BLACK ᴿᴬᵂ",
            "category_name": "US| PRIME ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "PRIME", "RAW", "60FPS"},
            "expected_name": "SHADES OF BLACK",
        },
        {
            "channel_name": "US| CNN HD",
            "category_name": "US| NEWS",
            "expected_tags": {"US", "HD", "NEWS"},
            "expected_name": "CNN",
        },
        {
            "channel_name": "BBC ONE 4K",
            "category_name": "UK| ENTERTAINMENT",
            "expected_tags": {"4K"},
            "expected_name": "BBC ONE",
        },
        {"channel_name": "HBO", "category_name": "MOVIES", "expected_tags": set(), "expected_name": "HBO"},
        # New test cases from user examples
        {
            "channel_name": "US: DISCOVERY WEST HD",
            "category_name": "US| ENTERTAINMENT ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "HD", "RAW", "60FPS"},
            "expected_name": "DISCOVERY WEST",
        },
        {
            "channel_name": "US: FASHION ONE ᵁᴴᴰ 3840P",
            "category_name": "US| ENTERTAINMENT ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "UHD", "4K", "HD", "RAW", "60FPS"},
            "expected_name": "FASHION ONE",
        },
        {
            "channel_name": "US: GREAT AMERICAN COUNTRY 4K",
            "category_name": "US| ENTERTAINMENT ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "4K", "HD", "RAW", "60FPS"},
            "expected_name": "GREAT AMERICAN COUNTRY",
        },
        {
            "channel_name": "GO: YU-GI-OH!",
            "category_name": "US| DIREC TV ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "GO", "RAW", "60FPS"},
            "expected_name": "YU-GI-OH!",
        },
        {
            "channel_name": "US: TELEMUNDO 51 MIAMI (WSCV)",
            "category_name": "US| ENTERTAINMENT ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "HD", "RAW", "60FPS", "WSCV"},
            "expected_name": "TELEMUNDO 51 MIAMI WSCV",
        },
        {
            "channel_name": "US: TNT EAST 4K",
            "category_name": "US| ENTERTAINMENT ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "4K", "HD", "RAW", "60FPS"},
            "expected_name": "TNT EAST",
        },
        {
            "channel_name": "US: SPECTRUM NEWS 1 RALEIGH ᴴᴰ",
            "category_name": "US| SPECTRUM NETWORK ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "HD", "RAW", "60FPS"},
            "expected_name": "SPECTRUM NEWS 1 RALEIGH",
        },
        {
            "channel_name": "US: TELEMUNDO (KNSO) FRESNO ᴴᴰ",
            "category_name": "US| TELEMUNDO NETWORK ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "HD", "RAW", "60FPS", "KNSO"},
            "expected_name": "TELEMUNDO KNSO FRESNO",
        },
        {
            "channel_name": "US: CBS HARTFORD (WFSB)",
            "category_name": "US| NEWS ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "NEWS", "HD", "RAW", "60FPS", "WFSB"},
            "expected_name": "CBS HARTFORD WFSB",
        },
        {
            "channel_name": "US: CBS 11 DALLAS TX (KTVT) HD",
            "category_name": "US| NEWS ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "NEWS", "HD", "RAW", "60FPS", "KTVT"},
            "expected_name": "CBS 11 DALLAS TX KTVT",
        },
        {
            "channel_name": "US: FOX NET [TWIN FALLS ID]",
            "category_name": "US| FOX ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "HD", "RAW", "60FPS", "TWIN_FALLS_ID"},
            "expected_name": "FOX NET TWIN FALLS ID",
        },
        {
            "channel_name": "US: FOX (KABB) SAN ANTONIO HD",
            "category_name": "US| FOX ᴴᴰ/ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "expected_tags": {"US", "HD", "RAW", "60FPS", "KABB"},
            "expected_name": "FOX KABB SAN ANTONIO",
        },
    ]

    print("\nRunning test cases...\n")

    passed = 0
    failed = 0

    for i, test in enumerate(test_cases, 1):
        print(f"Test Case {i}:")
        print(f"  Channel: {test['channel_name']}")
        print(f"  Category: {test['category_name']}")

        tags, cleaned_name = TagService.extract_tags(test["channel_name"], test["category_name"], rules)

        print(f"  Extracted Tags: {tags}")
        print(f"  Cleaned Name: {cleaned_name}")
        print(f"  Expected Tags: {test['expected_tags']}")
        print(f"  Expected Name: {test['expected_name']}")

        tags_match = tags == test["expected_tags"]
        name_match = cleaned_name == test["expected_name"]

        if tags_match and name_match:
            print("  ✓ PASSED")
            passed += 1
        else:
            print("  ✗ FAILED")
            if not tags_match:
                print(f"    Tags mismatch: got {tags}, expected {test['expected_tags']}")
            if not name_match:
                print(f"    Name mismatch: got '{cleaned_name}', expected '{test['expected_name']}'")
            failed += 1

        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


def test_tag_normalization():
    """Test tag name normalization"""
    print("\nTesting Tag Normalization")
    print("=" * 60)

    test_cases = [
        ("ᴿᴬᵂ", "RAW"),
        ("⁶⁰ᶠᵖˢ", "60FPS"),
        ("US", "US"),
        ("prime video", "PRIME_VIDEO"),
        ("4K HDR", "4K_HDR"),
    ]

    passed = 0
    failed = 0

    for input_tag, expected in test_cases:
        result = TagService.normalize_tag_name(input_tag)
        print(f"  '{input_tag}' -> '{result}' (expected: '{expected}')")

        if result == expected:
            print("  ✓ PASSED")
            passed += 1
        else:
            print("  ✗ FAILED")
            failed += 1
        print()

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return failed == 0


if __name__ == "__main__":
    extraction_ok = test_tag_extraction()
    normalization_ok = test_tag_normalization()

    if extraction_ok and normalization_ok:
        print("\n✓ All tests passed!")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed!")
        sys.exit(1)
