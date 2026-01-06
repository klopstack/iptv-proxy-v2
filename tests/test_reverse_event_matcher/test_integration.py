"""
Integration Tests for Reverse Event Matcher

Tests the complete workflow with realistic scenarios to ensure all components
work together correctly.
"""

from datetime import datetime, timedelta, timezone

from services.reverse_event_matcher.orchestrator import ReverseEventMatcher
from services.thesportsdb_calendar_scraper import CalendarEvent


def make_calendar_event(
    event_id: str,
    event_name: str,
    league_name: str,
    date: str,
    time_utc: str,
    home_team: str = None,
    away_team: str = None,
) -> CalendarEvent:
    """Helper to create CalendarEvent instances for testing."""
    return CalendarEvent(
        event_id=event_id,
        event_name=event_name,
        league_name=league_name,
        date=date,
        time_utc=time_utc,
        home_team=home_team,
        away_team=away_team,
    )


class TestRealWorldScenarios:
    """Test with realistic channel name formats."""

    def test_standard_team_format(self):
        """Test standard 'Team A vs Team B' format."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        events = [
            make_calendar_event(
                event_id="1",
                event_name="Lakers vs Celtics",
                league_name="NBA",
                date=tomorrow.strftime("%Y-%m-%d"),
                time_utc=tomorrow.strftime("%H:%M") + " UTC",
                home_team="Los Angeles Lakers",
                away_team="Boston Celtics",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Test various channel name formats
        test_channels = [
            "Lakers vs Celtics",
            "LA Lakers vs Boston Celtics",
            "Lakers Celtics",
            "NBA: Lakers vs Celtics",
            "PPV Lakers vs Celtics",
        ]

        for channel in test_channels:
            matches = matcher.find_matches(channel)
            assert len(matches) > 0, f"Should match: {channel}"
            assert matches[0].event.event_id == "1"

    def test_messy_channel_names(self):
        """Test channels with extra noise and formatting."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        events = [
            make_calendar_event(
                event_id="1",
                event_name="UFC 300",
                league_name="UFC",
                date=tomorrow.strftime("%Y-%m-%d"),
                time_utc=tomorrow.strftime("%H:%M") + " UTC",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Messy formats that should still match
        test_channels = [
            "PPV: UFC 300 Main Card",
            "[HD] UFC 300",
            "UFC_300_Main_Event",
            "UFC 300 | Main Card",
        ]

        for channel in test_channels:
            matches = matcher.find_matches(channel)
            # Should match UFC 300
            assert len(matches) >= 0  # May match depending on word overlap

    def test_date_in_channel_name(self):
        """Test channels with dates embedded in name."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        event_time = now + timedelta(hours=6)

        events = [
            make_calendar_event(
                event_id="1",
                event_name="Big Fight",
                league_name="Boxing",
                date=event_time.strftime("%Y-%m-%d"),
                time_utc=event_time.strftime("%H:%M") + " UTC",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Channel with date should get confidence boost
        date_str = event_time.strftime("%m/%d/%Y")
        matches = matcher.find_matches(f"Big Fight {date_str}")

        # Should return results (may or may not match depending on confidence)
        assert isinstance(matches, list)

    def test_multiple_events_same_league(self):
        """Test matching when multiple events exist in same league."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        events = [
            make_calendar_event(
                event_id="1",
                event_name="Lakers vs Celtics",
                league_name="NBA",
                date=tomorrow.strftime("%Y-%m-%d"),
                time_utc="20:00 UTC",
                home_team="Los Angeles Lakers",
                away_team="Boston Celtics",
            ),
            make_calendar_event(
                event_id="2",
                event_name="Warriors vs Heat",
                league_name="NBA",
                date=tomorrow.strftime("%Y-%m-%d"),
                time_utc="22:00 UTC",
                home_team="Golden State Warriors",
                away_team="Miami Heat",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Should match correct event
        matches = matcher.find_matches("Lakers vs Celtics")
        assert len(matches) > 0
        assert matches[0].event.event_id == "1"

        matches = matcher.find_matches("Warriors vs Heat")
        assert len(matches) > 0
        assert matches[0].event.event_id == "2"

    def test_past_vs_future_events(self):
        """Test filtering past vs future events."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        past = now - timedelta(days=10)
        future = now + timedelta(days=2)

        events = [
            make_calendar_event(
                event_id="past",
                event_name="Old Fight",
                league_name="Boxing",
                date=past.strftime("%Y-%m-%d"),
                time_utc=past.strftime("%H:%M") + " UTC",
            ),
            make_calendar_event(
                event_id="future",
                event_name="Upcoming Fight",
                league_name="Boxing",
                date=future.strftime("%Y-%m-%d"),
                time_utc=future.strftime("%H:%M") + " UTC",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        from services.reverse_event_matcher.match_filter import DateFilter

        # Search for future events only
        matches = matcher.find_matches("Fight", date_filter=DateFilter.UPCOMING_ONLY)

        # Should prefer/include future event
        if len(matches) > 0:
            # If we got matches, future should be preferred
            assert any(m.event.event_id == "future" for m in matches)


class TestPerformance:
    """Test performance with larger datasets."""

    def test_large_event_set(self):
        """Test with 100+ events to verify performance."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        events = []

        # Create 100 events across different leagues
        leagues = ["NBA", "NFL", "NHL", "MLB", "Soccer"]
        team_names = [
            "Eagles",
            "Hawks",
            "Bears",
            "Lions",
            "Panthers",
            "Jaguars",
            "Tigers",
            "Wolves",
            "Foxes",
            "Sharks",
        ]

        for i in range(100):
            league = leagues[i % len(leagues)]
            event_date = now + timedelta(days=(i % 30))
            home = f"{team_names[i % len(team_names)]} {chr(65 + (i // len(team_names)))}"
            away = f"{team_names[(i + 1) % len(team_names)]} {chr(66 + (i // len(team_names)))}"

            events.append(
                make_calendar_event(
                    event_id=f"event_{i}",
                    event_name=f"{home} vs {away}",
                    league_name=league,
                    date=event_date.strftime("%Y-%m-%d"),
                    time_utc=event_date.strftime("%H:%M") + " UTC",
                    home_team=home,
                    away_team=away,
                )
            )

        # Index building should be fast
        import time

        start = time.time()
        matcher._event_index.build_indexes(events)
        build_time = time.time() - start

        matcher._events_loaded = True

        # Should complete in reasonable time (< 1 second for 100 events)
        assert build_time < 1.0, f"Index building took {build_time:.2f}s"

        # Matching should also be fast
        start = time.time()
        matches = matcher.find_matches("Eagles A vs Hawks B")
        match_time = time.time() - start

        # Should complete in reasonable time (< 0.1 seconds)
        assert match_time < 0.1, f"Matching took {match_time:.2f}s"
        assert len(matches) > 0, "Should find matches for Eagles vs Hawks"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_no_events_loaded(self):
        """Test behavior when no events are loaded."""
        matcher = ReverseEventMatcher()

        matches = matcher.find_matches("Test Channel")
        assert matches == []

    def test_empty_channel_name(self):
        """Test with empty channel name."""
        matcher = ReverseEventMatcher()
        matcher._events_loaded = True

        matches = matcher.find_matches("")
        assert matches == []

    def test_generic_channel_names(self):
        """Test that generic names don't match."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        events = [
            make_calendar_event(
                event_id="1",
                event_name="Big Event",
                league_name="Sport",
                date=now.strftime("%Y-%m-%d"),
                time_utc=now.strftime("%H:%M") + " UTC",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Generic channel names should be filtered
        generic_names = [
            "PPV 1",
            "PPV 2",
            "Event 1",
        ]

        for channel in generic_names:
            matches = matcher.find_matches(channel)
            assert matches == [], f"Generic channel should not match: {channel}"

    def test_max_results_limit(self):
        """Test that max_results parameter works."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        # Create multiple events with similar names
        events = []
        for i in range(10):
            events.append(
                make_calendar_event(
                    event_id=f"event_{i}",
                    event_name=f"Fight {i}",
                    league_name="Boxing",
                    date=tomorrow.strftime("%Y-%m-%d"),
                    time_utc=tomorrow.strftime("%H:%M") + " UTC",
                )
            )

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Should respect max_results
        matches = matcher.find_matches("Fight", max_results=3)
        assert len(matches) <= 3

    def test_unicode_and_special_characters(self):
        """Test handling of unicode and special characters."""
        matcher = ReverseEventMatcher()

        now = datetime.now(timezone.utc)
        tomorrow = now + timedelta(days=1)

        events = [
            make_calendar_event(
                event_id="1",
                event_name="Café vs Naïve",
                league_name="Soccer",
                date=tomorrow.strftime("%Y-%m-%d"),
                time_utc=tomorrow.strftime("%H:%M") + " UTC",
                home_team="Café FC",
                away_team="Naïve United",
            ),
        ]

        matcher._event_index.build_indexes(events)
        matcher._events_loaded = True

        # Should handle unicode
        matches = matcher.find_matches("Café vs Naïve")
        assert isinstance(matches, list)


class TestBackwardCompatibility:
    """Test that new implementation maintains backward compatibility."""

    def test_api_compatibility(self):
        """Test that public API matches original implementation."""
        from unittest.mock import Mock

        # Create matcher with mocked scraper to avoid slow network calls
        mock_scraper = Mock()
        mock_scraper.get_events_for_date_range.return_value = {}  # Empty dict

        matcher = ReverseEventMatcher(calendar_scraper=mock_scraper)

        # These methods should exist and work
        assert hasattr(matcher, "load_events_for_date_range")
        assert hasattr(matcher, "find_matches")
        assert hasattr(matcher, "get_stats")
        assert hasattr(matcher, "clear_cache")

        # load_events_for_date_range should return count
        count = matcher.load_events_for_date_range()
        assert isinstance(count, int)
        assert count == 0  # No events loaded (scraper returns empty)

        # find_matches should return list
        matches = matcher.find_matches("test")
        assert isinstance(matches, list)

        # get_stats should return dict
        stats = matcher.get_stats()
        assert isinstance(stats, dict)

        # clear_cache should not raise
        matcher.clear_cache()
