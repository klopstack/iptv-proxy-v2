"""
Parametrized PPV detection tests (TODO 64).

Single source of truth for category, placeholder, channel, and event-title helpers.
Reverse matcher integration tests: tests/test_reverse_event_matcher/
"""

import re

import pytest

from models import Account, Category, Channel, db
from services.epg.constants import PPV_PLACEHOLDER_PATTERNS
from services.ppv.detection import get_ppv_event_title, is_ppv_category, is_ppv_channel, is_ppv_placeholder_name

# --- is_ppv_category ---

PPV_CATEGORY_CASES = [
    ("UK| DAZN PPV", True),
    ("US| ESPN+ PPV", True),
    ("NL| MAX PPV", True),
    ("UK| PAY-PER-VIEW", True),
    ("US| Pay Per View", True),
    ("PAY-PER-VIEW EVENTS", True),
    ("uk| dazn ppv", True),
    ("Uk| DaZn PpV", True),
    ("UK| SPORTS", False),
    ("US| ENTERTAINMENT", False),
    ("MOVIES", False),
    ("", False),
    (None, False),
]

# --- is_ppv_placeholder_name (merged from epg_service + visibility suites) ---

PPV_PLACEHOLDER_CASES = [
    # NO EVENT STREAMING / SCHEDULED
    ("NO EVENT STREAMING", True),
    ("- NO EVENT STREAMING -", True),
    ("UK: DAZN PPV 1 - NO EVENT STREAMING -", True),
    ("US: ESPN PLUS 01 PPV - NO EVENT STREAMING", True),
    ("UK: DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE", True),
    ("NL: MAX PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE", True),
    ("NO EVENT SCHEDULED", True),
    ("PPV 1 - NO EVENT SCHEDULED", True),
    ("EVENT 01 - NO SCHEDULED EVENT", True),
    ("no event streaming", True),
    # Numbered slots
    ("PPV 1", True),
    ("PPV 2", True),
    ("PPV-01", True),
    ("ppv 1", True),
    ("UK: PPV 3", True),
    ("UK: VIDIO EVENT 1", True),
    ("UK: MONO MAX EVENT 5", True),
    ("EVENT 1", True),
    ("EVENT 14", True),
    ("EVENT 99", True),
    # Colon / dash empty slots
    ("UFC 09:", True),
    ("NBA 10 -", True),
    (":Viaplay NL  14", True),
    (":MAX NL  05", True),
    (":MAX US 03", True),
    (":ESPN UK 05", True),
    # TBA / offline
    ("TBA", True),
    ("TBD", True),
    ("OFFLINE", True),
    ("COMING SOON", True),
    # Fixtures / regional slots
    ("GaaGo Fixtures 10:", True),
    ("Gaa++ Fixtures 07:", True),
    ("NIFL 5 |", True),
    ("Florugby 00", True),
    ("DIRTVISION 03", True),
    ("GOLF 10", True),
    ("GOLF 10 HD", True),
    ("US: DIRTVISION 03", True),
    ("GOLF 1", True),
    # Empty
    ("", True),
    (None, True),
    # Active events (not placeholders)
    ("UFC 300: Jones vs Miocic", False),
    ("UFC 300: Main Event", False),
    ("UFC 300 - Jones vs Miocic", False),
    ("BOXING: Fury vs Joshua", False),
    ("NBA Finals: Lakers vs Celtics", False),
    ("WWE Wrestlemania 40", False),
    ("Canelo vs Charlo Live", False),
    ("Canelo vs Crawford", False),
    ("AEW All In 2024", False),
    ("Bellator 300", False),
    ("DAZN: Anthony Joshua Fight Night", False),
    ("WWE Raw Live", False),
    ("UK: DAZN PPV 3 - EAST CAROLINA @ NORTH CAROLINA | Tue 23 Dec 01:50", False),
    ("LOI 1 | Shamrock Rovers v Cork City start:2025-11-09 14:45:00", False),
    ("EPL 01: 20:00 Manchester United vs Newcastle United", False),
]


@pytest.mark.parametrize("name,expected", PPV_CATEGORY_CASES)
def test_is_ppv_category(name, expected):
    assert is_ppv_category(name) is expected


@pytest.mark.parametrize("name,expected", PPV_PLACEHOLDER_CASES)
def test_is_ppv_placeholder_name(name, expected):
    assert is_ppv_placeholder_name(name) is expected


def test_ppv_placeholder_patterns_are_valid_regex():
    for pattern in PPV_PLACEHOLDER_PATTERNS:
        re.compile(pattern)


class TestIsPpvChannel:
    def test_ppv_channel_with_ppv_category(self, app):
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="PPV 1", category_id=category.id)
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is True

    def test_non_ppv_channel(self, app):
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| SPORTS")
            db.session.add(category)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="Sky Sports 1", category_id=category.id)
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is False

    def test_ppv_channel_with_no_category(self, app):
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            channel = Channel(account_id=account.id, stream_id="456", name="PPV 1", category_id=None)
            db.session.add(channel)
            db.session.commit()

            assert is_ppv_channel(channel) is False


class TestGetPpvEventTitle:
    def test_active_ppv_channel_returns_title(self, app):
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="456",
                name="UFC 300: Jones vs Miocic",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            assert get_ppv_event_title(channel) == "UFC 300: Jones vs Miocic"

    def test_placeholder_returns_none(self, app):
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="456",
                name="PPV 1 - NO EVENT STREAMING",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            assert get_ppv_event_title(channel) is None

    def test_empty_name_returns_none(self, app):
        with app.app_context():
            channel = Channel(account_id=1, stream_id="1001", name="", is_active=True)
            assert get_ppv_event_title(channel) is None

    def test_whitespace_stripped(self, app):
        with app.app_context():
            account = Account(name="Test", server="http://test.com", username="test", password="test")
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="123", category_name="UK| DAZN PPV")
            db.session.add(category)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="456",
                name="  UFC 300: Jones vs Miocic  ",
                category_id=category.id,
            )
            db.session.add(channel)
            db.session.commit()

            assert get_ppv_event_title(channel) == "UFC 300: Jones vs Miocic"
