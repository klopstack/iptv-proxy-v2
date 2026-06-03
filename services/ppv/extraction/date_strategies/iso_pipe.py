"""Pipe-delimited ISO date: 2026-06-02 | 17:00."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.patterns import ISO_PIPE_DATE_PATTERN


class IsoPipeDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(ISO_PIPE_DATE_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        year, month, day, hour, minute = match.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
        except ValueError:
            return None
