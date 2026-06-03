"""Production date-extraction fixtures (TODO 120)."""

from datetime import datetime

import pytest

from services.ppv.extraction import PPVEventExtractor
from services.reverse_event_matcher.date_extractor import DateExtractor

REFERENCE = datetime(2026, 6, 3, 18, 0, 0)

PRODUCTION_FIXTURES = [
    pytest.param(
        "football-time-only",
        "Live Football 01: Charlton Athletic vs Leicester City 12:30pm",
        datetime(2026, 6, 3, 12, 30),
        id="football-time-only",
    ),
    pytest.param(
        "wcws-jun4",
        "#11 Texas Tech vs #2 Texas (WCWS Finals Game 1) @ Jun 4 01:55",
        datetime(2026, 6, 4, 1, 55),
        id="wcws-jun4",
    ),
    pytest.param(
        "tennis-jun3",
        "Tennis: Anna Kalinskaya vs Maja Chwalinska @ Jun 3 11:00 AM",
        datetime(2026, 6, 3, 11, 0),
        id="tennis-jun3",
    ),
    pytest.param(
        "boxing-no-date",
        "Boxing 1 : Oleksandr Usyk vs. Rico Verhoeven",
        None,
        id="boxing-no-date",
    ),
    pytest.param(
        "iso-peacock",
        "US (Peacock 001) | Away Feed: BAL at BOS (2026-06-03 18:30:00)",
        datetime(2026, 6, 3, 18, 30),
        id="iso-peacock",
    ),
    pytest.param(
        "albania-jun3",
        "Albania vs Israel @ Jun 3 20:50",
        datetime(2026, 6, 3, 20, 50),
        id="albania-jun3",
    ),
]


@pytest.fixture
def ppv_extractor():
    return PPVEventExtractor(current_date=REFERENCE)


@pytest.fixture
def date_extractor():
    return DateExtractor(reference_date=REFERENCE)


@pytest.mark.parametrize("fixture_id,channel_name,expected", PRODUCTION_FIXTURES)
def test_ppv_extractor_production_dates(ppv_extractor, fixture_id, channel_name, expected):
    assert ppv_extractor.extract_date(channel_name) == expected


@pytest.mark.parametrize("fixture_id,channel_name,expected", PRODUCTION_FIXTURES)
def test_date_extractor_production_dates(date_extractor, fixture_id, channel_name, expected):
    assert date_extractor.extract_date(channel_name) == expected


@pytest.mark.parametrize("fixture_id,channel_name,expected", PRODUCTION_FIXTURES)
def test_extractor_parity(ppv_extractor, date_extractor, fixture_id, channel_name, expected):
    ppv_date = ppv_extractor.extract_date(channel_name)
    de_date = date_extractor.extract_date(channel_name)
    assert ppv_date == de_date == expected
