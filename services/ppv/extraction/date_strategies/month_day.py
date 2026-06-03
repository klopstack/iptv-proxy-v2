"""Month abbreviation date: Dec 27 19:00."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.patterns import DATE_PATTERN, MONTH_ABBR_TO_NUM


class MonthDayDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(DATE_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        month_str, day, hour, minute, ampm = match.groups()
        month = MONTH_ABBR_TO_NUM.get(month_str.lower(), 1)

        hour = int(hour)
        if ampm:
            ampm = ampm.upper()
            if ampm == "PM" and hour != 12:
                hour += 12
            elif ampm == "AM" and hour == 12:
                hour = 0

        try:
            dt = datetime(current_year, month, int(day), hour, int(minute))
            today = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            event_day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            if event_day < today:
                dt = dt.replace(year=current_year + 1)
            return dt
        except ValueError:
            return None
