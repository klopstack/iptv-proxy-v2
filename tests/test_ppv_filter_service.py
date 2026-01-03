"""
Tests for PPV Filter Service - Phase 1 & 2 Implementation

Phase 1: Category-specific handling (boxing, wrestling, etc.) show events without explicit times
Phase 2: 24-hour time format support (HH:MM and HH.MM formats)
"""

from datetime import date, datetime, time

from services.ppv_filter_service import PPVFilterService


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
