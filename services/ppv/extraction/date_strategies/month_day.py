"""Month abbreviation date: Dec 27 19:00, @ Jun 3 11:00 AM."""

from datetime import datetime
from typing import Optional

from services.ppv.extraction.date_anchor import parse_month_day_anchor


class MonthDayDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        return parse_month_day_anchor(channel_name, current_date)
