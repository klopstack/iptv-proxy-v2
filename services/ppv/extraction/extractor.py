"""PPVEventExtractor — thin coordinator for channel name parsing."""

import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

from services.datetime_utils import parse_title_timezone
from services.ppv.extraction import competitors, patterns
from services.ppv.extraction.date_strategies import DEFAULT_DATE_STRATEGIES
from services.ppv.extraction.date_strategies.base import parse_date_with_strategies
from services.ppv.extraction.types import MatchupInfo


class PPVEventExtractor:
    """Extracts event information from PPV channel names using regex patterns."""

    SPORT_PATTERN = patterns.SPORT_PATTERN
    TOURNAMENT_STRUCTURE_PATTERN = patterns.TOURNAMENT_STRUCTURE_PATTERN
    COMPETITOR_PATTERN = patterns.COMPETITOR_PATTERN
    TRAILING_TIME_PATTERN = patterns.TRAILING_TIME_PATTERN
    NO_EVENT_PATTERN = patterns.NO_EVENT_PATTERN
    DATE_PATTERN = patterns.DATE_PATTERN
    ISO_DATE_PATTERN = patterns.ISO_DATE_PATTERN
    ISO_PIPE_DATE_PATTERN = patterns.ISO_PIPE_DATE_PATTERN
    ISO_PAREN_DATETIME_PATTERN = patterns.ISO_PAREN_DATETIME_PATTERN
    DDMM_DATE_PATTERN = patterns.DDMM_DATE_PATTERN
    WEEKDAY_PATTERN = patterns.WEEKDAY_PATTERN
    TIME_ONLY_PATTERN = patterns.TIME_ONLY_PATTERN
    STOP_TIME_PATTERN = patterns.STOP_TIME_PATTERN
    PIPE_DATE_PATTERN = patterns.PIPE_DATE_PATTERN
    _COUNTRY_PREFIX_RE = patterns.COUNTRY_PREFIX_RE
    _PROVIDER_SLOT_RE = patterns.PROVIDER_SLOT_RE
    _BARE_PPV_SLOT_RE = patterns.BARE_PPV_SLOT_RE

    def __init__(self, current_date: Optional[datetime] = None, date_strategies: Any = None):
        self.current_date = current_date or datetime.now()
        self.current_year = self.current_date.year
        self._date_strategies = date_strategies if date_strategies is not None else DEFAULT_DATE_STRATEGIES

    def is_placeholder(self, channel_name: str) -> bool:
        return competitors.is_placeholder(channel_name)

    def is_inactive_channel(self, channel_name: str) -> bool:
        return competitors.is_inactive_channel(channel_name)

    def is_date_far_future(self, event_date: datetime) -> bool:
        if event_date.year >= 2098:
            return True
        max_future = self.current_date + timedelta(days=365)
        return event_date > max_future

    def extract_sport(self, channel_name: str) -> Tuple[Optional[str], str]:
        return competitors.extract_sport(channel_name)

    def _clean_tournament_structure(self, channel_name: str) -> str:
        return competitors.clean_tournament_structure(channel_name)

    @staticmethod
    def _strip_provider_prefix(name: str) -> str:
        return competitors.strip_provider_prefix(name)

    @staticmethod
    def extract_country_prefix(name: str) -> Optional[str]:
        return competitors.extract_country_prefix(name)

    def _detect_separator(self, cleaned_name: str) -> Optional[str]:
        return competitors.detect_separator(cleaned_name)

    def _feed_region_code(
        self,
        channel_name: str,
        category_name: Optional[str] = None,
    ) -> Optional[str]:
        return competitors.feed_region_code(channel_name, category_name)

    def extract_matchup(
        self,
        channel_name: str,
        *,
        category_name: Optional[str] = None,
    ) -> Optional[MatchupInfo]:
        return competitors.extract_matchup(channel_name, category_name=category_name)

    def extract_competitors(self, channel_name: str) -> Optional[Tuple[str, str]]:
        return competitors.extract_competitors(channel_name)

    @staticmethod
    def has_iso_paren_utc_datetime(channel_name: str) -> bool:
        return bool(re.search(patterns.ISO_PAREN_DATETIME_PATTERN, channel_name, re.IGNORECASE))

    @staticmethod
    def _is_milb_channel(channel_name: str) -> bool:
        return bool(re.search(r"\bMiLB\b|\bMILB\b|:Milb\s+\d", channel_name or "", re.IGNORECASE))

    def extract_date(self, channel_name: str) -> Optional[datetime]:
        return parse_date_with_strategies(
            channel_name,
            self._date_strategies,
            current_date=self.current_date,
            current_year=self.current_year,
            is_date_far_future=self.is_date_far_future,
        )

    def extract_weekday(self, channel_name: str) -> Optional[str]:
        match = re.search(patterns.WEEKDAY_PATTERN, channel_name, re.IGNORECASE)
        if match:
            return match.group(1).lower()
        return None

    def extract_time_only(self, channel_name: str) -> Optional[Tuple[int, int, Optional[str]]]:
        match = re.search(patterns.TIME_ONLY_PATTERN, channel_name, re.IGNORECASE)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            ampm = match.group(3).lower() if match.group(3) else None
            return (hour, minute, ampm)
        return None

    @staticmethod
    def extract_stop_time(channel_name: str) -> Optional[datetime]:
        match = re.search(patterns.STOP_TIME_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        try:
            ts = match.group(1).strip()
            if ts.count(":") == 2:
                return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            return datetime.strptime(ts, "%Y-%m-%d %H:%M")
        except ValueError:
            return None

    def infer_date_from_time(self, hour: int, minute: int, ampm: Optional[str] = None) -> datetime:
        from services.ppv.extraction.date_anchor import apply_ampm

        hour, minute = apply_ampm(int(hour), int(minute), ampm)
        return self.current_date.replace(hour=hour, minute=minute, second=0, microsecond=0)

    def infer_date_from_weekday(self, weekday: str) -> Optional[datetime]:
        weekday = weekday.lower()
        weekday_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        if weekday not in weekday_names:
            return None

        target_weekday = weekday_names.index(weekday)
        current_weekday = self.current_date.weekday()

        days_ahead = target_weekday - current_weekday
        if days_ahead <= 0:
            days_ahead += 7

        target_date = self.current_date + timedelta(days=days_ahead)
        return target_date.replace(hour=0, minute=0, second=0, microsecond=0)

    def combine_date_and_time(self, date: datetime, hour: int, minute: int, ampm: Optional[str] = None) -> datetime:
        hour = int(hour)
        minute = int(minute)

        if ampm:
            ampm = ampm.lower()
            if ampm == "pm" and hour != 12:
                hour += 12
            elif ampm == "am" and hour == 12:
                hour = 0

        date_midnight = date.replace(hour=0, minute=0, second=0, microsecond=0)
        return date_midnight + timedelta(hours=hour, minutes=minute)

    def extract_all(self, channel_name: str) -> Dict[str, Any]:
        inline_sport, _ = self.extract_sport(channel_name)
        country_prefix = self.extract_country_prefix(channel_name)
        result: Dict[str, Any] = {
            "is_placeholder": self.is_placeholder(channel_name),
            "is_inactive": self.is_inactive_channel(channel_name),
            "competitors": None,
            "competitors_format": None,
            "competitors_players": None,
            "sport": inline_sport,
            "country_prefix": country_prefix,
            "date": None,
            "weekday": None,
            "time_only": None,
            "timezone": None,
            "matchup": None,
            "raw_name": channel_name,
            "inferred_how": None,
        }

        if result["is_placeholder"] or result["is_inactive"]:
            return result

        detail = competitors.extract_competitors_detail(channel_name)
        if detail:
            result["competitors"] = (detail.side1, detail.side2)
            result["competitors_format"] = detail.format
            result["competitors_players"] = detail.players

        channel_tz = parse_title_timezone(channel_name)
        result["timezone"] = channel_tz
        result["matchup"] = self.extract_matchup(channel_name)

        iso_match = re.search(patterns.ISO_DATE_PATTERN, channel_name, re.IGNORECASE)
        if iso_match:
            year = iso_match.group(1)
            if int(year) >= 2098:
                result["inferred_how"] = "date_too_far_future"
                return result

        full_date = self.extract_date(channel_name)
        if full_date:
            if self.is_date_far_future(full_date):
                result["inferred_how"] = "date_too_far_future"
                return result

            result["date"] = full_date
            if re.search(patterns.ISO_PAREN_DATETIME_PATTERN, channel_name, re.IGNORECASE):
                if self._is_milb_channel(channel_name):
                    result["inferred_how"] = "iso_paren_local"
                else:
                    result["timezone"] = "UTC"
                    result["inferred_how"] = "iso_paren_utc"
            else:
                result["inferred_how"] = "full_date"
            return result

        weekday = self.extract_weekday(channel_name)
        time_only = self.extract_time_only(channel_name)

        if weekday and time_only:
            hour, minute, ampm = time_only
            weekday_date = self.infer_date_from_weekday(weekday)
            if weekday_date:
                result["date"] = self.combine_date_and_time(weekday_date, hour, minute, ampm)
                result["weekday"] = weekday
                result["time_only"] = time_only
                result["inferred_how"] = "weekday_plus_time"
                return result

        if time_only:
            hour, minute, ampm = time_only
            result["date"] = self.infer_date_from_time(hour, minute, ampm)
            result["time_only"] = time_only
            result["inferred_how"] = "time_only_inferred_date"
            return result

        if weekday:
            weekday_date = self.infer_date_from_weekday(weekday)
            if weekday_date:
                result["date"] = weekday_date
                result["weekday"] = weekday
                result["inferred_how"] = "weekday_only"
                return result

        return result

    def _clean_team_name(self, name: str) -> str:
        return competitors.clean_team_name(name)

    def _is_valid_team_name(self, name: str) -> bool:
        return competitors.is_valid_team_name(name)

    def _month_to_num(self, month_str: str) -> int:
        return patterns.MONTH_ABBR_TO_NUM.get(month_str.lower(), 1)
