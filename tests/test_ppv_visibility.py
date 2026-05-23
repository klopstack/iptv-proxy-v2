"""
Tests for PPV channel visibility based on channel name detection

PPV channels from IPTV providers have placeholder names like "PPV 1" when no
event is scheduled. When an event IS scheduled, the provider changes the
channel name to the event title (e.g., "UFC 300: Main Event").

These tests verify the name-based detection logic.
"""

from models import Account, Channel, ChannelTag, Tag, db
from services.epg.constants import PPV_PLACEHOLDER_PATTERNS
from services.epg.ppv import get_ppv_event_title, is_ppv_placeholder_name


class TestPPVPlaceholderDetection:
    """Test PPV placeholder name pattern detection

    PPV channels from real IPTV providers typically have specific formats:
    - "UK: DAZN PPV 1 ᴿᴬᵂ" or "US: ESPN PLUS 01 PPV" when inactive
    - "UK: DAZN PPV 1 - UFC 300: Jones vs Miocic" when active
    - "NO EVENT STREAMING" markers are very common
    """

    def test_no_event_streaming_placeholder(self):
        """Test detection of 'NO EVENT STREAMING' markers (most common)"""
        # These are the most common placeholder formats from providers
        assert is_ppv_placeholder_name("NO EVENT STREAMING") is True
        assert is_ppv_placeholder_name("- NO EVENT STREAMING -") is True
        assert is_ppv_placeholder_name("UK: DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE") is True
        assert is_ppv_placeholder_name("NL: MAX PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE") is True
        assert is_ppv_placeholder_name("NO EVENT SCHEDULED") is True

    def test_event_number_only_placeholder(self):
        """Test detection of numbered event channels without event info"""
        # These are channels with just numbers, no actual event scheduled
        assert is_ppv_placeholder_name("UK: VIDIO EVENT 1") is True
        assert is_ppv_placeholder_name("UK: MONO MAX EVENT 5") is True
        assert is_ppv_placeholder_name("EVENT 14") is True

    def test_empty_slot_placeholder(self):
        """Test detection of empty PPV slots with trailing colon/dash"""
        # These indicate no event is scheduled
        assert is_ppv_placeholder_name("UFC 09:") is True
        assert is_ppv_placeholder_name("NBA 10 -") is True
        assert is_ppv_placeholder_name(":MAX NL  05") is True
        assert is_ppv_placeholder_name(":Viaplay NL  14") is True

    def test_tba_offline_placeholder(self):
        """Test detection of TBA/Offline placeholders"""
        assert is_ppv_placeholder_name("TBA") is True
        assert is_ppv_placeholder_name("TBD") is True
        assert is_ppv_placeholder_name("OFFLINE") is True
        assert is_ppv_placeholder_name("COMING SOON") is True

    def test_empty_fixture_placeholder(self):
        """Test detection of empty fixture slots"""
        assert is_ppv_placeholder_name("GaaGo Fixtures 10:") is True
        assert is_ppv_placeholder_name("Gaa++ Fixtures 07:") is True

    def test_empty_name_is_placeholder(self):
        """Test that empty/None name is treated as placeholder"""
        assert is_ppv_placeholder_name("") is True
        assert is_ppv_placeholder_name(None) is True

    def test_actual_event_not_placeholder(self):
        """Test that actual event titles are NOT detected as placeholders"""
        # These should NOT be detected as placeholders (active events)
        assert is_ppv_placeholder_name("UFC 300: Main Event") is False
        assert is_ppv_placeholder_name("UFC 300 - Jones vs Miocic") is False
        assert is_ppv_placeholder_name("WWE Wrestlemania 40") is False
        assert is_ppv_placeholder_name("BOXING: Fury vs Joshua") is False
        assert is_ppv_placeholder_name("Canelo vs Charlo Live") is False
        assert is_ppv_placeholder_name("AEW All In 2024") is False
        assert is_ppv_placeholder_name("Bellator 300") is False
        assert is_ppv_placeholder_name("DAZN: Anthony Joshua Fight Night") is False
        # Real examples from database with actual events
        assert is_ppv_placeholder_name("UK: DAZN PPV 3 - EAST CAROLINA @ NORTH CAROLINA | Tue 23 Dec 01:50") is False
        assert is_ppv_placeholder_name("LOI 1 | Shamrock Rovers v Cork City start:2025-11-09 14:45:00") is False
        assert is_ppv_placeholder_name("EPL 01: 20:00 Manchester United vs Newcastle United") is False


class TestGetPPVEventTitle:
    """Test extraction of event title from PPV channel"""

    def test_event_title_extraction(self, app):
        """Test that event title is extracted from active PPV channel"""
        with app.app_context():
            channel = Channel(
                account_id=1,
                stream_id="1001",
                name="UFC 300: Main Event",
                is_active=True,
            )
            title = get_ppv_event_title(channel)
            assert title == "UFC 300: Main Event"

    def test_placeholder_returns_none(self, app):
        """Test that placeholder name returns None"""
        with app.app_context():
            channel = Channel(
                account_id=1,
                stream_id="1001",
                name="PPV 1",
                is_active=True,
            )
            title = get_ppv_event_title(channel)
            assert title is None

    def test_empty_name_returns_none(self, app):
        """Test that empty name returns None"""
        with app.app_context():
            channel = Channel(
                account_id=1,
                stream_id="1001",
                name="",
                is_active=True,
            )
            title = get_ppv_event_title(channel)
            assert title is None


class TestPPVPlaceholderPatterns:
    """Test that PPV placeholder patterns are valid and working"""

    def test_patterns_are_valid_regex(self):
        """Test that all placeholder patterns are valid regex"""
        import re

        for pattern in PPV_PLACEHOLDER_PATTERNS:
            try:
                re.compile(pattern)
            except re.error as e:
                assert False, f"Invalid regex pattern '{pattern}': {e}"

    def test_patterns_match_expected_names(self):
        """Test various placeholder names against patterns

        These test cases are based on actual channel names from real IPTV providers.
        """
        test_cases = [
            # (name, expected_is_placeholder)
            # NO EVENT STREAMING markers (most common)
            ("NO EVENT STREAMING", True),
            ("UK: DAZN PPV 5 - NO EVENT STREAMING - | 8K EXCLUSIVE", True),
            # Empty slots
            ("UFC 09:", True),
            (":MAX NL  05", True),
            # TBA/Offline
            ("TBA", True),
            ("OFFLINE", True),
            # Event numbers only
            ("EVENT 14", True),
            # Actual events (should NOT be placeholders)
            ("UFC 300: Main Event", False),
            ("Canelo vs Crawford", False),
            ("WWE Raw Live", False),
            ("EPL 01: 20:00 Manchester United vs Newcastle United", False),
        ]

        for name, expected in test_cases:
            result = is_ppv_placeholder_name(name)
            assert result == expected, f"Expected is_ppv_placeholder_name('{name}') to be {expected}, got {result}"
