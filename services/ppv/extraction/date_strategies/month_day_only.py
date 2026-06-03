"""Month and day without time: Oct 18, January 1st."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.date_anchor import resolve_month_day_datetime
from services.ppv.extraction.patterns import DATE_PATTERN, MONTH_ABBR_TO_NUM

_MONTH_ONLY_PATTERN = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)

_FULL_MONTH_TO_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

_FULL_MONTH_ONLY_PATTERN = re.compile(
    r"\b(January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+(\d{1,2})(?:st|nd|rd|th)?\b",
    re.IGNORECASE,
)


class MonthDayOnlyDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        if re.search(DATE_PATTERN, channel_name, re.IGNORECASE):
            return None

        match = _MONTH_ONLY_PATTERN.search(channel_name)
        if match:
            month = MONTH_ABBR_TO_NUM.get(match.group(1).lower())
            day = int(match.group(2))
            if month:
                return resolve_month_day_datetime(month, day, 0, 0, reference=current_date)

        match = _FULL_MONTH_ONLY_PATTERN.search(channel_name)
        if match:
            month = _FULL_MONTH_TO_NUM.get(match.group(1).lower())
            day = int(match.group(2))
            if month:
                return resolve_month_day_datetime(month, day, 0, 0, reference=current_date)

        return None
