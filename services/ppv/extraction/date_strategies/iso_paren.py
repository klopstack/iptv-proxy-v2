"""Parenthetical ISO datetime: (2026-06-03 02:00:00)."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.patterns import ISO_PAREN_DATETIME_PATTERN


class IsoParenDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(ISO_PAREN_DATETIME_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        year, month, day, hour, minute, second = match.groups()
        try:
            sec = int(second) if second else 0
            return datetime(int(year), int(month), int(day), int(hour), int(minute), sec)
        except ValueError:
            return None
