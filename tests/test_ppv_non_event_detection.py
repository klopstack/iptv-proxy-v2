"""
Test suite for PPV non-event detection.

This module verifies that the PPV filter correctly identifies and hides non-event channels.
The most critical aspect is ensuring we never show PPV channels that are NOT hosting an event.
"""

from datetime import datetime

import pytest

from services.ppv_filter_service import PPVFilterService


class TestPPVNonEventDetection:
    """Test non-event channel detection across all filter types."""

    @pytest.fixture
    def service(self):
        """Create a service with a fixed current time for testing."""
        # Friday, Jan 17, 2025 at 1:00 PM
        current = datetime(2025, 1, 17, 13, 0)
        return PPVFilterService(current_time=current)

    # ============================================================================
    # Tests for Universal Non-Event Patterns
    # ============================================================================

    def test_no_event_marker(self, service):
        """Channels with 'NO EVENT' marker should be hidden."""
        result, meta = service.should_show_channel("PEACOCK PPV - NO EVENT STREAMING", "US| PEACOCK PPV")
        assert result is False, "NO EVENT STREAMING marker should hide channel"

    def test_no_event_short_marker(self, service):
        """Channels with just 'NO EVENT' should be hidden."""
        result, meta = service.should_show_channel("PPV EVENT - NO EVENT", "US| PPV EVENT")
        assert result is False, "NO EVENT marker should hide channel"

    def test_offline_marker(self, service):
        """Channels marked as OFFLINE should be hidden."""
        result, meta = service.should_show_channel("DAZN PPV - OFFLINE", "US| DAZN PPV")
        assert result is False, "OFFLINE marker should hide channel"

    def test_tbd_marker(self, service):
        """Channels marked as TBD should be hidden."""
        result, meta = service.should_show_channel("Event TBD - Check back soon", "US| PPV EVENT")
        assert result is False, "TBD marker should hide channel"

    def test_dash_only_marker(self, service):
        """Channels that are just a dash should be hidden."""
        result, meta = service.should_show_channel("PPV Channel -", "US| PPV EVENT")
        assert result is False, "Dash-only channel should be hidden"

    # ============================================================================
    # Tests for Empty/Malformed Entries
    # ============================================================================

    def test_empty_time_slot_rugby(self, service):
        """Rugby entry with no time (16:|) should be hidden."""
        result, meta = service.should_show_channel("Rugby 16:|", "US| RUGBY PPV")
        assert result is False, "Empty rugby time slot should be hidden"

    def test_empty_time_slot_nfl(self, service):
        """NFL entry with empty slot (| 01 -) should be hidden."""
        result, meta = service.should_show_channel("NFL  | 01 -|", "US| NFL PPV")
        assert result is False, "Empty NFL slot should be hidden (unknown provider, defaults to HIDE)"

    def test_empty_nfhs_slot(self, service):
        """NFHS entry with empty time (60 -) should be hidden."""
        result, meta = service.should_show_channel("NFHS PPV 60 -", "US| NFHS PPV")
        assert result is False, "Empty NFHS slot should be hidden (unknown provider)"

    # ============================================================================
    # Tests for Relative Time Format (Rugby, NRL, AFL)
    # ============================================================================

    def test_valid_rugby_today(self, service):
        """Valid rugby event today should be shown."""
        result, meta = service.should_show_channel("Rugby 1: Stormers vs Lions 1:30pm", "US| RUGBY PPV")
        assert result is True, "Valid rugby event today should be shown"
        assert meta is not None, "Should return event metadata"
        assert meta["start_datetime"].hour == 13, "Hour should be 13 (1:30 PM)"
        assert meta["start_datetime"].minute == 30, "Minute should be 30"

    def test_valid_rugby_sunday(self, service):
        """Valid rugby event on Sunday should be shown."""
        result, meta = service.should_show_channel(
            "Rugby 10: Southland vs Counties Manukau 5:35am Sun", "US| RUGBY PPV"
        )
        assert result is True, "Valid rugby event Sunday should be shown"
        assert meta is not None, "Should return event metadata"
        # Sunday is Jan 19, 2025
        assert meta["start_datetime"].day == 19, "Should be Sunday (day 19)"
        assert meta["start_datetime"].hour == 5, "Hour should be 5"
        assert meta["start_datetime"].minute == 35, "Minute should be 35"

    def test_past_rugby_event(self, service):
        """Past rugby event should be hidden."""
        result, meta = service.should_show_channel("Rugby Old: Team A vs Team B 12:00pm", "US| RUGBY PPV")
        assert result is False, "Past rugby event (12:00 PM, before 1:00 PM) should be hidden"

    def test_future_rugby_event_3pm(self, service):
        """Rugby event at 3 PM (after current 1 PM) should be shown."""
        result, meta = service.should_show_channel("Rugby 3: Saracens vs Exeter 3:00pm", "US| RUGBY PPV")
        assert result is True, "Future rugby event at 3 PM should be shown"
        assert meta["start_datetime"].hour == 15, "Hour should be 15 (3:00 PM)"

    def test_nrl_tv_with_day(self, service):
        """NRL entry with day name should work."""
        result, meta = service.should_show_channel("NRL TV 01: Panthers @ Sharks 4:30am Sun", "AU| NRL TV PPV")
        assert result is True, "Valid NRL event Sunday should be shown"
        assert meta["start_datetime"].day == 19, "Should be Sunday"
        assert meta["start_datetime"].hour == 4, "Hour should be 4"

    def test_afl_ppv_event(self, service):
        """AFL PPV event should work."""
        result, meta = service.should_show_channel("AFL 01: Team A vs Team B 8:00am Sat", "AU| AFL PPV")
        # Saturday would be Jan 18, 2025 (tomorrow from Friday Jan 17)
        assert result is True, "Valid AFL event should be shown"
        assert meta["start_datetime"].day == 18, "Should be Saturday"
        assert meta["start_datetime"].hour == 8, "Hour should be 8"

    # ============================================================================
    # Tests for ISO Datetime Format
    # ============================================================================

    def test_valid_espn_plus_event(self, service):
        """Valid ESPN+ event with future datetime should be shown."""
        result, meta = service.should_show_channel("ESPN+ 001 (2025-01-20 14:00:00) - Some Event", "US| ESPN+ PPV")
        assert result is True, "Valid future ESPN+ event should be shown"
        assert meta is not None, "Should return metadata"

    def test_espn_plus_placeholder_date(self, service):
        """ESPN+ with placeholder date (2098-12-31) should be hidden."""
        result, meta = service.should_show_channel("ESPN+ 046 (2098-12-31 08:00:01) - No Event", "US| ESPN+ PPV")
        assert result is False, "Placeholder date 2098-12-31 should be hidden"

    def test_espn_plus_past_event(self, service):
        """ESPN+ event with past datetime should be hidden."""
        result, meta = service.should_show_channel("ESPN+ 100 (2025-01-15 14:00:00) - Past Event", "US| ESPN+ PPV")
        assert result is False, "Past event should be hidden"

    def test_fanatiz_future_event(self, service):
        """Fanatiz event with future datetime should be shown."""
        result, meta = service.should_show_channel("Fanatiz (2025-01-25 07:30:00) - Match Event", "BR| FANATIZ PPV")
        assert result is True, "Valid future Fanatiz event should be shown"

    # ============================================================================
    # Tests for Text-Based Filtering
    # ============================================================================

    def test_dazn_no_event_streaming(self, service):
        """DAZN with 'NO EVENT STREAMING' should be hidden."""
        result, meta = service.should_show_channel("DAZN PPV - NO EVENT STREAMING", "US| DAZN PPV")
        assert result is False, "DAZN with NO EVENT STREAMING should be hidden"

    def test_24_7_entertainment_always_shown(self, service):
        """24/7 entertainment channels should always be shown."""
        result, meta = service.should_show_channel("US: 24/7 COMEDY MOVIES", "US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ")
        assert result is True, "24/7 pattern should always show"

    # ============================================================================
    # Tests for Always Show/Hide Types
    # ============================================================================

    def test_bally_sports_always_shown(self, service):
        """Bally Sports should always be shown (subscription channels)."""
        result, meta = service.should_show_channel("BALLY SPORTS ARIZONA HD", "US| BALLY SPORTS PPV")
        assert result is True, "Bally Sports should always be shown"

    # ============================================================================
    # Tests for Unknown Providers (Conservative Default)
    # ============================================================================

    def test_unknown_provider_defaults_to_hide(self, service):
        """Unknown providers should default to HIDE (conservative)."""
        result, meta = service.should_show_channel("Some Event at Some Time", "XX| UNKNOWN PPV PROVIDER")
        assert result is False, "Unknown provider should default to HIDE"

    def test_malformed_channel_name(self, service):
        """Malformed channel names should be hidden."""
        result, meta = service.should_show_channel("| | | -", "US| PPV EVENT")
        assert result is False, "Heavily malformed channel should be hidden"

    # ============================================================================
    # Integration Tests - Full Workflow
    # ============================================================================

    def test_full_ppv_list_realistic_sample(self, service):
        """Test with realistic sample from actual PPV.list data."""
        test_cases = [
            # (channel_name, category, should_show, reason)
            ("Rugby 1: Stormers vs Lions 1:30pm", "US| RUGBY PPV", True, "Future time"),
            ("Rugby 16:|", "US| RUGBY PPV", False, "Empty time"),
            ("PEACOCK PPV - NO EVENT STREAMING", "US| PEACOCK PPV", False, "NO EVENT marker"),
            ("ESPN+ (2025-01-20 15:00:00) Event", "US| ESPN+ PPV", True, "Future datetime"),
            ("ESPN+ (2098-12-31 00:00:00) Placeholder", "US| ESPN+ PPV", False, "Placeholder date"),
            ("BALLY SPORTS ARIZONA", "US| BALLY SPORTS PPV", True, "Always show"),
            ("Random Unknown Event", "XX| UNKNOWN PPV", False, "Unknown provider"),
        ]

        for channel, category, expected_show, reason in test_cases:
            result, _ = service.should_show_channel(channel, category)
            assert (
                result == expected_show
            ), f"Failed: {reason}\n  Channel: {channel}\n  Expected: {expected_show}, Got: {result}"


class TestPPVFilterEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def service(self):
        """Create service at boundary time (2 PM exactly)."""
        return PPVFilterService(current_time=datetime(2025, 1, 17, 14, 0))

    def test_event_at_exact_current_time(self, service):
        """Event at exactly current time should be shown (event is happening now)."""
        result, _ = service.should_show_channel("Rugby 1: Event 2:00pm", "US| RUGBY PPV")
        # Current time is 2:00 PM, event is at 2:00 PM
        # The comparison is event_datetime < self.current_time, so 2:00 PM < 2:00 PM is False
        # Therefore the event will be shown (it's happening now)
        assert result is True, "Event at exact current time should be shown (happening now)"

    def test_event_one_minute_in_future(self, service):
        """Event one minute in the future should be shown."""
        result, _ = service.should_show_channel("Rugby 1: Event 2:01pm", "US| RUGBY PPV")
        assert result is True, "Event 1 minute in future should be shown"

    def test_midnight_transition(self):
        """Test event spanning midnight (today vs tomorrow)."""
        # Create service at 11 PM
        service = PPVFilterService(current_time=datetime(2025, 1, 17, 23, 0))

        # Event at 1 AM "tomorrow" (or just time without day = today = past)
        result, _ = service.should_show_channel("Rugby 1: Event 1:00am", "US| RUGBY PPV")
        # Without day specified, 1:00am is interpreted as 1:00 AM today
        # which is 22 hours in the past, so should be hidden
        assert result is False, "1:00 AM today (past) should be hidden"


class TestPPVFilterDataIntegrity:
    """Test that filter rules are properly loaded and configured."""

    def test_all_provider_rules_configured(self):
        """Verify all documented providers have rules configured."""
        service = PPVFilterService()

        expected_providers = [
            "US| ESPN+ PPV",
            "US| B1G+ PPV",
            "US| DAZN PPV",
            "US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ",
            "US| BALLY SPORTS PPV",
            "BR| FANATIZ PPV",
            "US| RUGBY PPV",
            "AU| NRL TV PPV",
            "AU| AFL PPV",
            "US| LIVE FOOTBALL PPV",
        ]

        for provider in expected_providers:
            assert provider in service._default_rules, f"Provider '{provider}' rule not found in defaults"

    def test_filter_rule_has_required_fields(self):
        """Verify each rule has required configuration."""
        service = PPVFilterService()

        for provider, rule in service._default_rules.items():
            assert "filter_type" in rule, f"{provider} missing 'filter_type'"
            assert "provider_name" in rule, f"{provider} missing 'provider_name'"

            filter_type = rule["filter_type"]
            if filter_type == "ISO_DATETIME":
                assert "date_field_pattern" in rule, f"{provider} missing 'date_field_pattern'"
            elif filter_type == "TEXT_BASED":
                # Should have either placeholder_text or always_show_pattern
                has_placeholder = "placeholder_text" in rule
                has_show = "always_show_pattern" in rule
                assert (
                    has_placeholder or has_show
                ), f"{provider} (TEXT_BASED) missing placeholder_text or always_show_pattern"
            elif filter_type == "RELATIVE_TIME":
                assert "time_pattern" in rule, f"{provider} missing 'time_pattern'"


class TestPPVFilterBatchProcessing:
    """Test filtering in batch mode (like processing multiple channels)."""

    @pytest.fixture
    def service(self):
        """Create service with fixed time."""
        return PPVFilterService(current_time=datetime(2025, 1, 17, 13, 0))

    def test_batch_rugby_entries(self, service):
        """Process a batch of rugby entries and verify filtering."""
        entries = [
            ("Rugby 1: Stormers vs Lions 1:30pm", True),
            ("Rugby 2: Glasgow vs Edinburgh 2:00pm", True),
            ("Rugby 3: Saracens vs Exeter 3:00pm", True),
            ("Rugby 16:|", False),  # Empty
            ("Rugby 16: Past Event 12:00pm", False),  # Past
        ]

        results = []
        for channel, expected in entries:
            result, _ = service.should_show_channel(channel, "US| RUGBY PPV")
            results.append((channel, result == expected))

        # All should pass
        assert all(passed for _, passed in results), f"Some entries failed: {[c for c, p in results if not p]}"

    def test_batch_mixed_providers(self, service):
        """Process entries from different providers."""
        entries = [
            ("Rugby 1: Event 1:30pm", "US| RUGBY PPV", True),
            ("DAZN PPV - NO EVENT STREAMING", "US| DAZN PPV", False),
            ("ESPN+ (2025-01-20 14:00:00) Event", "US| ESPN+ PPV", True),
            ("BALLY SPORTS HD", "US| BALLY SPORTS PPV", True),
        ]

        for channel, category, expected in entries:
            result, _ = service.should_show_channel(channel, category)
            assert result == expected, f"Failed for {category}: {channel}\nExpected: {expected}, Got: {result}"


class TestPPVFilterUtilityMethods:
    """Test utility methods for datetime parsing and event extraction."""

    @pytest.fixture
    def service(self):
        """Create service with fixed time."""
        return PPVFilterService(current_time=datetime(2025, 1, 17, 13, 0))

    # =========================================================================
    # Tests for extract_datetime_string
    # =========================================================================

    def test_extract_datetime_with_parentheses(self, service):
        """Extract datetime from parentheses."""
        channel = "Event (2025-01-20 14:00:00) Description"
        pattern = r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)"
        result = service.extract_datetime_string(channel, pattern)
        assert result == "2025-01-20 14:00:00"

    def test_extract_datetime_not_found(self, service):
        """Return None when pattern doesn't match."""
        channel = "Event with no datetime"
        pattern = r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)"
        result = service.extract_datetime_string(channel, pattern)
        assert result is None

    def test_extract_datetime_with_whitespace(self, service):
        """Handle whitespace in extracted datetime."""
        channel = "Event (  2025-01-20 14:00:00  )"
        pattern = r"\(\s*(\d{4}-\d{2}-\d{2}\s[\d:]+)\s*\)"
        result = service.extract_datetime_string(channel, pattern)
        assert result == "2025-01-20 14:00:00"

    def test_extract_datetime_invalid_regex(self, service):
        """Handle invalid regex pattern gracefully."""
        channel = "Event (2025-01-20 14:00:00)"
        pattern = r"(?P<invalid"  # Invalid regex
        result = service.extract_datetime_string(channel, pattern)
        assert result is None

    # =========================================================================
    # Tests for parse_iso_datetime
    # =========================================================================

    def test_parse_iso_datetime_with_space(self, service):
        """Parse ISO datetime with space separator."""
        result = service.parse_iso_datetime("2025-01-20 14:00:00")
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 20
        assert result.hour == 14

    def test_parse_iso_datetime_with_t(self, service):
        """Parse ISO datetime with T separator."""
        result = service.parse_iso_datetime("2025-01-20T14:00:00")
        assert result is not None
        assert result.hour == 14

    def test_parse_iso_datetime_with_z(self, service):
        """Parse ISO datetime with Z timezone."""
        result = service.parse_iso_datetime("2025-01-20T14:00:00Z")
        assert result is not None
        assert result.hour == 14

    def test_parse_dd_mm_format(self, service):
        """Parse DD/MM HH:MM format with year inference."""
        # Date: 25/01 (future from Jan 17)
        result = service.parse_iso_datetime("25/01 14:00")
        assert result is not None
        assert result.day == 25
        assert result.month == 1
        assert result.year == 2025

    def test_parse_mm_dd_format(self, service):
        """Parse MM/DD HH:MM format with year inference."""
        # Date: 01/25 (US format, future from Jan 17)
        result = service.parse_iso_datetime("01/25 14:00")
        assert result is not None
        assert result.month == 1
        assert result.day == 25

    def test_parse_datetime_no_year_past(self, service):
        """Parse date without year - if past this year, use next year."""
        # Date: 19/10 (October 19, past from Jan 17)
        # Should infer year as 2025 (since we're in Jan, Oct is future)
        result = service.parse_iso_datetime("19/10 14:00")
        assert result is not None
        assert result.month == 10
        assert result.day == 19

    def test_parse_datetime_empty_string(self, service):
        """Return None for empty datetime string."""
        result = service.parse_iso_datetime("")
        assert result is None

    def test_parse_datetime_invalid_format(self, service):
        """Return None for unrecognized datetime format."""
        result = service.parse_iso_datetime("invalid-datetime")
        assert result is None

    def test_parse_datetime_short_format(self, service):
        """Parse datetime without seconds."""
        result = service.parse_iso_datetime("2025-01-20 14:00")
        assert result is not None
        assert result.hour == 14
        assert result.minute == 0

    # =========================================================================
    # Tests for extract_event_name
    # =========================================================================

    def test_extract_event_name_with_pipe(self, service):
        """Extract event name between pipe and parenthesis."""
        channel = "Provider | Team A vs Team B (2025-01-20 14:00:00)"
        result = service.extract_event_name(channel)
        assert result == "Team A vs Team B"

    def test_extract_event_name_before_parenthesis(self, service):
        """Extract event name before parenthesis."""
        channel = "Event Name (2025-01-20 14:00:00)"
        result = service.extract_event_name(channel)
        assert result == "Event Name"

    def test_extract_event_name_empty_channel(self, service):
        """Return None for empty channel name."""
        result = service.extract_event_name("")
        assert result is None

    def test_extract_event_name_no_pattern(self, service):
        """Return None when no pattern matches."""
        result = service.extract_event_name("Some random channel")
        assert result is None

    # =========================================================================
    # Tests for _get_next_weekday
    # =========================================================================

    def test_get_next_weekday_tomorrow(self, service):
        """Get next weekday when it's coming up soon."""
        # Current: Friday Jan 17, 2025
        # Next Saturday: Jan 18
        result = service._get_next_weekday("Sat")
        assert result.day == 18
        assert result.month == 1
        assert result.year == 2025

    def test_get_next_weekday_same_day_future(self, service):
        """Get same weekday (Friday to Friday)."""
        # Current: Friday Jan 17, 2025
        # Next Friday: Jan 24
        result = service._get_next_weekday("Fri")
        # Should return today (day 17) since same weekday
        assert result.day == 17 or result.day == 24

    def test_get_next_weekday_full_name(self, service):
        """Handle full weekday names."""
        result = service._get_next_weekday("Sunday")
        assert result is not None
        # Should be Jan 19, 2025 (Sunday)
        assert result.day == 19

    def test_get_next_weekday_invalid(self, service):
        """Return current date for invalid weekday name."""
        result = service._get_next_weekday("InvalidDay")
        assert result == service.current_time.date()

    # =========================================================================
    # Tests for _estimate_event_duration
    # =========================================================================

    def test_estimate_duration_basketball(self, service):
        """Basketball events should be 2.5 hours."""
        channel = "NBA Basketball Game"
        rule = {}
        result = service._estimate_event_duration(channel, rule)
        assert result.total_seconds() == 2.5 * 3600

    def test_estimate_duration_wrestling(self, service):
        """Wrestling events should be 4 hours."""
        channel = "WWE Wrestling Event"
        rule = {}
        result = service._estimate_event_duration(channel, rule)
        assert result.total_seconds() == 4 * 3600

    def test_estimate_duration_baseball(self, service):
        """Baseball events should be 3 hours."""
        channel = "MLB Baseball Game"
        rule = {}
        result = service._estimate_event_duration(channel, rule)
        assert result.total_seconds() == 3 * 3600

    def test_estimate_duration_default(self, service):
        """Default duration is 4 hours."""
        channel = "Unknown Sport Event"
        rule = {}
        result = service._estimate_event_duration(channel, rule)
        assert result.total_seconds() == 4 * 3600

    def test_estimate_duration_soccer(self, service):
        """Soccer events should be 2.5 hours."""
        channel = "Soccer Match"
        rule = {}
        result = service._estimate_event_duration(channel, rule)
        assert result.total_seconds() == 2.5 * 3600

    # =========================================================================
    # Tests for error handling and edge cases
    # =========================================================================

    def test_handler_unknown_filter_type(self, service):
        """Unknown filter type should return False (HIDE)."""
        result, meta = service.should_show_channel("Test Channel", "TEST| PPV", {"filter_type": "UNKNOWN_TYPE"})
        assert result is False
        assert meta is None

    def test_handler_exception_handling(self, service):
        """Exceptions during filtering should result in HIDE."""
        # Create a rule that will cause an error in handlers
        rule = {
            "filter_type": "ISO_DATETIME",
            "date_field_pattern": r"(?P<invalid",  # Invalid regex
        }
        result, meta = service.should_show_channel("Test Channel", "TEST| PPV", rule)
        assert result is False
        assert meta is None

    def test_relative_time_invalid_hour_range(self, service):
        """Reject times with invalid hour values."""
        result, _ = service.should_show_channel(
            "Event 25:30pm",  # Invalid hour
            "US| RUGBY PPV",
        )
        # Should be hidden because 25 > 12
        assert result is False

    def test_text_based_with_empty_patterns_list(self, service):
        """Text-based with empty pattern lists should hide."""
        result, meta = service.should_show_channel(
            "Regular Event",
            "TEST| PPV",
            {
                "filter_type": "TEXT_BASED",
                "placeholder_text": [],
                "always_show_pattern": [],
            },
        )
        assert result is False

    # =========================================================================
    # Tests for non-event detection edge cases
    # =========================================================================

    def test_non_event_header_marker(self, service):
        """Channels with header markers should be hidden."""
        result, _ = service.should_show_channel("##### RUGBY PPV #####", "US| RUGBY PPV")
        assert result is False

    def test_non_event_comment_marker(self, service):
        """Channels with comment markers should be hidden."""
        result, _ = service.should_show_channel("### Sports PPV ###", "US| PPV")
        assert result is False

    def test_non_event_empty_after_slot(self, service):
        """Channel with empty content after slot number."""
        result, _ = service.should_show_channel("Channel 01:", "US| PPV")
        assert result is False

    def test_non_event_pipe_dash_format(self, service):
        """Channel with pipe-dash format (provider | 01 -)."""
        result, _ = service.should_show_channel("Provider | 01 -", "US| PPV")
        assert result is False

    # =========================================================================
    # Tests for actual event metadata
    # =========================================================================

    def test_event_metadata_contains_required_fields(self, service):
        """Event metadata should contain required fields."""
        result, meta = service.should_show_channel("Rugby 1: Stormers vs Lions 1:30pm", "US| RUGBY PPV")
        assert result is True
        assert meta is not None
        assert "event_name" in meta
        assert "start_datetime" in meta
        assert "suggested_duration" in meta
        assert "confidence" in meta

    def test_event_metadata_confidence(self, service):
        """Event metadata confidence should be reasonable."""
        result, meta = service.should_show_channel("Rugby 1: Stormers vs Lions 1:30pm", "US| RUGBY PPV")
        assert meta["confidence"] >= 0.8
