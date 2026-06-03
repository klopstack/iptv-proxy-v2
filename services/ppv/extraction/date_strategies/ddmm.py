"""European DD/MM date: 24/10 16:00, 15-11 20:30, 05/03 8:30pm."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.date_anchor import apply_ampm
from services.ppv.extraction.patterns import DDMM_DATE_PATTERN


class DdMmDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(DDMM_DATE_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        year_str, day, month, hour, minute, ampm = match.groups()
        try:
            hour, minute = apply_ampm(int(hour), int(minute), ampm)
            year_match = None
            if year_str:
                year = int(year_str)
            else:
                text_before_date = channel_name[: match.start()]
                for m in re.finditer(r"\b(\d{4})\b", text_before_date):
                    year_match = m
                year = int(year_match.group(1)) if year_match else current_year

            parsed = datetime(year, int(month), int(day), hour, minute)

            if not year_str and year_match is None and (parsed - current_date).days < -7:
                parsed = datetime(year + 1, int(month), int(day), int(hour), int(minute))

            return parsed
        except ValueError:
            return None
