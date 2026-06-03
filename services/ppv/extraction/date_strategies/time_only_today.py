"""Trailing clock time anchored to the reference calendar day."""

from datetime import datetime
from typing import Optional

from services.ppv.extraction.date_anchor import time_only_on_reference_day


class TimeOnlyTodayDateStrategy:
    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        return time_only_on_reference_day(channel_name, current_date)
