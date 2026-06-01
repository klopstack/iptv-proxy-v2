"""
Tests for PPV Calendar Enrichment Service

Comprehensive test coverage for the calendar-based PPV event enrichment workflow.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest

from services.ppv.constants import GENERIC_CHANNEL_PATTERNS
from services.ppv.detection import is_generic_channel_name
from services.ppv.enrichment import (
    EnrichmentResult,
    PPVCalendarEnrichmentService,
    enrich_ppv_channels_batch,
    get_calendar_enrichment_service,
)
from services.thesportsdb_calendar_scraper import CalendarEvent


class TestIsGenericChannelName:
    """Tests for the is_generic_channel_name helper function."""

    @pytest.mark.parametrize(
        "channel_name,expected",
        [
            # Generic/placeholder names - should be filtered
            ("PPV 1", True),
            ("PPV 23", True),
            ("PPV Event", True),
            ("PPV Event 1", True),
            ("UFC Event", True),
            ("UFC Event 5", True),
            ("Boxing Event", True),
            ("MMA Event", True),
            ("Sport Event", True),
            ("Sports Event 2", True),
            ("Live Event", True),
            ("Event 1", True),
            ("Event 99", True),
            ("1 - PPV", True),
            ("23 - PPV", True),
            ("PPV HD", True),
            ("PPV HD 1", True),
            ("(ESPN)", True),
            ("(Fanatiz 012)", True),
            ("MILB 01", True),
            ("MILB 100", True),
            ("Milb  100", True),
            ("US (MiLB 100)", True),
            # Real event names - should NOT be filtered
            ("Clearwater Threshers vs Dunedin Blue Jays @ May 31 12:00 PM :Milb  01", False),
            ("US (MiLB 009) | Syracuse Mets @ Rochester Red Wings (2026-05-31 13:05:10)", False),
            ("UFC 300 Pereira vs Hill", False),
            ("Boxing: Fury vs Usyk", False),
            ("WWE WrestleMania 40", False),
            ("Canelo vs Bivol", False),
            ("Jake Paul vs Mike Tyson", False),
            ("NBA All-Star Game", False),
            ("Premier League Live", False),
        ],
    )
    def test_generic_channel_detection(self, channel_name, expected):
        """Test that generic channel names are correctly identified."""
        result = is_generic_channel_name(channel_name)
        assert result == expected, f"Expected {expected} for '{channel_name}'"

    def test_case_insensitivity(self):
        """Test that generic pattern matching is case-insensitive."""
        assert is_generic_channel_name("ppv 1")
        assert is_generic_channel_name("PPV 1")
        assert is_generic_channel_name("Ppv 1")
        assert is_generic_channel_name("ufc event")
        assert is_generic_channel_name("UFC EVENT")

    def test_whitespace_handling(self):
        """Test that whitespace is handled correctly."""
        assert is_generic_channel_name("PPV 1")
        assert is_generic_channel_name(" PPV 1 ")
        assert is_generic_channel_name("  PPV  1  ")


class TestEnrichmentResult:
    """Tests for EnrichmentResult dataclass."""

    def test_default_values(self):
        """Test EnrichmentResult with minimal arguments."""
        mock_channel = Mock()
        result = EnrichmentResult(channel=mock_channel, matched=False)

        assert result.channel == mock_channel
        assert result.matched is False
        assert result.event is None
        assert result.calendar_event is None
        assert result.confidence == 0.0
        assert result.match_method == "none"
        assert result.extraction_result is None
        assert result.error is None

    def test_all_values(self):
        """Test EnrichmentResult with all arguments."""
        mock_channel = Mock()
        mock_event = Mock()
        mock_calendar_event = Mock()
        extraction = {"competitors": ("Team A", "Team B")}

        result = EnrichmentResult(
            channel=mock_channel,
            matched=True,
            event=mock_event,
            calendar_event=mock_calendar_event,
            confidence=0.85,
            match_method="calendar_high_confidence",
            extraction_result=extraction,
            error=None,
        )

        assert result.matched is True
        assert result.event == mock_event
        assert result.calendar_event == mock_calendar_event
        assert result.confidence == 0.85
        assert result.match_method == "calendar_high_confidence"
        assert result.extraction_result == extraction


class TestPPVCalendarEnrichmentServiceInit:
    """Tests for PPVCalendarEnrichmentService initialization."""

    def test_init_creates_extractor(self, app):
        """Test that service creates PPVEventExtractor."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            assert service.extractor is not None

    def test_init_creates_calendar_scraper(self, app):
        """Test that service creates calendar scraper."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            assert service.calendar_scraper is not None

    def test_init_creates_thesportsdb_service(self, app):
        """Test that service creates TheSportsDB service."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            assert service.thesportsdb is not None

    def test_init_creates_empty_queue(self, app):
        """Test that service creates empty detail queue."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            assert service._detail_queue.empty()

    def test_init_stats_zeroed(self, app):
        """Test that service initializes stats to zero."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            assert service._stats["channels_processed"] == 0
            assert service._stats["channels_matched"] == 0
            assert service._stats["api_requests"] == 0


class TestExtractAllChannels:
    """Tests for _extract_all_channels method."""

    def test_extracts_from_all_channels(self, app):
        """Test that extraction is performed on all channels."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            # Create mock channels
            channels = [
                Mock(name="UFC 300 Pereira vs Hill"),
                Mock(name="Boxing: Fury vs Usyk"),
                Mock(name="PPV 1"),
            ]

            # Mock the extractor
            service.extractor = Mock()
            service.extractor.extract_all.side_effect = [
                {"competitors": ("Pereira", "Hill"), "is_placeholder": False},
                {"competitors": ("Fury", "Usyk"), "is_placeholder": False},
                {"competitors": None, "is_placeholder": True},
            ]

            results = service._extract_all_channels(channels)

            assert len(results) == 3
            assert service.extractor.extract_all.call_count == 3


class TestGroupByDate:
    """Tests for _group_by_date method."""

    def test_groups_by_explicit_date(self, app):
        """Test grouping channels by explicit date."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            channel1 = Mock(name="Event Jan 5")
            channel2 = Mock(name="Event Jan 6")
            channel3 = Mock(name="Another Jan 5")

            extractions = [
                (channel1, {"date": "2026-01-05", "competitors": ("A", "B")}),
                (channel2, {"date": "2026-01-06", "competitors": ("C", "D")}),
                (channel3, {"date": "2026-01-05", "competitors": ("E", "F")}),
            ]

            grouped = service._group_by_date(extractions)

            assert "2026-01-05" in grouped
            assert "2026-01-06" in grouped
            assert len(grouped["2026-01-05"]) == 2
            assert len(grouped["2026-01-06"]) == 1


class TestGetEventDate:
    """Tests for _get_event_date method."""

    def test_explicit_date_string(self, app):
        """Test extracting explicit date from string."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            extraction = {"date": "2026-01-05"}
            result = service._get_event_date(extraction)
            assert result == "2026-01-05"

    def test_explicit_date_datetime(self, app):
        """Test extracting explicit date from datetime object."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            extraction = {"date": datetime(2026, 1, 5, 20, 0, tzinfo=timezone.utc)}
            result = service._get_event_date(extraction)
            assert result == "2026-01-05"

    def test_no_date_defaults_to_today(self, app):
        """Test that missing date defaults to today."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            extraction = {}
            result = service._get_event_date(extraction)
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            assert result == today


class TestMatchChannelToCalendar:
    """Tests for _match_channel_to_calendar method."""

    def test_no_calendar_events(self, app):
        """Test matching when no calendar events available."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            # Mock ReverseEventMatcher for empty calendar
            service.reverse_matcher = Mock()
            service.reverse_matcher.load_events_for_date_range = Mock()
            service.reverse_matcher.find_matches = Mock(return_value=[])

            channel = Mock()
            channel.name = "UFC Event"
            extraction = {"competitors": ("Fighter A", "Fighter B")}

            result = service._match_channel_to_calendar(channel, extraction, [], "2026-01-05")

            assert result.matched is False
            # With empty calendar_events list, it returns early before calling ReverseEventMatcher
            assert result.match_method == "no_calendar_events"

    def test_successful_match(self, app):
        """Test successful channel-to-event matching."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            # Mock the ReverseEventMatcher to return a match
            mock_calendar_event = CalendarEvent(
                event_id="12345",
                event_name="Fighter A vs Fighter B",
                league_name="UFC",
                time_utc="22:00",
                date="2027-01-05",
                home_team="Fighter A",
                away_team="Fighter B",
            )

            # Mock MatchResult from ReverseEventMatcher
            mock_match_result = Mock()
            mock_match_result.event = mock_calendar_event
            mock_match_result.confidence = 0.85

            service.reverse_matcher = Mock()
            service.reverse_matcher.load_events_for_date_range = Mock()
            service.reverse_matcher.find_matches = Mock(return_value=[mock_match_result])

            channel = Mock()
            channel.name = "UFC: Fighter A vs Fighter B"
            extraction = {"competitors": ("Fighter A", "Fighter B"), "time_only": None}

            result = service._match_channel_to_calendar(channel, extraction, [mock_calendar_event], "2026-01-05")

            assert result.matched is True
            assert result.confidence == 0.85
            assert result.calendar_event == mock_calendar_event
            # Verify ReverseEventMatcher was called
            service.reverse_matcher.load_events_for_date_range.assert_called_once()
            service.reverse_matcher.find_matches.assert_called_once()

    def test_low_confidence_no_match(self, app):
        """Test that low confidence scores result in no match."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            # Mock ReverseEventMatcher to return no matches
            # (low confidence matches are filtered out by find_matches)
            service.reverse_matcher = Mock()
            service.reverse_matcher.load_events_for_date_range = Mock()
            service.reverse_matcher.find_matches = Mock(return_value=[])  # No matches pass threshold

            channel = Mock()
            channel.name = "UFC: Fighter A vs Fighter B"
            extraction = {"competitors": ("Fighter A", "Fighter B"), "time_only": None}

            mock_calendar_event = CalendarEvent(
                event_id="12345",
                event_name="Some Other Event",
                league_name="UFC",
                time_utc="22:00",
                date="2027-01-05",
            )

            result = service._match_channel_to_calendar(channel, extraction, [mock_calendar_event], "2026-01-05")

            assert result.matched is False
            assert result.match_method == "no_match_found"

    def test_ambiguous_medium_confidence_match_rejected(self, app):
        """Test that ambiguous low-confidence matches are rejected."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            # Create two calendar events with similar names
            mock_event1 = CalendarEvent(
                event_id="12345",
                event_name="Fighter A vs Fighter B",
                league_name="UFC",
                time_utc="22:00",
                date="2027-01-05",
                home_team="Fighter A",
                away_team="Fighter B",
            )

            mock_event2 = CalendarEvent(
                event_id="67890",
                event_name="Fighter A vs Fighter C",
                league_name="UFC",
                time_utc="23:00",
                date="2027-01-05",
                home_team="Fighter A",
                away_team="Fighter C",
            )

            # Mock ReverseEventMatcher to return two close matches
            # (both low confidence, gap < 0.2)
            mock_match1 = Mock()
            mock_match1.event = mock_event1
            mock_match1.confidence = 0.45  # Low confidence
            mock_match1.match_type = "both_teams"

            mock_match2 = Mock()
            mock_match2.event = mock_event2
            mock_match2.confidence = 0.40  # Close to first match (gap = 0.05 < 0.2)
            mock_match2.match_type = "both_teams"

            service.reverse_matcher = Mock()
            service.reverse_matcher.load_events_for_date_range = Mock()
            service.reverse_matcher.find_matches = Mock(return_value=[mock_match1, mock_match2])

            channel = Mock()
            channel.name = "UFC: Fighter vs Someone"
            extraction = {"competitors": ("Fighter", "Someone"), "time_only": None}

            result = service._match_channel_to_calendar(channel, extraction, [mock_event1, mock_event2], "2026-01-05")

            # Should reject ambiguous match
            assert result.matched is False
            assert result.match_method == "ambiguous_match"

    def test_clear_winner_medium_confidence_accepted(self, app):
        """Test that low-confidence matches with clear winner are accepted."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            mock_event1 = CalendarEvent(
                event_id="12345",
                event_name="Fighter A vs Fighter B",
                league_name="UFC",
                time_utc="22:00",
                date="2027-01-05",
                home_team="Fighter A",
                away_team="Fighter B",
            )

            mock_event2 = CalendarEvent(
                event_id="67890",
                event_name="Different Event",
                league_name="Boxing",
                time_utc="23:00",
                date="2027-01-05",
            )

            # Mock ReverseEventMatcher with clear winner (gap >= 0.2 for low confidence)
            mock_match1 = Mock()
            mock_match1.event = mock_event1
            mock_match1.confidence = 0.45  # Low confidence

            mock_match2 = Mock()
            mock_match2.event = mock_event2
            mock_match2.confidence = 0.20  # Much lower (gap = 0.25 >= 0.2)

            service.reverse_matcher = Mock()
            service.reverse_matcher.load_events_for_date_range = Mock()
            service.reverse_matcher.find_matches = Mock(return_value=[mock_match1, mock_match2])

            channel = Mock()
            channel.name = "UFC: Fighter A vs Fighter B"
            extraction = {"competitors": ("Fighter A", "Fighter B"), "time_only": None}

            result = service._match_channel_to_calendar(channel, extraction, [mock_event1, mock_event2], "2026-01-05")

            # Should accept the clear winner
            assert result.matched is True
            assert result.confidence == 0.45
            assert result.calendar_event == mock_event1
            assert result.match_method == "calendar_low_confidence"


class TestCreateOrUpdateEvent:
    """Tests for _create_or_update_event method."""

    def test_creates_new_event(self, app, db):
        """Test creating a new event from calendar data."""

        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            calendar_event = CalendarEvent(
                event_id="12345",
                event_name="Fighter A vs Fighter B",
                league_name="UFC",
                time_utc="22:00",
                date="2027-01-05",
                home_team="Fighter A",
                away_team="Fighter B",
            )
            # Note: scheduled_at is a computed property based on date and time_utc

            event = service._create_or_update_event(calendar_event)

            assert event is not None
            assert event.external_id == "12345"
            assert event.home_team_name == "Fighter A"
            assert event.away_team_name == "Fighter B"
            assert event.data_completeness == "basic"

    def test_returns_existing_event(self, app, db):
        """Test that existing event is returned without duplication."""
        from models import Event

        with app.app_context():
            # Create existing event
            existing = Event(
                external_id="12345",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="",
                home_team_name="Fighter A",
                away_team_id="",
                away_team_name="Fighter B",
                scheduled_at=datetime(2027, 1, 5, 22, 0, tzinfo=timezone.utc),
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(existing)
            db.session.commit()

            service = PPVCalendarEnrichmentService(app)

            calendar_event = CalendarEvent(
                event_id="12345",
                event_name="Fighter A vs Fighter B",
                league_name="UFC",
                time_utc="22:00",
                date="2027-01-05",
                home_team="Fighter A",
                away_team="Fighter B",
            )

            event = service._create_or_update_event(calendar_event)

            assert event.id == existing.id


class TestLinkChannelToEvent:
    """Tests for _link_channel_to_event method."""

    def test_creates_new_link(self, app, db):
        """Test creating a new channel-event link."""
        from models import Account, Category, Channel, Event, EventChannelLink

        with app.app_context():
            # Create test data
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(account_id=account.id, category_id="1", category_name="PPV")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id=100,
                name="Test PPV Channel",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.flush()

            event = Event(
                external_id="12345",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="team_a",
                home_team_name="Team A",
                away_team_id="team_b",
                away_team_name="Team B",
                scheduled_at=datetime.now(timezone.utc),
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()

            service = PPVCalendarEnrichmentService(app)
            service._link_channel_to_event(channel, event, 0.85, "calendar_high_confidence")
            db.session.commit()

            link = EventChannelLink.query.filter_by(channel_id=channel.id, event_id=event.id).first()

            assert link is not None
            assert link.match_confidence == 0.85
            assert link.match_method == "calendar_high_confidence"

    def test_updates_existing_link_if_better_confidence(self, app, db):
        """Test that existing link is updated if new confidence is higher."""
        from models import Account, Category, Channel, Event, EventChannelLink

        with app.app_context():
            # Create test data
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.flush()

            category = Category(account_id=account.id, category_id="1", category_name="PPV")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id=100,
                name="Test PPV Channel",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.flush()

            event = Event(
                external_id="12345",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="team_a",
                home_team_name="Team A",
                away_team_id="team_b",
                away_team_name="Team B",
                scheduled_at=datetime.now(timezone.utc),
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.flush()

            # Create existing link with lower confidence
            existing_link = EventChannelLink(
                event_id=event.id,
                channel_id=channel.id,
                match_confidence=0.5,
                match_method="calendar_low_confidence",
            )
            db.session.add(existing_link)
            db.session.commit()

            service = PPVCalendarEnrichmentService(app)
            service._link_channel_to_event(channel, event, 0.9, "calendar_high_confidence")
            db.session.commit()

            link = EventChannelLink.query.filter_by(channel_id=channel.id, event_id=event.id).first()

            assert link.match_confidence == 0.9
            assert link.match_method == "calendar_high_confidence"


class TestDetailFetcher:
    """Tests for detail fetcher thread functionality."""

    def test_start_detail_fetcher(self, app):
        """Test starting the detail fetcher thread."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            service.start_detail_fetcher()

            assert service._detail_thread is not None
            assert service._detail_thread.is_alive()

            # Clean up
            service.stop_detail_fetcher()

    def test_stop_detail_fetcher(self, app):
        """Test stopping the detail fetcher thread."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            service.start_detail_fetcher()
            assert service._detail_thread.is_alive()

            service.stop_detail_fetcher()

            # Thread should stop within timeout
            assert not service._detail_thread.is_alive() or service._stop_detail_thread.is_set()

    def test_start_fetcher_twice_logs_warning(self, app):
        """Test that starting fetcher twice logs a warning."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            service.start_detail_fetcher()
            thread1 = service._detail_thread

            # Starting again should not create new thread
            with patch("services.ppv.enrichment.logger") as mock_logger:
                service.start_detail_fetcher()
                mock_logger.warning.assert_called_once()

            # Same thread should be running
            assert service._detail_thread == thread1

            # Clean up
            service.stop_detail_fetcher()


class TestUpdateEventFromApi:
    """Tests for _update_event_from_api method."""

    def test_updates_basic_info(self, app, db):
        """Test updating event with API data."""
        from models import Event

        with app.app_context():
            event = Event(
                external_id="12345",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="",
                home_team_name="Unknown",
                away_team_id="",
                away_team_name="Unknown",
                scheduled_at=datetime.now(timezone.utc),
                status=Event.STATUS_SCHEDULED,
                data_completeness="basic",
            )
            db.session.add(event)
            db.session.commit()

            service = PPVCalendarEnrichmentService(app)

            api_data = {
                "strSport": "MMA",
                "strLeague": "UFC",
                "idLeague": "4443",
                "strHomeTeam": "Pereira",
                "idHomeTeam": "123",
                "strAwayTeam": "Hill",
                "idAwayTeam": "456",
                "strTimestamp": "2026-01-05T22:00:00Z",
                "strVenue": "T-Mobile Arena",
                "strCity": "Las Vegas",
                "strCountry": "USA",
                "strPoster": "https://example.com/poster.jpg",
                "strStatus": "Not Started",
            }

            service._update_event_from_api(event, api_data)

            assert event.sport == "MMA"
            assert event.league_name == "UFC"
            assert event.home_team_name == "Pereira"
            assert event.away_team_name == "Hill"
            assert event.venue_name == "T-Mobile Arena"
            assert event.city == "Las Vegas"
            assert event.data_completeness == "full"

    def test_updates_status_finished(self, app, db):
        """Test updating event status to finished."""
        from models import Event

        with app.app_context():
            event = Event(
                external_id="12345",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="team_a_id",
                home_team_name="A",
                away_team_id="team_b_id",
                away_team_name="B",
                scheduled_at=datetime.now(timezone.utc),
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()

            service = PPVCalendarEnrichmentService(app)

            # Provide complete API data to avoid NOT NULL violations
            api_data = {
                "strStatus": "Match Finished",
                "idHomeTeam": "team_a_id",
                "idAwayTeam": "team_b_id",
            }
            service._update_event_from_api(event, api_data)

            assert event.status == Event.STATUS_FINISHED


class TestGetStatus:
    """Tests for get_status method."""

    def test_returns_status_dict(self, app):
        """Test that get_status returns expected structure."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            # Mock calendar scraper cache stats
            service.calendar_scraper = Mock()
            service.calendar_scraper.get_cache_stats.return_value = {"hits": 10, "misses": 2}

            status = service.get_status()

            assert "detail_queue_size" in status
            assert "detail_thread_running" in status
            assert "calendar_cache_stats" in status
            assert "cumulative_stats" in status
            assert "session_stats" in status


class TestGetCalendarEnrichmentService:
    """Tests for get_calendar_enrichment_service singleton function."""

    def test_returns_singleton(self, app):
        """Test that function returns same instance."""
        # Reset singleton for test
        import services.ppv.enrichment as module

        module._service_instance = None

        with app.app_context():
            service1 = get_calendar_enrichment_service(app)
            service2 = get_calendar_enrichment_service(app)

            assert service1 is service2


class TestEnrichPPVChannelsBatch:
    """Tests for enrich_ppv_channels_batch convenience function."""

    def test_no_channels_returns_error(self, app, db):
        """Test that empty channel list returns error."""
        from models import Account

        with app.app_context():
            account = Account(name="Test", server="test.com")
            db.session.add(account)
            db.session.commit()

            # Reset singleton
            import services.ppv.enrichment as module

            module._service_instance = None

            result = enrich_ppv_channels_batch(app, account.id)

            assert "error" in result


class TestGenericPatterns:
    """Tests for GENERIC_CHANNEL_PATTERNS constant."""

    def test_patterns_are_valid_regex(self):
        """Test that all patterns are valid regular expressions."""
        import re

        for pattern in GENERIC_CHANNEL_PATTERNS:
            try:
                re.compile(pattern)
            except re.error as e:
                pytest.fail(f"Invalid regex pattern '{pattern}': {e}")

    def test_patterns_count(self):
        """Test that we have expected number of patterns."""
        # Should have at least 10 generic patterns
        assert len(GENERIC_CHANNEL_PATTERNS) >= 10


class TestFarFutureEnrichmentFilter:
    """Tests that channels with dates >31 days in the future are skipped during enrichment."""

    def _make_channel(self, name):
        ch = Mock()
        ch.name = name
        ch.ppv_enrichment_status = None
        return ch

    def test_far_future_channel_skipped(self, app):
        """A channel with an extracted date >31 days away is filtered out before matching."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            far_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=45)

            # Patch the internal steps so we can inspect the valid_extractions list
            with patch.object(service, "_extract_all_channels") as mock_extract, patch.object(
                service, "_group_by_date"
            ) as mock_group, patch.object(service, "_update_stats"), patch(
                "services.ppv.enrichment.sync_enrichment_status_from_links"
            ), patch(
                "services.ppv.enrichment.prune_orphan_ppv_events"
            ):

                ch = self._make_channel("UFC 405: Jones vs Smith")
                mock_extract.return_value = [
                    (
                        ch,
                        {
                            "is_placeholder": False,
                            "is_inactive": False,
                            "competitors": ("Jones", "Smith"),
                            "date": far_date,
                        },
                    )
                ]
                # Return an empty group so nothing tries to match
                mock_group.return_value = {}

                result = service.enrich_channels([ch], fetch_details=False)

            # The channel was filtered out (counted as no_extraction, reason: far_future)
            assert result["no_extraction"] == 1
            assert result["far_future_skipped"] == 1
            assert result["processed"] == 0

    def test_channel_within_31_days_not_skipped(self, app):
        """A channel with an extracted date <=31 days away proceeds to matching."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            near_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=20)

            with patch.object(service, "_extract_all_channels") as mock_extract, patch.object(
                service, "_group_by_date"
            ) as mock_group, patch.object(service, "_update_stats"), patch(
                "services.ppv.enrichment.sync_enrichment_status_from_links"
            ), patch(
                "services.ppv.enrichment.prune_orphan_ppv_events"
            ):

                ch = self._make_channel("UFC 403: Brown vs White")
                mock_extract.return_value = [
                    (
                        ch,
                        {
                            "is_placeholder": False,
                            "is_inactive": False,
                            "competitors": ("Brown", "White"),
                            "date": near_date,
                        },
                    )
                ]
                mock_group.return_value = {}

                result = service.enrich_channels([ch], fetch_details=False)

            # Channel was NOT filtered as far_future — it was accepted into valid_extractions
            assert result["no_extraction"] == 0

    def test_channel_with_no_date_not_skipped(self, app):
        """A channel with no extracted date is not affected by the far-future filter."""
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)

            with patch.object(service, "_extract_all_channels") as mock_extract, patch.object(
                service, "_group_by_date"
            ) as mock_group, patch.object(service, "_update_stats"), patch(
                "services.ppv.enrichment.sync_enrichment_status_from_links"
            ), patch(
                "services.ppv.enrichment.prune_orphan_ppv_events"
            ):

                ch = self._make_channel("UFC 404: Fighter vs Fighter")
                mock_extract.return_value = [
                    (
                        ch,
                        {
                            "is_placeholder": False,
                            "is_inactive": False,
                            "competitors": ("Fighter A", "Fighter B"),
                            "date": None,
                        },
                    )
                ]
                mock_group.return_value = {}

                result = service.enrich_channels([ch], fetch_details=False)

            assert result["no_extraction"] == 0
