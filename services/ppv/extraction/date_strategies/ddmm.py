"""European DD/MM date: 24/10 16:00."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.patterns import DDMM_DATE_PATTERN


class DdMmDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(DDMM_DATE_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        year_str, day, month, hour, minute = match.groups()
        try:
            if year_str:
                year = int(year_str)
            else:
                text_before_date = channel_name[: match.start()]
                year_match = None
                for m in re.finditer(r"\b(\d{4})\b", text_before_date):
                    year_match = m
                year = int(year_match.group(1)) if year_match else current_year

            return datetime(year, int(month), int(day), int(hour), int(minute))
        except ValueError:
            return None
