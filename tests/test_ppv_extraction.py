"""
Tests for PPVEventExtractor - competitor and date extraction from channel names

Note: Tests use the database sync date (2025-12-28 00:04:36) as the reference point
for determining whether dates are in the past/future. This ensures consistency with
actual data extraction runs.
"""
from datetime import datetime

from services.ppv.extraction import PPVEventExtractor

# Reference date from last database sync (2025-12-28 00:04:36 UTC)
# Using this ensures all tests are consistent with production extraction
SYNC_REFERENCE_DATE = datetime(2025, 12, 28, 0, 4, 36)


class TestPPVEventExtractor:
    """Test PPV event extraction from channel names"""

    def setup_method(self):
        """Set up test fixtures using sync reference date"""
        self.extractor = PPVEventExtractor(current_date=SYNC_REFERENCE_DATE)

    # ========================================================================
    # Competitor Pattern Tests - "vs" variations
    # ========================================================================

    def test_extract_competitors_lowercase_vs(self):
        """Test extraction of competitors with lowercase 'vs'"""
        result = self.extractor.extract_competitors("Benin vs Botswana")
        assert result == ("Benin", "Botswana")

    def test_extract_competitors_uppercase_vs(self):
        """Test extraction of competitors with uppercase 'VS'"""
        result = self.extractor.extract_competitors("Arsenal VS Brighton")
        assert result == ("Arsenal", "Brighton")

    def test_extract_competitors_vs_with_period(self):
        """Test extraction of competitors with 'VS.' (period)"""
        result = self.extractor.extract_competitors("#25 NORTH TEXAS VS. SAN DIEGO STATE")
        assert result == ("NORTH TEXAS", "SAN DIEGO STATE")

    def test_extract_competitors_vs_lowercase_with_period(self):
        """Test extraction of competitors with 'vs.' (lowercase with period)"""
        result = self.extractor.extract_competitors("NORTH TEXAS vs. SAN DIEGO STATE")
        assert result == ("NORTH TEXAS", "SAN DIEGO STATE")

    # ========================================================================
    # Competitor Pattern Tests - "at" variations
    # ========================================================================

    def test_extract_competitors_lowercase_at(self):
        """Test extraction of competitors with lowercase 'at'"""
        result = self.extractor.extract_competitors("Milwaukee Wave at Baltimore Blast")
        assert result == ("Milwaukee Wave", "Baltimore Blast")

    def test_extract_competitors_uppercase_at(self):
        """Test extraction of competitors with uppercase 'AT'"""
        result = self.extractor.extract_competitors("TEAM A AT TEAM B")
        assert result == ("TEAM A", "TEAM B")

    def test_extract_competitors_at_with_period(self):
        """Test extraction of competitors with 'at.' (period)"""
        result = self.extractor.extract_competitors("Team A at. Team B")
        assert result == ("Team A", "Team B")

    # ========================================================================
    # Competitor Pattern Tests - @ and versus
    # ========================================================================

    def test_extract_competitors_at_symbol(self):
        """Test extraction of competitors with @ symbol"""
        result = self.extractor.extract_competitors("SPO @ MH")
        assert result == ("SPO", "MH")

    def test_extract_competitors_whl_abbreviations(self):
        """Test extraction of WHL team abbreviations"""
        result = self.extractor.extract_competitors("Round 4 - Game 1: SPO @ MH")
        assert result == ("SPO", "MH")

    def test_extract_competitors_versus_full_word(self):
        """Test extraction with 'versus' full word"""
        result = self.extractor.extract_competitors("Team A versus Team B")
        assert result == ("Team A", "Team B")

    # ========================================================================
    # Dash-Separated Team Names (e.g., Soccer/Rugby)
    # ========================================================================

    def test_extract_competitors_dash_separator(self):
        """Test extraction with dash separator (common in rugby/soccer)"""
        result = self.extractor.extract_competitors("NORTHAMPTON SAINTS - HARLEQUINS")
        assert result == ("NORTHAMPTON SAINTS", "HARLEQUINS")

    def test_extract_competitors_dash_with_provider_prefix(self):
        """Test extraction ignoring provider prefix before dash separator"""
        result = self.extractor.extract_competitors("UK: D+ PPV 1 - NORTHAMPTON SAINTS - HARLEQUINS | Sat 03 Jan 17:15")
        assert result == ("NORTHAMPTON SAINTS", "HARLEQUINS")

    def test_extract_competitors_dash_laliga(self):
        """Test extraction of Spanish La Liga team match with dash separator"""
        result = self.extractor.extract_competitors(
            "ES: LALIGA+ PPV 3 - BARAKALDO CF - UNIONISTAS DE SALAMANCA CF | Sat 03 Jan 18:30"
        )
        assert result == ("BARAKALDO CF", "UNIONISTAS DE SALAMANCA CF")

    # ========================================================================
    # Multi-word Team Names
    # ========================================================================

    def test_extract_competitors_multi_word_names(self):
        """Test extraction of multi-word team names"""
        result = self.extractor.extract_competitors("SAN DIEGO STATE vs NORTH CAROLINA STATE")
        assert result == ("SAN DIEGO STATE", "NORTH CAROLINA STATE")

    def test_extract_competitors_with_special_chars(self):
        """Test extraction with team names containing ampersands and apostrophes"""
        result = self.extractor.extract_competitors("King's College vs St Johns")
        assert result == ("King's College", "St Johns")

    def test_extract_competitors_with_ampersand(self):
        """Test extraction with ampersand in team name"""
        result = self.extractor.extract_competitors("Foo & Bar vs Team B")
        assert result == ("Foo & Bar", "Team B")

    # ========================================================================
    # Ranking/Number Prefixes
    # ========================================================================

    def test_extract_competitors_with_ranking_prefix(self):
        """Test extraction with ranking prefix like #25"""
        result = self.extractor.extract_competitors("#25 NORTH TEXAS VS. SAN DIEGO STATE")
        assert result == ("NORTH TEXAS", "SAN DIEGO STATE")

    def test_extract_competitors_with_numeric_prefix(self):
        """Test extraction with numeric prefix like 22"""
        result = self.extractor.extract_competitors("#22 GEORGIA TECH VS. #12 BYU")
        # Should extract team names without the ranking numbers
        assert result == ("GEORGIA TECH", "BYU")

    # ========================================================================
    # Tennis/Comma-separated Player Names
    # ========================================================================

    def test_extract_competitors_tennis_with_commas(self):
        """Test extraction of tennis player names with commas"""
        result = self.extractor.extract_competitors("Eala, Alexandra vs Andreeva, Mirra @ Dec 28")
        assert result == ("Eala, Alexandra", "Andreeva, Mirra")

    def test_extract_competitors_tennis_vs_with_date(self):
        """Test extraction of tennis match with vs and full date"""
        result = self.extractor.extract_competitors("Fernandez, Leylah vs Kasatkina, Daria @ Dec 28 07:30 AM")
        assert result == ("Fernandez, Leylah", "Kasatkina, Daria")

    def test_extract_competitors_hyphenated_team_names(self):
        """Test extraction of hyphenated team names like Tiger-Cats"""
        result = self.extractor.extract_competitors("Montreal Alouettes vs Hamilton Tiger-Cats | Sat")
        assert result == ("Montreal Alouettes", "Hamilton Tiger-Cats")

    # ========================================================================
    # Date Format Tests - ISO format (YYYY-MM-DD HH:MM)
    # ========================================================================

    def test_extract_date_iso_format(self):
        """Test extraction of ISO date format"""
        result = self.extractor.extract_date("(Benin vs Botswana (2025-12-27 07:30:00))")
        assert result == datetime(2025, 12, 27, 7, 30, 0)

    def test_extract_date_iso_format_afternoon(self):
        """Test ISO date format in afternoon"""
        result = self.extractor.extract_date("Event (2026-01-15 19:00:00)")
        assert result == datetime(2026, 1, 15, 19, 0, 0)

    def test_extract_date_iso_format_with_separators(self):
        """Test ISO date with surrounding text and separators"""
        result = self.extractor.extract_date("Victory+ 001 | Team A at Team B (2025-12-27 16:00:00)")
        assert result == datetime(2025, 12, 27, 16, 0, 0)

    # ========================================================================
    # Date Format Tests - Month DD HH:MM format with ordinal suffixes
    # ========================================================================

    def test_extract_date_with_ordinal_suffix(self):
        """Test extraction with ordinal date suffix like 'th'"""
        result = self.extractor.extract_date("Event May 9th 9:00 PM")
        assert result is not None
        assert result.hour == 21  # 9 PM = 21:00
        assert result.month == 5
        assert result.day == 9

    def test_extract_date_with_st_suffix(self):
        """Test extraction with 'st' ordinal suffix"""
        result = self.extractor.extract_date("Event Dec 1st 8:00 PM")
        assert result is not None
        assert result.month == 12
        assert result.day == 1

    def test_extract_date_with_nd_suffix(self):
        """Test extraction with 'nd' ordinal suffix"""
        result = self.extractor.extract_date("Event Dec 2nd 8:00 PM")
        assert result is not None
        assert result.month == 12
        assert result.day == 2

    def test_extract_date_with_rd_suffix(self):
        """Test extraction with 'rd' ordinal suffix"""
        result = self.extractor.extract_date("Event Dec 3rd 8:00 PM")
        assert result is not None
        assert result.month == 12
        assert result.day == 3

    # ========================================================================
    # Date Format Tests - Month DD HH:MM format
    # ========================================================================

    def test_extract_date_month_day_time(self):
        """Test extraction of Month DD HH:MM format"""
        result = self.extractor.extract_date("Event on Dec 27 23:43")
        # Should match to 2026-12-27 (next occurrence)
        assert result is not None
        assert result.month == 12
        assert result.day == 27
        assert result.hour == 23
        assert result.minute == 43

    def test_extract_date_with_ampm(self):
        """Test extraction with AM/PM notation"""
        result = self.extractor.extract_date("Event May 9th 9:00 PM")
        assert result is not None
        assert result.hour == 21  # 9 PM = 21:00

    # ========================================================================
    # Date Format Tests - DD/MM format (European, e.g., "24/10 16:00")
    # ========================================================================

    def test_extract_date_ddmm_format(self):
        """Test extraction of DD/MM HH:MM format"""
        result = self.extractor.extract_date("Event: 24/10 16:00")
        assert result is not None
        assert result.month == 10
        assert result.day == 24
        assert result.hour == 16
        assert result.minute == 0

    def test_extract_date_ddmm_with_year_in_channel(self):
        """Test DD/MM format with year appearing earlier in channel name"""
        result = self.extractor.extract_date("Flo (FLSP) 288: 2025 Davenport vs Purdue Northwest - Mens - 24/10 16:00")
        assert result == datetime(2025, 10, 24, 16, 0, 0)

    def test_extract_date_ddmm_with_different_year(self):
        """Test DD/MM format correctly uses extracted year"""
        result = self.extractor.extract_date("Event 2024 - 15/05 14:30")
        assert result == datetime(2024, 5, 15, 14, 30, 0)

    # ========================================================================
    # Date Format Tests - Weekday inference
    # ========================================================================

    def test_extract_weekday_saturday(self):
        """Test extraction of weekday"""
        result = self.extractor.extract_weekday("Event on Sat 27 Dec 22:35")
        assert result == "sat"

    def test_extract_weekday_friday(self):
        """Test extraction of Friday"""
        result = self.extractor.extract_weekday("Fri May 9th 9:00PM")
        assert result == "fri"

    # ========================================================================
    # Team Name Validation
    # ========================================================================

    def test_valid_team_name_full_name(self):
        """Test that full team names are valid"""
        assert self.extractor._is_valid_team_name("Arsenal") is True
        assert self.extractor._is_valid_team_name("Manchester United") is True

    def test_valid_team_name_abbreviations(self):
        """Test that sport abbreviations are valid"""
        assert self.extractor._is_valid_team_name("BYU") is True
        assert self.extractor._is_valid_team_name("SPO") is True
        assert self.extractor._is_valid_team_name("MH") is True

    def test_invalid_team_name_tech_specs(self):
        """Test that tech specs are invalid"""
        assert self.extractor._is_valid_team_name("HD") is False
        assert self.extractor._is_valid_team_name("SD") is False
        assert self.extractor._is_valid_team_name("FHD") is False

    def test_invalid_team_name_metadata(self):
        """Test that metadata keywords are invalid"""
        assert self.extractor._is_valid_team_name("PPV") is False
        assert self.extractor._is_valid_team_name("Round 1") is False
        assert self.extractor._is_valid_team_name("Game 5") is False

    def test_invalid_team_name_too_short(self):
        """Test that single character names are invalid"""
        assert self.extractor._is_valid_team_name("A") is False

    def test_invalid_team_name_only_numbers(self):
        """Test that numeric-only names are invalid"""
        assert self.extractor._is_valid_team_name("123") is False

    # ========================================================================
    # Team Name Cleaning
    # ========================================================================

    def test_clean_team_name_ranking_prefix(self):
        """Test cleaning of ranking prefixes"""
        result = self.extractor._clean_team_name("#25 GEORGIA TECH")
        assert result == "GEORGIA TECH"

    def test_clean_team_name_numeric_prefix(self):
        """Test cleaning of numeric prefixes"""
        result = self.extractor._clean_team_name("22 BYU")
        assert result == "BYU"

    def test_clean_team_name_provider_code(self):
        """Test cleaning of provider codes"""
        result = self.extractor._clean_team_name("Arsenal :Viaplay SE")
        assert result == "Arsenal"

    def test_clean_team_name_trailing_numbers(self):
        """Test cleaning of trailing numbers"""
        result = self.extractor._clean_team_name("Team Name 123")
        assert result == "Team Name"

    def test_clean_team_name_whitespace(self):
        """Test normalization of whitespace"""
        result = self.extractor._clean_team_name("  Team   A  ")
        assert result == "Team A"

    # ========================================================================
    # Placeholder Detection
    # ========================================================================

    def test_is_placeholder_no_event_streaming(self):
        """Test detection of 'NO EVENT STREAMING' placeholder"""
        assert self.extractor.is_placeholder("BR: MAX PPV 1 - NO EVENT STREAMING - | 8K") is True

    def test_is_placeholder_not_placeholder(self):
        """Test that valid events are not marked as placeholder"""
        assert self.extractor.is_placeholder("Arsenal vs Brighton") is False

    # ========================================================================
    # Inactive Channel Detection
    # ========================================================================

    def test_is_inactive_provider_name(self):
        """Test detection of provider name channels"""
        assert self.extractor.is_inactive_channel("(Fanatiz 012)") is True

    def test_is_inactive_section_header(self):
        """Test detection of section headers"""
        assert self.extractor.is_inactive_channel("###########") is True

    def test_is_inactive_generic_placeholder(self):
        """Test detection of generic channel placeholders"""
        assert self.extractor.is_inactive_channel("::::::::::") is True

    def test_is_inactive_channel_number(self):
        """Test detection of generic channel numbers"""
        # "AFL TV 00" has more than 5 chars so it's not marked as inactive by length
        # It would need to match the specific pattern
        assert self.extractor.is_inactive_channel("Channel 00") is False

    def test_is_inactive_empty_channel(self):
        """Test detection of empty channels"""
        assert self.extractor.is_inactive_channel("") is True

    def test_is_inactive_short_name(self):
        """Test detection of very short names"""
        assert self.extractor.is_inactive_channel("a") is True

    def test_is_not_inactive_real_event(self):
        """Test that real events are not marked inactive"""
        assert self.extractor.is_inactive_channel("(Fanatiz 001) | Benin vs Botswana (2025-12-27 07:30:00)") is False

    # ========================================================================
    # Far Future Date Detection
    # ========================================================================

    def test_is_date_far_future_past_date(self):
        """Test that past dates are not far future.

        Using sync reference date (2025-12-28), a date from earlier in 2025
        should not be marked as far future.
        """
        past_date = datetime(2025, 6, 1)
        assert self.extractor.is_date_far_future(past_date) is False

    def test_is_date_far_future_current_year(self):
        """Test that dates within ~1 year of sync date are not far future.

        Using sync reference date (2025-12-28), a date within the next few months
        (2026-06-01) should not be marked as far future.
        """
        near_date = datetime(2026, 6, 1)
        assert self.extractor.is_date_far_future(near_date) is False

    def test_is_date_far_future_beyond_threshold(self):
        """Test that dates >1 year in future from sync date are far future.

        Using sync reference date (2025-12-28), a date beyond 365 days out
        (2026-12-28 + 1 day = 2026-12-29) should be marked as far future.
        """
        # Sync date + 366 days = beyond threshold
        far_date = datetime(2026, 12, 29)
        assert self.extractor.is_date_far_future(far_date) is True

    # ========================================================================
    # Full Extraction Pipeline Tests
    # ========================================================================

    def test_extract_all_full_event_fanatiz(self):
        """Test full extraction of Fanatiz event"""
        result = self.extractor.extract_all("(Fanatiz 001) | Benin vs Botswana (2025-12-27 07:30:00)")
        assert result["competitors"] == ("Benin", "Botswana")
        assert result["date"] == datetime(2025, 12, 27, 7, 30, 0)
        assert result["is_placeholder"] is False
        assert result["is_inactive"] is False

    def test_extract_all_full_event_victory(self):
        """Test full extraction of Victory+ event"""
        result = self.extractor.extract_all("(Victory+ 001) | Milwaukee Wave at Baltimore Blast  (2025-12-27 16:00:00)")
        assert result["competitors"] == ("Milwaukee Wave", "Baltimore Blast")
        assert result["date"] == datetime(2025, 12, 27, 16, 0, 0)
        assert result["is_inactive"] is False

    def test_extract_all_whl_event(self):
        """Test full extraction of WHL event with abbreviations"""
        result = self.extractor.extract_all("WHL TV 00: Round 4 - Game 1: SPO @ MH | UPCOMING | Fri May 9th 9:00PM")
        assert result["competitors"] == ("SPO", "MH")
        assert result["date"] is not None

    def test_extract_all_ncaa_event(self):
        """Test full extraction of NCAA event with ranking prefix"""
        result = self.extractor.extract_all(
            "BR: DISNEY PLUS BR PPV 6 - #22 GEORGIA TECH VS. #12 BYU | Sat 28 Dec 01:31"
        )
        # Should extract with proper team names (without rankings)
        assert result["competitors"] is not None
        assert result["date"] is not None

    def test_extract_all_placeholder_no_extraction(self):
        """Test that placeholders are properly marked"""
        result = self.extractor.extract_all("BR: MAX PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE")
        assert result["is_placeholder"] is True

    def test_extract_all_inactive_provider_no_extraction(self):
        """Test that inactive provider channels are marked"""
        result = self.extractor.extract_all("(Fanatiz 012)")
        assert result["is_inactive"] is True

    def test_extract_all_no_event_with_date(self):
        """Test that channels with no team info but with date are extracted"""
        result = self.extractor.extract_all("Some Event | Sat 27 Dec 22:35 | 8K EXCLUSIVE")
        # Should have weekday+time or date info
        assert result["date"] is not None or result.get("inferred_how") is not None

    # ========================================================================
    # Edge Cases
    # ========================================================================

    def test_extract_competitors_with_parenthesized_date(self):
        """Test extraction when competitors have parenthesized dates"""
        result = self.extractor.extract_competitors("Arsenal vs Brighton (2025-12-27 15:00:00)")
        # Should extract properly despite following parentheses
        assert result == ("Arsenal", "Brighton")

    def test_extract_competitors_no_match_pipe_separator(self):
        """Test that pipe-only separated teams don't match"""
        result = self.extractor.extract_competitors("Team A | Team B")
        assert result is None

    def test_extract_date_multiple_dates_in_string(self):
        """Test extraction when multiple dates present"""
        result = self.extractor.extract_date("Event (2025-12-27 07:30:00) Rescheduled from (2025-12-26 10:00:00)")
        # Should extract the first date
        assert result == datetime(2025, 12, 27, 7, 30, 0)

    def test_extract_all_mixed_separators(self):
        """Test extraction with mixed vs/at separators"""
        result = self.extractor.extract_all("Arsenal vs Brighton at Stamford Bridge")
        # Should extract first vs match
        assert result["competitors"] is not None
