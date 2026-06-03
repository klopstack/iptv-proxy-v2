"""Day before month: 28 Dec 8:00pm."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.date_anchor import resolve_month_day_datetime
from services.ppv.extraction.patterns import DAY_MONTH_TIME_PATTERN, MONTH_ABBR_TO_NUM


class DayMonthDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(DAY_MONTH_TIME_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        day, month_str, hour, minute, ampm = match.groups()
        month = MONTH_ABBR_TO_NUM.get(month_str.lower())
        if not month:
            return None
        return resolve_month_day_datetime(
            month,
            int(day),
            int(hour),
            int(minute),
            ampm=ampm,
            reference=current_date,
        )
