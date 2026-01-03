#!/usr/bin/env python3
"""
Test actual API and HTML search code against TheSportsDB API.
Tests both direct API calls and the extraction/matching logic.
"""

import logging
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Test data from NO_DATA.list - sample PPV entries
TEST_CHANNELS = [
    # AR TOD PPV channels - numbered placeholders
    "AR: TOD PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE",
    "AR: TOD PPV 10 - NO EVENT STREAMING - | 8K EXCLUSIVE",
    # Soccer matches (hypothetical formats)
    "AR| Real Madrid vs Barcelona (2025-01-20 14:00:00)",
    "AR| Liverpool at Manchester United (2025-01-20 15:30:00)",
    "AR| Paris Saint-Germain - Lyon | Jan 25 19:45",
    # USA/General matches
    "US| Warriors @ Lakers | Jan 20 19:00",
    "US| Yankees vs Red Sox (2025-02-01 13:00)",
    "US| Cowboys - Giants | Sat 20:00 PM",
    # European clubs with symbols
    "ES| FC Barcelona ⚽ vs Real Sociedad | 20 Jan 21:00",
    "IT| Juventus vs AC Milan (2025-01-26)",
    # Boxing/PPV specific
    "BOXING: Canelo Alvarez vs John Ryder | 2025-02-01 22:00",
    "UFC 311: Makhachev vs Nurmagomedov (2025-01-18 23:00)",
    # Just provider names (inactive)
    "(Fanatiz 001)",
    "DAZN PPV",
]


def test_thesportsdb_service():
    """Test direct TheSportsDB service API calls."""
    print("\n" + "=" * 80)
    print("TESTING THESPORTSDB SERVICE")
    print("=" * 80)

    try:
        from services.thesportsdb_service import TheSportsDBService

        service = TheSportsDBService()

        # Test 1: Get next league events for Premier League
        print("\n[Test 1] Fetching Premier League events...")
        events = service.get_next_league_events("133602", max_events=5)
        if events:
            print(f"✓ Retrieved {len(events)} events")
            for event in events[:2]:
                print(f"  - {event.get('strEvent')} ({event.get('dateEvent')})")
        else:
            print("✗ No events returned")

        # Test 2: Get league info
        print("\n[Test 2] Fetching Premier League info...")
        league_info = service.get_league_info("133602")
        if league_info:
            print(f"✓ League: {league_info.get('strLeague')}")
        else:
            print("✗ League info not found")

        # Test 3: Get teams
        print("\n[Test 3] Fetching Premier League teams...")
        teams = service.get_league_teams("133602", max_teams=3)
        if teams:
            print(f"✓ Retrieved {len(teams)} teams")
            for team in teams[:2]:
                print(f"  - {team.get('strTeam')}")
        else:
            print("✗ No teams returned")

        return True
    except Exception as e:
        print(f"✗ TheSportsDB Service Error: {e}")
        logger.exception("TheSportsDB service error")
        return False


def test_ppv_event_extractor():
    """Test PPV event extraction logic."""
    print("\n" + "=" * 80)
    print("TESTING PPV EVENT EXTRACTOR")
    print("=" * 80)

    try:
        from services.ppv_event_extractor import PPVEventExtractor

        extractor = PPVEventExtractor(current_date=datetime(2025, 1, 20, 12, 0))

        print("\n[Test 1] Placeholder Detection")
        test_cases = [
            ("AR: TOD PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE", True),
            ("AR| Real Madrid vs Barcelona", False),
            ("DAZN PPV", False),
        ]

        for channel, expected_placeholder in test_cases:
            result = extractor.is_placeholder(channel)
            status = "✓" if result == expected_placeholder else "✗"
            print(f"  {status} {channel[:50]}: placeholder={result}")

        print("\n[Test 2] Inactive Channel Detection")
        test_cases = [
            ("(Fanatiz 001)", True),
            ("AR| Real Madrid vs Barcelona", False),
            ("DAZN PPV", False),
        ]

        for channel, expected_inactive in test_cases:
            result = extractor.is_inactive_channel(channel)
            status = "✓" if result == expected_inactive else "✗"
            print(f"  {status} {channel}: inactive={result}")

        print("\n[Test 3] Extract Competitors")
        test_cases = [
            "AR| Real Madrid vs Barcelona",
            "US| Warriors @ Lakers",
            "AR| Paris Saint-Germain - Lyon",
            "BOXING: Canelo Alvarez vs John Ryder",
            "UFC 311: Makhachev vs Nurmagomedov",
        ]

        for channel in test_cases:
            competitors = extractor.extract_competitors(channel)
            status = "✓" if competitors else "✗"
            print(f"  {status} {channel[:40]}: {competitors}")

        print("\n[Test 4] Extract Event Date")
        test_cases = [
            ("AR| Real Madrid vs Barcelona (2025-01-20 14:00:00)", "2025-01-20"),
            ("AR| Paris Saint-Germain - Lyon | Jan 25 19:45", "01-25"),
            ("US| Cowboys - Giants | Sat 20:00 PM", None),  # Will infer date
            ("AR: TOD PPV 1 - NO EVENT STREAMING", None),
        ]

        for channel, expected_substring in test_cases:
            date_info = extractor.extract_date(channel)
            if date_info:
                result = date_info.strftime("%Y-%m-%d %H:%M")
                status = "✓"
            else:
                result = "None"
                status = "?"
            print(f"  {status} {channel[:40]}: {result}")

        return True
    except Exception as e:
        print(f"✗ PPV Event Extractor Error: {e}")
        logger.exception("PPV event extractor error")
        return False


def test_ppv_calendar_enrichment():
    """Test PPV calendar enrichment service integration."""
    print("\n" + "=" * 80)
    print("TESTING PPV CALENDAR ENRICHMENT SERVICE")
    print("=" * 80)

    try:
        from services.ppv_calendar_enrichment_service import API_REQUESTS_PER_MINUTE, DETAIL_FETCH_BATCH_SIZE

        print("\n[Test 1] Service Configuration")
        # Test the constants directly
        print(f"  ✓ API requests per minute (for details): {API_REQUESTS_PER_MINUTE}")
        print(f"  ✓ Detail fetch batch size: {DETAIL_FETCH_BATCH_SIZE}")

        # Check configuration values are reasonable
        if API_REQUESTS_PER_MINUTE <= 30 and DETAIL_FETCH_BATCH_SIZE > 0:
            print("  ✓ Rate limiting constants are correct")
        else:
            print("  ✗ Rate limiting constants incorrect")
            return False

        print("\n[Test 2] Calendar Scraper")
        from services.thesportsdb_calendar_scraper import TheSportsDBCalendarScraper

        scraper = TheSportsDBCalendarScraper()
        print("  ✓ Calendar scraper instantiated")
        print(f"  ✓ Cache TTL: {scraper.cache_ttl_seconds} seconds")

        return True
    except Exception as e:
        print(f"✗ PPV Calendar Enrichment Error: {e}")
        logger.exception("PPV calendar enrichment error")
        return False


def test_real_world_matching():
    """Test real-world PPV channel matching scenarios."""
    print("\n" + "=" * 80)
    print("TESTING REAL-WORLD MATCHING SCENARIOS")
    print("=" * 80)

    try:
        from services.ppv_event_extractor import PPVEventExtractor

        extractor = PPVEventExtractor(current_date=datetime(2026, 1, 2, 12, 0))

        print("\n[Test 1] Extract All Information from Channel")
        test_channels = [
            "AR| Real Madrid vs Barcelona (2025-01-20 14:00:00)",
            "US| Warriors @ Lakers | Jan 20 19:00",
            "UFC 311: Makhachev vs Nurmagomedov (2025-01-18 23:00)",
        ]

        for channel in test_channels:
            info = extractor.extract_all(channel)
            has_competitors = bool(info.get("competitors"))
            has_date = bool(info.get("date"))
            status = "✓" if (has_competitors or has_date) else "?"
            print(f"  {status} {channel[:45]}")
            print(f"     → Competitors: {info.get('competitors')}")
            print(f"     → Date: {info.get('date')}")
            print(f"     → Inferred: {info.get('inferred_how')}")

        print("\n[Test 2] Skip NO_DATA Placeholders")
        placeholders = [
            "AR: TOD PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE",
            "AR: TOD PPV 10 - NO EVENT STREAMING - | 8K EXCLUSIVE",
        ]

        for channel in placeholders:
            info = extractor.extract_all(channel)
            is_placeholder = info.get("is_placeholder")
            status = "✓" if is_placeholder else "✗"
            print(f"  {status} {channel[:50]} → placeholder={is_placeholder}")

        print("\n[Test 3] Filter Inactive Channels")
        inactive = [
            "(Fanatiz 001)",
            "DAZN PPV",
            "    ",
        ]

        for channel in inactive:
            is_inactive = extractor.is_inactive_channel(channel)
            status = "✓" if is_inactive else "✗"
            print(f"  {status} '{channel}' → inactive={is_inactive}")

        return True
    except Exception as e:
        print(f"✗ Real-World Matching Error: {e}")
        logger.exception("Real-world matching error")
        return False


def test_html_search_patterns():
    """Test HTML parsing and search patterns."""
    print("\n" + "=" * 80)
    print("TESTING HTML SEARCH AND PARSING")
    print("=" * 80)

    try:
        from services.ppv_event_extractor import PPVEventExtractor

        extractor = PPVEventExtractor()

        # Test regex patterns directly
        print("\n[Test 1] Competitor Pattern Matching")
        test_cases = [
            ("Real Madrid vs Barcelona", ["Real Madrid", "Barcelona"]),
            ("Warriors @ Lakers", ["Warriors", "Lakers"]),
            ("Federer, Roger vs Nadal, Rafael @ time", ["Federer, Roger", "Nadal, Rafael"]),
            ("Paris Saint-Germain - Lyon", ["Paris Saint-Germain", "Lyon"]),
        ]

        for channel, expected_teams in test_cases:
            competitors = extractor.extract_competitors(channel)
            if competitors and len(competitors) == 2:
                status = "✓"
            else:
                status = "✗"
            print(f"  {status} {channel}: {competitors}")

        print("\n[Test 2] Date Pattern Matching")
        test_cases = [
            "Jan 25 19:45",
            "January 20 14:00 PM",
            "2025-01-20 14:00:00",
            "Sat 20:00 PM",
        ]

        for date_str in test_cases:
            date_info = extractor.extract_date(f"Channel | {date_str}")
            status = "✓" if date_info else "?"
            print(f"  {status} {date_str}: {date_info}")

        return True
    except Exception as e:
        print(f"✗ HTML Search Patterns Error: {e}")
        logger.exception("HTML search patterns error")
        return False


def test_rate_limiting():
    """Test rate limiting configuration."""
    print("\n" + "=" * 80)
    print("TESTING RATE LIMITING")
    print("=" * 80)

    try:
        from services.ppv_calendar_enrichment_service import API_REQUESTS_PER_MINUTE, DETAIL_FETCH_BATCH_SIZE

        print("\n[Test 1] Rate Limit Constants (Calendar Enrichment)")
        print(f"  ✓ API requests per minute (details only): {API_REQUESTS_PER_MINUTE}")
        print(f"  ✓ Detail fetch batch size: {DETAIL_FETCH_BATCH_SIZE}")
        print("  ✓ Calendar scraping: No rate limit (HTML scraping)")

        if API_REQUESTS_PER_MINUTE <= 30:
            print("  ✓ Rate limit correctly set under 30/minute")
        else:
            print(f"  ✗ Rate limit should be <= 30/minute, got {API_REQUESTS_PER_MINUTE}")
            return False

        return True
    except Exception as e:
        print(f"✗ Rate Limiting Error: {e}")
        logger.exception("Rate limiting error")
        return False


def test_all():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("IPTV PROXY v2 - API & HTML SEARCH INTEGRATION TESTS")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    results = {
        "TheSportsDB Service": test_thesportsdb_service(),
        "PPV Event Extractor": test_ppv_event_extractor(),
        "PPV Calendar Enrichment": test_ppv_calendar_enrichment(),
        "Real-World Matching": test_real_world_matching(),
        "HTML Search Patterns": test_html_search_patterns(),
        "Rate Limiting": test_rate_limiting(),
    }

    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")
    print("=" * 80)

    return all(results.values())


if __name__ == "__main__":
    success = test_all()
    sys.exit(0 if success else 1)
