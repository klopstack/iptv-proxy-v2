"""Ordered date format strategies for channel name parsing."""

from typing import List

from services.ppv.extraction.date_strategies.base import DateParseStrategy
from services.ppv.extraction.date_strategies.day_month import DayMonthDateStrategy
from services.ppv.extraction.date_strategies.ddmm import DdMmDateStrategy
from services.ppv.extraction.date_strategies.iso_date import IsoDateStrategy
from services.ppv.extraction.date_strategies.iso_paren import IsoParenDateStrategy
from services.ppv.extraction.date_strategies.iso_pipe import IsoPipeDateStrategy
from services.ppv.extraction.date_strategies.month_day import MonthDayDateStrategy
from services.ppv.extraction.date_strategies.month_day_only import MonthDayOnlyDateStrategy
from services.ppv.extraction.date_strategies.pipe_weekday import PipeWeekdayDateStrategy
from services.ppv.extraction.date_strategies.time_only_today import TimeOnlyTodayDateStrategy

DEFAULT_DATE_STRATEGIES: List[DateParseStrategy] = [
    IsoParenDateStrategy(),
    IsoPipeDateStrategy(),
    IsoDateStrategy(),
    DdMmDateStrategy(),
    PipeWeekdayDateStrategy(),
    DayMonthDateStrategy(),
    MonthDayDateStrategy(),
    MonthDayOnlyDateStrategy(),
    TimeOnlyTodayDateStrategy(),
]

__all__ = [
    "DEFAULT_DATE_STRATEGIES",
    "DayMonthDateStrategy",
    "DdMmDateStrategy",
    "IsoDateStrategy",
    "IsoParenDateStrategy",
    "IsoPipeDateStrategy",
    "MonthDayDateStrategy",
    "MonthDayOnlyDateStrategy",
    "PipeWeekdayDateStrategy",
    "TimeOnlyTodayDateStrategy",
]
