"""
Tests for PPV Filter Service - Phase 1 & 2 Implementation

Phase 1: Category-specific handling (boxing, wrestling, etc.) show events without explicit times
Phase 2: 24-hour time format support (HH:MM and HH.MM formats)

Test Coverage:
- All filter types (ALWAYS_SHOW, ALWAYS_HIDE, TEXT_BASED, ISO_DATETIME, RELATIVE_TIME, DATETIME_24HR)
- Datetime parsing (ISO, month-day-time, 24-hour, combined)
- Event name extraction
- Duration estimation
- Non-event detection patterns
- Edge cases and error handling
"""

from datetime import date, datetime, time, timedelta

from services.ppv_filter_service import DEFAULT_FILTER_RULES, PPVFilterService


class TestPhase224HourTimeFormatParsing:
    """Test 24-hour time format parsing (HH:MM and HH.MM)"""

    def test_parse_24hour_time_colon_format(self):
        """Test parsing HH:MM format (colon-separated)"""
        service = PPVFilterService()

        # Basic HH:MM format
        result = service.parse_24hour_time("Event at 20:30")
        assert result == time(20, 30, 0)

        result = service.parse_24hour_time("20:30")
        assert result == time(20, 30, 0)

        result = service.parse_24hour_time("Start: 08:15")
        assert result == time(8, 15, 0)

    def test_parse_24hour_time_colon_with_seconds(self):
        """Test parsing HH:MM:SS format"""
        service = PPVFilterService()

        result = service.parse_24hour_time("Starts 20:30:45")
        assert result == time(20, 30, 45)

        result = service.parse_24hour_time("20:30:00")
        assert result == time(20, 30, 0)

    def test_parse_24hour_time_dot_format(self):
        """Test parsing HH.MM format (European dot-separated)"""
        service = PPVFilterService()

        # Basic HH.MM format
        result = service.parse_24hour_time("Event at 20.30")
        assert result == time(20, 30, 0)

        result = service.parse_24hour_time("20.30")
        assert result == time(20, 30, 0)

        result = service.parse_24hour_time("Start: 08.15")
        assert result == time(8, 15, 0)

    def test_parse_24hour_time_dot_with_seconds(self):
        """Test parsing HH.MM.SS format (European)"""
        service = PPVFilterService()

        result = service.parse_24hour_time("Starts 20.30.45")
        assert result == time(20, 30, 45)

        result = service.parse_24hour_time("20.30.00")
        assert result == time(20, 30, 0)

    def test_parse_24hour_time_no_match(self):
        """Test non-matching text returns None"""
        service = PPVFilterService()

        assert service.parse_24hour_time("No time here") is None
        assert service.parse_24hour_time("12:60") is None  # Invalid minute
        assert service.parse_24hour_time("25:30") is None  # Invalid hour
        assert service.parse_24hour_time("") is None

    def test_parse_24hour_time_edge_cases(self):
        """Test edge cases like midnight and end of day"""
        service = PPVFilterService()

        # Midnight
        result = service.parse_24hour_time("00:00")
        assert result == time(0, 0, 0)

        # 23:59
        result = service.parse_24hour_time("23:59")
        assert result == time(23, 59, 0)

        # With leading zero
        result = service.parse_24hour_time("09:05")
        assert result == time(9, 5, 0)

    def test_parse_iso_datetime_with_24hr_iso_format(self):
        """Test that ISO format still works"""
        service = PPVFilterService()

        result = service.parse_iso_datetime_with_24hr("2025-12-27 20:30")
        assert result.year == 2025
        assert result.month == 12
        assert result.day == 27
        assert result.hour == 20
        assert result.minute == 30

    def test_parse_iso_datetime_with_24hr_24hr_format(self):
        """Test 24-hour format combined with sync_date"""
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(sync_date=sync_date)

        result = service.parse_iso_datetime_with_24hr("Event at 20:30")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 20
        assert result.minute == 30

    def test_parse_iso_datetime_with_24hr_override_sync_date(self):
        """Test overriding sync_date for individual parse"""
        default_sync = date(2025, 1, 15)
        override_sync = date(2025, 2, 20)
        service = PPVFilterService(sync_date=default_sync)

        result = service.parse_iso_datetime_with_24hr("Event at 20:30", sync_date_override=override_sync)
        assert result.year == 2025
        assert result.month == 2
        assert result.day == 20
        assert result.hour == 20
        assert result.minute == 30

    def test_parse_iso_datetime_with_24hr_european_format(self):
        """Test European format (HH.MM) with sync_date"""
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(sync_date=sync_date)

        result = service.parse_iso_datetime_with_24hr("Event at 20.30")
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 20
        assert result.minute == 30

    def test_parse_month_day_time_abbrev_pm(self):
        """Test month abbreviation with day and PM time"""
        # Current: Friday Jan 17, 2025
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        result = service.parse_month_day_time("Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK")
        assert result is not None
        assert result.month == 10
        assert result.day == 18
        assert result.hour == 23  # 11PM in 24-hour format
        # Year should be 2025 (Oct 18 is after Jan 17 in same year)
        assert result.year == 2025

    def test_parse_month_day_time_abbrev_am(self):
        """Test month abbreviation with AM time"""
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        result = service.parse_month_day_time("Match on Jan 20 : 9AM ET")
        assert result is not None
        assert result.month == 1
        assert result.day == 20
        assert result.hour == 9
        # Jan 20 is after Jan 17 (test date), so same year
        assert result.year == 2025

    def test_parse_month_day_time_full_name(self):
        """Test full month name"""
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        result = service.parse_month_day_time("Event on December 25 : 6PM")
        assert result is not None
        assert result.month == 12
        assert result.day == 25
        assert result.hour == 18

    def test_parse_month_day_time_various_separators(self):
        """Test various separator styles"""
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        # With colon
        result1 = service.parse_month_day_time("Oct 18 : 11PM")
        # With dash
        result2 = service.parse_month_day_time("Oct 18 - 11PM")
        # With slash
        result3 = service.parse_month_day_time("Oct 18 / 11PM")

        assert result1 is not None and result1.hour == 23
        assert result2 is not None and result2.hour == 23
        assert result3 is not None and result3.hour == 23

    def test_parse_month_day_time_midnight(self):
        """Test midnight (12AM and 12PM)"""
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        midnight = service.parse_month_day_time("Event Jan 20 : 12AM")
        assert midnight is not None
        assert midnight.hour == 0

        noon = service.parse_month_day_time("Event Jan 20 : 12PM")
        assert noon is not None
        assert noon.hour == 12

    def test_parse_month_day_time_invalid(self):
        """Test invalid month-day-time formats"""
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        assert service.parse_month_day_time("No date here") is None
        assert service.parse_month_day_time("Jan 32 : 5PM") is None  # Invalid day
        assert service.parse_month_day_time("Jan 20 : 13PM") is None  # Invalid hour
        assert service.parse_month_day_time("Xyz 20 : 5PM") is None  # Invalid month

    def test_parse_iso_datetime_with_24hr_month_format(self):
        """Test month-day-time fallback in combined parser"""
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        service = PPVFilterService(current_time=current_time)
        result = service.parse_iso_datetime_with_24hr("Event Oct 18 : 11PM")
        assert result is not None
        assert result.month == 10
        assert result.day == 18
        assert result.hour == 23

    def test_parse_danny_garcia_ppv_entry(self):
        """Test actual NO_DATA entry: Danny Garcia PPV match"""
        # Current test time: Friday Jan 17, 2025 at 1:00 PM
        current_time = datetime(2025, 1, 17, 13, 0, 0)
        sync_date = current_time.date()
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        # Actual channel name from line 8570 of NO_DATA.list
        channel_name = "LIVE EVENT 26 -Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK / 6PM ET"

        # Parse the event
        result = service.parse_iso_datetime_with_24hr(channel_name)
        assert result is not None
        assert result.month == 10
        assert result.day == 18
        assert result.hour == 23
        assert result.year == 2025

        # Verify it would not be hidden (future date)
        assert result > current_time


class TestPhase1CategorySpecificHandling:
    """Test Phase 1: Events in categories like boxing, wrestling show without explicit dates"""

    def test_datetime_24hr_filter_with_valid_iso_datetime(self):
        """Test DATETIME_24HR filter with valid ISO datetime"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        # Event in the future
        channel_name = "Boxing Event (2025-01-15 20:30)"
        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)

        assert should_show is True
        assert metadata is not None
        assert metadata["start_datetime"] > current_time

    def test_datetime_24hr_filter_with_24hr_time(self):
        """Test DATETIME_24HR filter with 24-hour time format"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        # Event with just 24-hour time (no explicit date)
        channel_name = "Boxing Event - 20:30"
        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)

        assert should_show is True
        assert metadata is not None
        # Should use sync_date
        assert metadata["start_datetime"].date() == sync_date

    def test_datetime_24hr_filter_allow_no_date_true(self):
        """Test DATETIME_24HR with allow_no_date=True shows event even without time"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        # Event name with no time information
        channel_name = "Boxing Event - No Time Info"
        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)

        # Phase 1: Should show even without explicit time
        assert should_show is True
        assert metadata is not None

    def test_datetime_24hr_filter_allow_no_date_false(self):
        """Test DATETIME_24HR with allow_no_date=False hides event without time"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": False,  # Conservative: hide without explicit time
            "provider_name": "Generic",
        }

        # Event name with no time information
        channel_name = "Event - No Time Info"
        should_show, metadata = service.should_show_channel(channel_name, "US| GENERIC PPV", rule)

        # Should hide (conservative)
        assert should_show is False
        assert metadata is None

    def test_datetime_24hr_filter_past_event_hidden(self):
        """Test DATETIME_24HR hides events in the past"""
        current_time = datetime(2025, 1, 15, 20, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        # Event that has already passed
        channel_name = "Boxing Event (2025-01-15 15:00)"
        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)

        assert should_show is False
        assert metadata is None


class TestDefaultRulesWithPhase1And2:
    """Test that default rules are properly configured for boxing and other categories"""

    def test_default_rules_include_boxing(self):
        """Test that DEFAULT_FILTER_RULES includes boxing category"""
        service = PPVFilterService()

        # Check if boxing rule exists in default rules
        boxing_rule = service._default_rules.get("UK| BOXING PPV")
        assert boxing_rule is not None
        assert boxing_rule["filter_type"] == "DATETIME_24HR"
        assert boxing_rule.get("allow_no_date") is True
        assert boxing_rule["provider_name"] == "Boxing"

    def test_default_rules_include_wrestling(self):
        """Test that DEFAULT_FILTER_RULES includes wrestling categories"""
        service = PPVFilterService()

        # UK Wrestling
        uk_wrestling = service._default_rules.get("UK| WRESTLING PPV")
        assert uk_wrestling is not None
        assert uk_wrestling["filter_type"] == "DATETIME_24HR"
        assert uk_wrestling.get("allow_no_date") is True

        # US Wrestling
        us_wrestling = service._default_rules.get("US| WRESTLING PPV")
        assert us_wrestling is not None
        assert us_wrestling["filter_type"] == "DATETIME_24HR"
        assert us_wrestling.get("allow_no_date") is True

    def test_default_rules_include_mma_ufc_aew_wwe(self):
        """Test that MMA, UFC, AEW, WWE rules are defined"""
        service = PPVFilterService()

        expected_categories = [
            "US| MMA PPV",
            "US| UFC PPV",
            "US| WWE PPV",
            "US| AEW PPV",
        ]

        for category in expected_categories:
            rule = service._default_rules.get(category)
            assert rule is not None, f"Missing rule for {category}"
            assert rule["filter_type"] == "DATETIME_24HR"
            assert rule.get("allow_no_date") is True


class TestIntegrationWithRealWorldChannelNames:
    """Test with realistic PPV channel names from real IPTV providers"""

    def test_boxing_channel_with_european_time(self):
        """Test boxing channel with European time format"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        # Real-world example: "Fury vs Usyk - 20.30 CET"
        channel_name = "Fury vs Usyk - 20.30 CET"
        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)

        assert should_show is True
        assert metadata["start_datetime"].hour == 20
        assert metadata["start_datetime"].minute == 30

    def test_wrestling_channel_with_iso_datetime(self):
        """Test wrestling channel with ISO datetime - uses 24-hour format as fallback"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Wrestling",
        }

        # Channel with just a 24-hour time (not ISO date)
        # Phase 2: Should use sync_date as reference date
        channel_name = "WrestleMania 41 - 19:00 CET"
        should_show, metadata = service.should_show_channel(channel_name, "US| WRESTLING PPV", rule)

        assert should_show is True
        assert metadata["start_datetime"].hour == 19
        assert metadata["start_datetime"].minute == 0
        assert metadata["start_datetime"].date() == sync_date

    def test_ufc_event_without_explicit_date(self):
        """Test UFC event shown without explicit date (Phase 1 behavior)"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "UFC",
        }

        # Event name only, no date (Phase 1 use case)
        channel_name = "UFC 300: Jones vs Miocic"
        should_show, metadata = service.should_show_channel(channel_name, "US| UFC PPV", rule)

        # Phase 1: Show even without explicit time/date
        assert should_show is True
        assert metadata is not None


class TestSyncDateBehavior:
    """Test sync_date parameter behavior (critical for Phase 1 & 2)"""

    def test_sync_date_defaults_to_today(self):
        """Test that sync_date defaults to today if not provided"""
        service = PPVFilterService()
        assert service.sync_date == date.today()

    def test_sync_date_can_be_overridden(self):
        """Test that sync_date can be explicitly set"""
        custom_sync = date(2025, 1, 15)
        service = PPVFilterService(sync_date=custom_sync)
        assert service.sync_date == custom_sync

    def test_sync_date_used_when_only_time_provided(self):
        """Test that sync_date is used when only time is provided (no date)"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 20)  # Different from current date
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        result = service.parse_iso_datetime_with_24hr("Event at 20:30")

        # Should use sync_date, not today
        assert result.date() == sync_date

    def test_sync_date_respected_in_datetime_24hr_handler(self):
        """Test that sync_date is respected in _handle_datetime_24hr"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 25)  # Different date
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        channel_name = "Boxing Event - 20:30"
        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)

        assert should_show is True
        assert metadata["start_datetime"].date() == sync_date


class TestEdgeCasesAndErrorHandling:
    """Test edge cases and error handling"""

    def test_malformed_time_string(self):
        """Test handling of malformed time strings"""
        service = PPVFilterService()

        # Invalid formats should return None
        assert service.parse_24hour_time("25:61") is None
        assert service.parse_24hour_time("abc:def") is None

    def test_empty_channel_name(self):
        """Test handling of empty channel names"""
        service = PPVFilterService()

        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Test",
        }

        should_show, metadata = service.should_show_channel("", "US| TEST PPV", rule)
        assert should_show is False

    def test_channel_with_multiple_time_formats(self):
        """Test channel name with multiple time formats (uses first match)"""
        service = PPVFilterService()

        # Should match the first time format found
        result = service.parse_24hour_time("Start: 20:30 or 20.45")
        # Should get first match (20:30)
        assert result == time(20, 30, 0)


# ============================================================================
# Non-Event Detection Tests
# ============================================================================


class TestNonEventChannelDetection:
    """Test universal non-event channel detection"""

    def test_no_event_text_marker(self):
        """Test detection of 'NO EVENT' marker"""
        service = PPVFilterService()

        test_cases = [
            "NO EVENT",
            "no event",
            "No Event",
            "Channel | NO EVENT",
            "ESPN | NO EVENT - OFFLINE",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_no_event_streaming_marker(self):
        """Test detection of 'NO EVENT STREAMING' marker"""
        service = PPVFilterService()

        test_cases = [
            "NO EVENT STREAMING",
            "no event streaming",
            "Channel NO EVENT STREAMING",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_offline_marker(self):
        """Test detection of 'OFFLINE' marker"""
        service = PPVFilterService()

        test_cases = [
            "Offline",
            "OFFLINE",
            "Channel - Offline",
            "offline stream",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_tbd_marker(self):
        """Test detection of 'TBD' marker"""
        service = PPVFilterService()

        test_cases = [
            "TBD",
            "tbd",
            "Event - TBD",
            "Match TBD",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_empty_slot_markers(self):
        """Test detection of empty slot patterns"""
        service = PPVFilterService()

        test_cases = [
            "-",
            " - ",
            "| -",
            "|- ",
            " | - ",
            "| - |",
            " | ",
            "|",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_header_markers(self):
        """Test detection of header/comment markers"""
        service = PPVFilterService()

        test_cases = [
            "#### HEADER",
            "### SECTION",
            "## Commentary",
            "###### Title",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_slot_number_only(self):
        """Test detection of slot number without event"""
        service = PPVFilterService()

        test_cases = [
            "Channel 01:",
            "Event 10: ",
            "Slot 05:",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_provider_with_dash_marker(self):
        """Test detection of provider with empty content"""
        service = PPVFilterService()

        test_cases = [
            "Rugby 16:|",
            "NFL | 01 -",
            "Provider | 01 -",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is True

    def test_valid_event_channels(self):
        """Test that valid event channels are not marked as non-event"""
        service = PPVFilterService()

        test_cases = [
            "ESPN+ PPV: Live Event",
            "Boxing Match 8PM ET",
            "UFC 300: Jones vs Smith",
            "Wrestling Event 20:30",
            "Sports Event - 2025-01-15 20:30",
        ]

        for channel_name in test_cases:
            assert service._is_non_event_channel(channel_name) is False


# ============================================================================
# Filter Type Handler Tests (ALWAYS_SHOW, ALWAYS_HIDE, TEXT_BASED, etc.)
# ============================================================================


class TestAlwaysShowHandler:
    """Test ALWAYS_SHOW filter handler"""

    def test_always_show_returns_true(self):
        """Test that ALWAYS_SHOW handler always returns True"""
        service = PPVFilterService()
        rule = {"filter_type": "ALWAYS_SHOW", "provider_name": "Bally Sports"}

        test_channels = [
            "BALLY SPORTS ARIZONA",
            "BALLY SPORTS DETROIT",
            "BALLY SPORTS MIDWEST",
            "Regional Sports Network",
        ]

        for channel_name in test_channels:
            should_show, metadata = service.should_show_channel(channel_name, "US| BALLY SPORTS PPV", rule)
            assert should_show is True
            assert metadata is None

    def test_always_show_with_all_channel_names(self):
        """Test ALWAYS_SHOW works with non-empty channel names"""
        service = PPVFilterService()
        rule = {"filter_type": "ALWAYS_SHOW", "provider_name": "Test"}

        # Valid channel names should be shown
        should_show, _ = service.should_show_channel("Test Event Channel", "US| TEST", rule)
        assert should_show is True


class TestAlwaysHideHandler:
    """Test ALWAYS_HIDE filter handler"""

    def test_always_hide_returns_false(self):
        """Test that ALWAYS_HIDE handler always returns False"""
        service = PPVFilterService()
        rule = {"filter_type": "ALWAYS_HIDE", "provider_name": "Header"}

        test_channels = [
            "HEADER CHANNEL",
            "Placeholder",
            "Empty Slot",
            "",
        ]

        for channel_name in test_channels:
            should_show, metadata = service.should_show_channel(channel_name, "US| HEADER", rule)
            assert should_show is False
            assert metadata is None


class TestTextBasedHandler:
    """Test TEXT_BASED filter handler"""

    def test_placeholder_text_single_string(self):
        """Test placeholder_text as single string"""
        service = PPVFilterService()
        rule = {
            "filter_type": "TEXT_BASED",
            "placeholder_text": "NO EVENT STREAMING",
            "provider_name": "DAZN",
        }

        should_show, metadata = service.should_show_channel(
            "DAZN PPV 1 - NO EVENT STREAMING",
            "AT| DAZN PPV",
            rule,
        )
        assert should_show is False

    def test_placeholder_text_list(self):
        """Test placeholder_text as list of strings"""
        service = PPVFilterService()
        rule = {
            "filter_type": "TEXT_BASED",
            "placeholder_text": ["NO EVENT", "OFFLINE", "TBD"],
            "provider_name": "Test",
        }

        test_cases = [
            ("Event NO EVENT", False),
            ("Event OFFLINE", False),
            ("Event TBD", False),
            ("Normal Event", False),  # No positive indicator
        ]

        for channel_name, expected in test_cases:
            should_show, _ = service.should_show_channel(channel_name, "US| TEST", rule)
            assert should_show is expected

    def test_always_show_pattern_single_string(self):
        """Test always_show_pattern as single string"""
        service = PPVFilterService()
        rule = {
            "filter_type": "TEXT_BASED",
            "always_show_pattern": "24/7",
            "provider_name": "Entertainment",
        }

        should_show, _ = service.should_show_channel(
            "Comedy Channel - 24/7",
            "US| ENTERTAINMENT",
            rule,
        )
        assert should_show is True

    def test_always_show_pattern_list(self):
        """Test always_show_pattern as list of strings"""
        service = PPVFilterService()
        rule = {
            "filter_type": "TEXT_BASED",
            "always_show_pattern": ["24/7", "CONTINUOUS"],
            "provider_name": "Entertainment",
        }

        test_cases = [
            ("Channel 24/7", True),
            ("Channel CONTINUOUS", True),
            ("Normal Event", False),
        ]

        for channel_name, expected in test_cases:
            should_show, _ = service.should_show_channel(channel_name, "US| TEST", rule)
            assert should_show is expected

    def test_placeholder_takes_priority_over_always_show(self):
        """Test that placeholder_text has priority over always_show_pattern"""
        service = PPVFilterService()
        rule = {
            "filter_type": "TEXT_BASED",
            "placeholder_text": "NO EVENT",
            "always_show_pattern": "24/7",
            "provider_name": "Test",
        }

        # Even with 24/7 marker, NO EVENT takes priority
        should_show, _ = service.should_show_channel(
            "24/7 Event NO EVENT",
            "US| TEST",
            rule,
        )
        assert should_show is False


class TestISODatetimeHandler:
    """Test ISO_DATETIME filter handler"""

    def test_iso_datetime_future_event_shown(self):
        """Test that future ISO datetime events are shown"""
        current_time = datetime(2025, 12, 27, 0, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "ISO_DATETIME",
            "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
            "placeholder_date": "2098-12-31",
            "provider_name": "ESPN+",
        }

        should_show, metadata = service.should_show_channel(
            "Event (2025-12-28 14:00:00)",
            "US| ESPN+ PPV",
            rule,
        )

        assert should_show is True
        assert metadata is not None
        assert metadata["start_datetime"] == datetime(2025, 12, 28, 14, 0, 0)

    def test_iso_datetime_placeholder_date_hidden(self):
        """Test that placeholder dates are hidden"""
        current_time = datetime(2025, 12, 27, 0, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "ISO_DATETIME",
            "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
            "placeholder_date": "2098-12-31",
            "provider_name": "ESPN+",
        }

        should_show, metadata = service.should_show_channel(
            "Event (2098-12-31 08:00:00)",
            "US| ESPN+ PPV",
            rule,
        )

        assert should_show is False
        assert metadata is None

    def test_iso_datetime_past_event_hidden(self):
        """Test that past events are hidden"""
        current_time = datetime(2025, 12, 27, 14, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "ISO_DATETIME",
            "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
            "placeholder_date": None,
            "provider_name": "Test",
        }

        should_show, _ = service.should_show_channel(
            "Past Event (2025-12-27 10:00:00)",
            "US| TEST",
            rule,
        )

        assert should_show is False

    def test_iso_datetime_cannot_extract_pattern(self):
        """Test handling when datetime cannot be extracted"""
        service = PPVFilterService()

        rule = {
            "filter_type": "ISO_DATETIME",
            "date_field_pattern": r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)",
            "placeholder_date": None,
            "provider_name": "Test",
        }

        should_show, _ = service.should_show_channel(
            "Event with no datetime",
            "US| TEST",
            rule,
        )

        assert should_show is False

    def test_iso_datetime_invalid_datetime_format(self):
        """Test handling when datetime format is invalid"""
        service = PPVFilterService()

        rule = {
            "filter_type": "ISO_DATETIME",
            "date_field_pattern": r"\(([^)]+)\)",
            "placeholder_date": None,
            "provider_name": "Test",
        }

        should_show, _ = service.should_show_channel(
            "Event (INVALID DATETIME)",
            "US| TEST",
            rule,
        )

        assert should_show is False


class TestRelativeTimeHandler:
    """Test RELATIVE_TIME filter handler"""

    def test_relative_time_today_future(self):
        """Test relative time for today in the future"""
        current_time = datetime(2025, 1, 17, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "RELATIVE_TIME",
            "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
            "provider_name": "Rugby",
        }

        should_show, metadata = service.should_show_channel(
            "Rugby Event 1:30pm",
            "US| RUGBY PPV",
            rule,
        )

        assert should_show is True
        assert metadata["start_datetime"].hour == 13
        assert metadata["start_datetime"].minute == 30

    def test_relative_time_today_past(self):
        """Test relative time for today in the past"""
        current_time = datetime(2025, 1, 17, 14, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "RELATIVE_TIME",
            "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
            "provider_name": "Rugby",
        }

        should_show, _ = service.should_show_channel(
            "Rugby Event 1:30pm",
            "US| RUGBY PPV",
            rule,
        )

        assert should_show is False

    def test_relative_time_with_day_name(self):
        """Test relative time with day name"""
        # Friday Jan 17, 2025
        current_time = datetime(2025, 1, 17, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "RELATIVE_TIME",
            "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
            "provider_name": "Rugby",
        }

        # Sunday (6 days away from Friday)
        should_show, metadata = service.should_show_channel(
            "Rugby Event 5:35am Sun",
            "US| RUGBY PPV",
            rule,
        )

        assert should_show is True
        assert metadata["start_datetime"].weekday() == 6  # Sunday

    def test_relative_time_same_weekday_future(self):
        """Test relative time when same weekday but time is in future"""
        # Friday Jan 17, 2025 at 10:00 AM
        current_time = datetime(2025, 1, 17, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "RELATIVE_TIME",
            "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
            "provider_name": "Rugby",
        }

        # Friday afternoon (same day, future time)
        should_show, metadata = service.should_show_channel(
            "Rugby Event 3:00pm Fri",
            "US| RUGBY PPV",
            rule,
        )

        assert should_show is True

    def test_relative_time_invalid_time_format(self):
        """Test handling of invalid time format"""
        current_time = datetime(2025, 1, 17, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        rule = {
            "filter_type": "RELATIVE_TIME",
            "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))(?:\s(Mon|Tue|Wed|Thu|Fri|Sat|Sun))?",
            "provider_name": "Rugby",
        }

        should_show, _ = service.should_show_channel(
            "Rugby Event 25:99pm",
            "US| RUGBY PPV",
            rule,
        )

        assert should_show is False

    def test_relative_time_no_pattern_in_rule(self):
        """Test handling when time_pattern is missing"""
        service = PPVFilterService()

        rule = {
            "filter_type": "RELATIVE_TIME",
            "provider_name": "Rugby",
            # Missing time_pattern
        }

        should_show, _ = service.should_show_channel(
            "Rugby Event 1:30pm",
            "US| RUGBY PPV",
            rule,
        )

        assert should_show is False


# ============================================================================
# Event Metadata and Extraction Tests
# ============================================================================


class TestEventNameExtraction:
    """Test event name extraction from channel names"""

    def test_extract_event_name_with_pipe_separator(self):
        """Test extraction with pipe separator"""
        service = PPVFilterService()

        channel_name = "ESPN+ PPV | Adelaide United vs Western Sydney (2025-12-27 03:35)"
        result = service.extract_event_name(channel_name)

        assert result == "Adelaide United vs Western Sydney"

    def test_extract_event_name_with_parenthesis(self):
        """Test extraction of text before parenthesis"""
        service = PPVFilterService()

        channel_name = "Boxing Match (2025-01-15 20:30)"
        result = service.extract_event_name(channel_name)

        assert result == "Boxing Match"

    def test_extract_event_name_removes_provider_prefix(self):
        """Test that provider prefix is removed"""
        service = PPVFilterService()

        channel_name = "US: Provider | Event Name (2025-01-15 20:30)"
        result = service.extract_event_name(channel_name)

        assert result == "Event Name"

    def test_extract_event_name_empty_channel(self):
        """Test handling of empty channel name"""
        service = PPVFilterService()

        result = service.extract_event_name("")
        assert result is None

    def test_extract_event_name_fallback(self):
        """Test fallback when standard patterns don't match"""
        service = PPVFilterService()

        channel_name = "Event Name No Pattern"
        result = service.extract_event_name(channel_name)

        # Should return None if no standard pattern matches
        assert result is None


class TestEventMetadataConstruction:
    """Test event metadata building"""

    def test_build_event_metadata_basic(self):
        """Test building basic event metadata"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        channel_name = "Boxing Match (2025-01-15 20:30)"
        event_datetime = datetime(2025, 1, 15, 20, 30, 0)
        rule = {"provider_name": "Boxing"}

        metadata = service._build_event_metadata(channel_name, event_datetime, rule)

        assert "event_name" in metadata
        assert "start_datetime" in metadata
        assert "suggested_duration" in metadata
        assert "confidence" in metadata
        assert metadata["start_datetime"] == event_datetime
        assert metadata["confidence"] == 0.9

    def test_build_event_metadata_with_duration(self):
        """Test that duration is calculated"""
        service = PPVFilterService()

        channel_name = "Event (2025-01-15 20:30)"
        event_datetime = datetime(2025, 1, 15, 20, 30, 0)
        rule = {}

        metadata = service._build_event_metadata(channel_name, event_datetime, rule)

        assert isinstance(metadata["suggested_duration"], timedelta)


class TestDurationEstimation:
    """Test event duration estimation"""

    def test_basketball_duration(self):
        """Test basketball duration estimate"""
        service = PPVFilterService()

        # Duration estimation looks for sport keyword in channel name
        duration = service._estimate_event_duration("Basketball Game: Lakers vs Celtics", {})
        assert duration == timedelta(hours=2.5)

    def test_soccer_duration(self):
        """Test soccer duration estimate"""
        service = PPVFilterService()

        duration = service._estimate_event_duration("Football: Man United vs Liverpool", {})
        assert duration == timedelta(hours=2.5)

    def test_wrestling_duration(self):
        """Test wrestling duration estimate"""
        service = PPVFilterService()

        duration = service._estimate_event_duration("WrestleMania 41", {})
        assert duration == timedelta(hours=4)

    def test_baseball_duration(self):
        """Test baseball duration estimate"""
        service = PPVFilterService()

        duration = service._estimate_event_duration("Baseball: Yankees vs Red Sox", {})
        assert duration == timedelta(hours=3)

    def test_default_duration(self):
        """Test default duration for unknown sports"""
        service = PPVFilterService()

        duration = service._estimate_event_duration("Unknown Event Type", {})
        assert duration == timedelta(hours=4)


# ============================================================================
# Datetime String Extraction Tests
# ============================================================================


class TestDatetimeStringExtraction:
    """Test datetime string extraction with regex patterns"""

    def test_extract_datetime_string_basic(self):
        """Test basic datetime extraction"""
        service = PPVFilterService()

        pattern = r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)"
        channel_name = "Event (2025-12-27 03:35:06)"

        result = service.extract_datetime_string(channel_name, pattern)
        assert result == "2025-12-27 03:35:06"

    def test_extract_datetime_string_with_spaces(self):
        """Test extraction handles whitespace in captured group"""
        service = PPVFilterService()

        pattern = r"\(\s*(\d{4}-\d{2}-\d{2}\s[\d:]+)\s*\)"
        channel_name = "Event (  2025-12-27 03:35:06  )"

        result = service.extract_datetime_string(channel_name, pattern)
        assert result == "2025-12-27 03:35:06"

    def test_extract_datetime_string_no_match(self):
        """Test when pattern doesn't match"""
        service = PPVFilterService()

        pattern = r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)"
        channel_name = "Event with no datetime"

        result = service.extract_datetime_string(channel_name, pattern)
        assert result is None

    def test_extract_datetime_string_invalid_regex(self):
        """Test handling of invalid regex pattern"""
        service = PPVFilterService()

        pattern = r"(\d{4}[INVALID"  # Invalid regex
        channel_name = "Event (2025-12-27)"

        result = service.extract_datetime_string(channel_name, pattern)
        assert result is None

    def test_extract_datetime_string_caching(self):
        """Test that compiled regex patterns are cached"""
        service = PPVFilterService()

        pattern = r"\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)"
        channel_name = "Event (2025-12-27 03:35:06)"

        # First call
        service.extract_datetime_string(channel_name, pattern)
        assert pattern in service.compiled_regexes

        # Second call should use cache
        result = service.extract_datetime_string(channel_name, pattern)
        assert result == "2025-12-27 03:35:06"


class TestISODatetimeParsing:
    """Test ISO datetime format parsing"""

    def test_parse_iso_datetime_iso_with_space(self):
        """Test ISO format with space separator"""
        service = PPVFilterService()

        result = service.parse_iso_datetime("2025-12-27 03:35:06")
        assert result == datetime(2025, 12, 27, 3, 35, 6)

    def test_parse_iso_datetime_iso_with_t(self):
        """Test ISO format with T separator"""
        service = PPVFilterService()

        result = service.parse_iso_datetime("2025-12-27T03:35:06")
        assert result == datetime(2025, 12, 27, 3, 35, 6)

    def test_parse_iso_datetime_iso_with_z(self):
        """Test ISO format with Z timezone"""
        service = PPVFilterService()

        result = service.parse_iso_datetime("2025-12-27T03:35:06Z")
        assert result == datetime(2025, 12, 27, 3, 35, 6)

    def test_parse_iso_datetime_iso_with_microseconds(self):
        """Test ISO format with microseconds"""
        service = PPVFilterService()

        result = service.parse_iso_datetime("2025-12-27T03:35:06.123456")
        assert result == datetime(2025, 12, 27, 3, 35, 6, 123456)

    def test_parse_iso_datetime_without_seconds(self):
        """Test ISO format without seconds"""
        service = PPVFilterService()

        result = service.parse_iso_datetime("2025-12-27 03:35")
        assert result == datetime(2025, 12, 27, 3, 35, 0)

    def test_parse_iso_datetime_ddmm_format(self):
        """Test DD/MM format without year"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        result = service.parse_iso_datetime("22/10 19:00")
        assert result.month == 10
        assert result.day == 22
        assert result.hour == 19

    def test_parse_iso_datetime_mmdd_format(self):
        """Test MM/DD format without year"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        result = service.parse_iso_datetime("10/22 19:00")
        assert result.month == 10
        assert result.day == 22
        assert result.hour == 19

    def test_parse_iso_datetime_past_date_in_year(self):
        """Test that past dates in year are moved to next year"""
        current_time = datetime(2025, 6, 15, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        # January is in the past from June
        result = service.parse_iso_datetime("01/15 19:00")
        assert result.year == 2026  # Should be next year

    def test_parse_iso_datetime_invalid(self):
        """Test handling of invalid datetime strings"""
        service = PPVFilterService()

        test_cases = [
            "2025-13-45 25:99:99",  # Invalid month/day/time
            "not a datetime",
            "",
            "2025/13/45",
        ]

        for test_str in test_cases:
            result = service.parse_iso_datetime(test_str)
            assert result is None


# ============================================================================
# Error Handling and Robustness Tests
# ============================================================================


class TestErrorHandlingAndRobustness:
    """Test error handling throughout the service"""

    def test_should_show_channel_with_invalid_filter_type(self):
        """Test handling of unknown filter type"""
        service = PPVFilterService()

        rule = {
            "filter_type": "UNKNOWN_TYPE",
            "provider_name": "Test",
        }

        should_show, metadata = service.should_show_channel("Some Event", "US| TEST", rule)
        assert should_show is False
        assert metadata is None

    def test_should_show_channel_exception_during_filtering(self):
        """Test that exceptions during filtering are caught"""
        service = PPVFilterService()

        rule = {
            "filter_type": "RELATIVE_TIME",
            "time_pattern": r"(\d{1,2}:\d{2}(?:am|pm|AM|PM))",
            "provider_name": "Test",
        }

        # Valid pattern but data that could cause issues
        should_show, metadata = service.should_show_channel("", "US| TEST", rule)
        assert should_show is False
        assert metadata is None

    def test_should_show_channel_with_non_event_defaults_to_hide(self):
        """Test that unknown providers default to HIDE"""
        service = PPVFilterService()

        # Unknown category with no rule
        should_show, _ = service.should_show_channel("Event Name", "US| UNKNOWN PROVIDER", None)
        assert should_show is False

    def test_get_next_weekday_unknown_day(self):
        """Test handling of unknown day name"""
        current_time = datetime(2025, 1, 17, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        result = service._get_next_weekday("XYZ")
        # Should return current date when unknown
        assert result == current_time.date()

    def test_get_next_weekday_all_days(self):
        """Test all day names work correctly"""
        current_time = datetime(2025, 1, 17, 10, 0, 0)  # Friday
        service = PPVFilterService(current_time=current_time)

        day_names = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]

        for day_name in day_names:
            result = service._get_next_weekday(day_name)
            assert isinstance(result, date)


class TestIntegrationWithDefaultRules:
    """Test integration with DEFAULT_FILTER_RULES"""

    def test_all_default_rules_have_required_fields(self):
        """Test that all default rules have required fields"""
        required_fields = ["filter_type", "provider_name"]

        for category, rule in DEFAULT_FILTER_RULES.items():
            for field in required_fields:
                assert field in rule, f"Rule for {category} missing {field}"

    def test_all_default_filter_types_are_valid(self):
        """Test that all filter types are known/valid"""
        valid_types = {
            "ALWAYS_SHOW",
            "ALWAYS_HIDE",
            "TEXT_BASED",
            "ISO_DATETIME",
            "RELATIVE_TIME",
            "DATETIME_24HR",
        }

        for category, rule in DEFAULT_FILTER_RULES.items():
            filter_type = rule.get("filter_type")
            assert filter_type in valid_types, f"Unknown filter type '{filter_type}' for {category}"

    def test_can_process_all_default_rules(self):
        """Test that service can process all default rules without errors"""
        current_time = datetime(2025, 12, 27, 10, 0, 0)
        service = PPVFilterService(current_time=current_time)

        for category, rule in DEFAULT_FILTER_RULES.items():
            # Should not raise exception
            should_show, _ = service.should_show_channel("Test Event", category, rule)
            # Result depends on rule and channel name, just verify no crash
            assert isinstance(should_show, bool)


class TestCombinedScenarios:
    """Test realistic combined scenarios"""

    def test_espn_plus_ppv_with_real_channel_name(self):
        """Test ESPN+ PPV with realistic channel name"""
        current_time = datetime(2025, 12, 27, 0, 0, 0)
        service = PPVFilterService(current_time=current_time)

        channel_name = (
            "US (ESPN+ 001) | Adelaide United vs. Western Sydney Wanderers FC Dec 27 3:35AM ET (2025-12-27 03:35:06)"
        )
        rule = DEFAULT_FILTER_RULES["US| ESPN+ PPV"]

        should_show, metadata = service.should_show_channel(channel_name, "US| ESPN+ PPV", rule)
        assert should_show is True
        assert metadata is not None
        assert "Adelaide United" in metadata["event_name"] or metadata["event_name"] == "Event"

    def test_boxing_ppv_without_explicit_date(self):
        """Test boxing PPV showing even without explicit date"""
        current_time = datetime(2025, 1, 15, 10, 0, 0)
        sync_date = date(2025, 1, 15)
        service = PPVFilterService(current_time=current_time, sync_date=sync_date)

        channel_name = "Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK / 6PM ET"
        rule = {
            "filter_type": "DATETIME_24HR",
            "allow_no_date": True,
            "provider_name": "Boxing",
        }

        should_show, metadata = service.should_show_channel(channel_name, "UK| BOXING PPV", rule)
        assert should_show is True

    def test_offline_channel_always_hidden(self):
        """Test that offline channels are always hidden regardless of rule"""
        current_time = datetime(2025, 12, 27, 0, 0, 0)
        service = PPVFilterService(current_time=current_time)

        # Even with ALWAYS_SHOW rule, universal markers should hide it
        channel_name = "Some Channel - OFFLINE"
        rule = {"filter_type": "ALWAYS_SHOW"}

        should_show, _ = service.should_show_channel(channel_name, "US| TEST", rule)
        # Universal markers are checked first, before filter rules
        # This tests that _is_non_event_channel is called first
        assert should_show is False
