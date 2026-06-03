"""Pipe-delimited weekday + date: | Sat 31 May 19:05."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.patterns import MONTH_ABBR_TO_NUM, PIPE_DATE_PATTERN


class PipeWeekdayDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(PIPE_DATE_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        day_str, month_abbr, hour_str, minute_str = match.groups()
        month = MONTH_ABBR_TO_NUM.get(month_abbr.lower(), 1)
        try:
            dt = datetime(current_year, month, int(day_str), int(hour_str), int(minute_str))
            today = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            if dt.replace(hour=0, minute=0, second=0, microsecond=0) < today:
                dt = dt.replace(year=current_year + 1)
            return dt
        except ValueError:
            return None
