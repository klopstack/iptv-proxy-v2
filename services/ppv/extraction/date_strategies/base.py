"""Date parsing strategy protocol and registry."""

from datetime import datetime
from typing import Callable, List, Optional, Protocol


class DateParseStrategy(Protocol):
    """Parse a datetime from channel name text, or return None."""

    def parse(self, channel_name: str, *, current_date: datetime, current_year: int) -> Optional[datetime]:
        ...


def parse_date_with_strategies(
    channel_name: str,
    strategies: List[DateParseStrategy],
    *,
    current_date: datetime,
    current_year: int,
    is_date_far_future: Callable[[datetime], bool],
) -> Optional[datetime]:
    """Try each strategy in order; skip far-future placeholder dates."""
    for strategy in strategies:
        dt = strategy.parse(channel_name, current_date=current_date, current_year=current_year)
        if dt is None:
            continue
        if is_date_far_future(dt):
            return None
        return dt
    return None
