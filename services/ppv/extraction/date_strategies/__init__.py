"""Ordered date format strategies for channel name parsing."""

from services.ppv.extraction.date_strategies.ddmm import DdMmDateStrategy
from services.ppv.extraction.date_strategies.iso_date import IsoDateStrategy
from services.ppv.extraction.date_strategies.iso_paren import IsoParenDateStrategy
from services.ppv.extraction.date_strategies.iso_pipe import IsoPipeDateStrategy
from services.ppv.extraction.date_strategies.month_day import MonthDayDateStrategy
from services.ppv.extraction.date_strategies.pipe_weekday import PipeWeekdayDateStrategy

DEFAULT_DATE_STRATEGIES = [
    IsoParenDateStrategy(),
    IsoPipeDateStrategy(),
    IsoDateStrategy(),
    DdMmDateStrategy(),
    PipeWeekdayDateStrategy(),
    MonthDayDateStrategy(),
]

__all__ = [
    "DEFAULT_DATE_STRATEGIES",
    "DdMmDateStrategy",
    "IsoDateStrategy",
    "IsoParenDateStrategy",
    "IsoPipeDateStrategy",
    "MonthDayDateStrategy",
    "PipeWeekdayDateStrategy",
]
