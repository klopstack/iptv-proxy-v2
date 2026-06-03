"""ISO date: YYYY-MM-DD HH:MM."""

import re
from datetime import datetime
from typing import Optional

from services.ppv.extraction.patterns import ISO_DATE_PATTERN


class IsoDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        match = re.search(ISO_DATE_PATTERN, channel_name, re.IGNORECASE)
        if not match:
            return None
        year, month, day, hour, minute = match.groups()
        try:
            return datetime(int(year), int(month), int(day), int(hour), int(minute))
        except ValueError:
            return None
