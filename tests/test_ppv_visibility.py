"""
Tests for PPV channel visibility based on channel name detection

PPV channels from IPTV providers have placeholder names like "PPV 1" when no
event is scheduled. When an event IS scheduled, the provider changes the
channel name to the event title (e.g., "UFC 300: Main Event").

These tests verify the name-based detection logic.
"""

from models import Account, Channel, ChannelTag, Tag, db
from services.epg_service import (
    PPV_PLACEHOLDER_PATTERNS,
    generate_ppv_epg_entries,
    get_ppv_epg_xmltv,
    get_ppv_event_title,
    is_ppv_placeholder_name,
    update_ppv_channel_visibility,
)


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


class TestPPVVisibilityUpdate:
    """Test PPV channel visibility updates based on channel names"""

    def test_ppv_channel_shown_with_event_name(self, app):
        """Test that PPV channel is shown when it has an event name"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create PPV channel with event name (initially hidden)
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",  # Actual event title
                is_active=True,
                is_visible=False,
            )
            db.session.add(channel)
            db.session.commit()

            # Tag channel as PPV
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=channel.stream_id,
                tag_id=ppv_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Update visibility
            stats = update_ppv_channel_visibility(account.id)

            # Channel should be visible now
            db.session.refresh(channel)
            assert channel.is_visible is True, "PPV channel should be visible with event name"
            assert stats["channels_shown"] == 1
            assert stats["events_detected"] == 1
            assert stats["channels_hidden"] == 0

    def test_ppv_channel_hidden_with_placeholder_name(self, app):
        """Test that PPV channel is hidden when it has a placeholder name"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create PPV channel with placeholder name (initially visible)
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="PPV 1",  # Placeholder
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Tag channel as PPV
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=channel.stream_id,
                tag_id=ppv_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Update visibility
            stats = update_ppv_channel_visibility(account.id)

            # Channel should be hidden now
            db.session.refresh(channel)
            assert channel.is_visible is False, "PPV channel should be hidden with placeholder name"
            assert stats["channels_hidden"] == 1
            assert stats["events_detected"] == 0
            assert stats["channels_shown"] == 0

    def test_multiple_ppv_channels_mixed_visibility(self, app):
        """Test updating multiple PPV channels with mixed name states"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create PPV channels with different names
            channel1 = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",  # Active event
                is_active=True,
                is_visible=False,
            )
            channel2 = Channel(
                account_id=account.id,
                stream_id="1002",
                name="PPV 2",  # Placeholder
                is_active=True,
                is_visible=True,
            )
            channel3 = Channel(
                account_id=account.id,
                stream_id="1003",
                name="WWE Wrestlemania 40",  # Active event
                is_active=True,
                is_visible=False,
            )
            channel4 = Channel(
                account_id=account.id,
                stream_id="1004",
                name="COMING SOON",  # Placeholder
                is_active=True,
                is_visible=True,
            )
            db.session.add_all([channel1, channel2, channel3, channel4])
            db.session.commit()

            # Tag all as PPV
            for channel in [channel1, channel2, channel3, channel4]:
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=channel.stream_id,
                    tag_id=ppv_tag.id,
                )
                db.session.add(channel_tag)
            db.session.commit()

            # Update visibility
            stats = update_ppv_channel_visibility(account.id)

            # Refresh channels
            db.session.refresh(channel1)
            db.session.refresh(channel2)
            db.session.refresh(channel3)
            db.session.refresh(channel4)

            # Check visibility
            assert channel1.is_visible is True, "Channel with event name should be visible"
            assert channel2.is_visible is False, "Channel with placeholder should be hidden"
            assert channel3.is_visible is True, "Channel with event name should be visible"
            assert channel4.is_visible is False, "Channel with placeholder should be hidden"

            # Check stats
            assert stats["total_ppv_channels"] == 4
            assert stats["events_detected"] == 2
            assert stats["channels_shown"] == 2
            assert stats["channels_hidden"] == 2

    def test_no_ppv_tag_returns_empty_stats(self, app):
        """Test that function handles missing PPV tag gracefully"""
        with app.app_context():
            # Don't create PPV tag
            stats = update_ppv_channel_visibility()

            assert stats["total_ppv_channels"] == 0
            assert stats["channels_shown"] == 0
            assert stats["channels_hidden"] == 0
            assert stats["events_detected"] == 0

    def test_no_changes_if_already_correct(self, app):
        """Test that no changes are made if visibility is already correct"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create channels with correct visibility
            channel1 = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",  # Active - already visible
                is_active=True,
                is_visible=True,
            )
            channel2 = Channel(
                account_id=account.id,
                stream_id="1002",
                name="PPV 2",  # Placeholder - already hidden
                is_active=True,
                is_visible=False,
            )
            db.session.add_all([channel1, channel2])
            db.session.commit()

            # Tag all as PPV
            for channel in [channel1, channel2]:
                channel_tag = ChannelTag(
                    account_id=account.id,
                    stream_id=channel.stream_id,
                    tag_id=ppv_tag.id,
                )
                db.session.add(channel_tag)
            db.session.commit()

            # Update visibility
            stats = update_ppv_channel_visibility(account.id)

            # No changes should be made
            assert stats["channels_shown"] == 0, "No channels should be newly shown"
            assert stats["channels_hidden"] == 0, "No channels should be newly hidden"
            assert stats["events_detected"] == 1, "One event should be detected"
            assert stats["total_ppv_channels"] == 2


class TestPPVEpgGeneration:
    """Test PPV EPG generation for active events"""

    def test_generate_ppv_epg_entries(self, app):
        """Test that EPG entries are generated for active PPV channels"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create visible PPV channel with event name
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",
                is_active=True,
                is_visible=True,  # Already visible (active event)
            )
            db.session.add(channel)
            db.session.commit()

            # Tag as PPV
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=channel.stream_id,
                tag_id=ppv_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Generate EPG entries
            entries = generate_ppv_epg_entries(account.id)

            assert len(entries) == 1
            assert entries[0]["title"] == "UFC 300: Main Event"
            assert entries[0]["channel_id"] == f"ppv-{channel.stream_id}-{account.id}"
            assert entries[0]["category"] == "Sports"
            assert "start" in entries[0]
            assert "stop" in entries[0]

    def test_no_epg_for_placeholder_channels(self, app):
        """Test that no EPG is generated for placeholder (hidden) channels"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create hidden PPV channel with placeholder name
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="PPV 1",
                is_active=True,
                is_visible=False,  # Hidden (placeholder)
            )
            db.session.add(channel)
            db.session.commit()

            # Tag as PPV
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=channel.stream_id,
                tag_id=ppv_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Generate EPG entries
            entries = generate_ppv_epg_entries(account.id)

            assert len(entries) == 0, "No EPG should be generated for placeholder channels"

    def test_get_ppv_epg_xmltv(self, app):
        """Test XMLTV generation for PPV channels"""
        with app.app_context():
            # Create account
            account = Account(
                name="Test Account",
                server="http://test.com",
                username="user",
                password="pass",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            # Create PPV tag
            ppv_tag = Tag(name="PPV")
            db.session.add(ppv_tag)
            db.session.commit()

            # Create visible PPV channel
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Tag as PPV
            channel_tag = ChannelTag(
                account_id=account.id,
                stream_id=channel.stream_id,
                tag_id=ppv_tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

            # Generate XMLTV
            xml_data = get_ppv_epg_xmltv(account.id)

            assert xml_data is not None
            assert b"<tv" in xml_data
            assert b"UFC 300: Main Event" in xml_data
            assert b"<programme" in xml_data
            assert b"<channel" in xml_data


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
