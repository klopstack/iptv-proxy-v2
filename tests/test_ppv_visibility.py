"""
Tests for PPV channel visibility

Covers placeholder name detection (services.epg.ppv) and event-based visibility
filtering (services.ppv.visibility).
"""

from datetime import datetime, timedelta, timezone

from models import Account, Channel, ChannelTag, Event, EventChannelLink, Tag, db
from services.epg.constants import PPV_PLACEHOLDER_PATTERNS
from services.epg.ppv import get_ppv_event_title, is_ppv_placeholder_name
from services.ppv.visibility import PPVVisibilityService


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


# Event-based visibility (PPVVisibilityService)


class TestPPVVisibilityService:
    """Test PPV visibility logic based on Event records"""

    def test_init_with_account(self, app):
        """Test service initialization with account"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            service = PPVVisibilityService(account)

            assert service.account == account
            assert service.ppv_visibility == "hide_inactive"

    def test_init_default_visibility(self, app):
        """Test service initialization with default visibility"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com")
            service = PPVVisibilityService(account)

            # Default is HIDE_INACTIVE, but getattr returns None if not set
            assert service.ppv_visibility in [None, "hide_inactive"]

    def test_non_ppv_channel_always_shown(self, app):
        """Test that non-PPV channels are always shown regardless of settings"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_all")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="Regular Channel",
                is_ppv=False,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is True

    def test_hide_all_hides_ppv_channels(self, app):
        """Test that hide_all setting hides all PPV channels"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_all")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_show_all_shows_ppv_channels(self, app):
        """Test that show_all setting shows all PPV channels"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="show_all")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is True

    def test_hide_inactive_shows_future_event(self, app):
        """Test that future events are shown with hide_inactive"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            # Create event in the future
            future_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
            event = Event(
                external_id="test-event-1",
                scheduled_at=future_date,
                home_team_id="ufc-id",
                home_team_name="UFC",
                away_team_id="300-id",
                away_team_name="300",
                league_name="MMA",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()

            # Create channel
            channel = Channel(
                account_id=account.id,
                stream_id="1001",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Link event to channel
            link = EventChannelLink(event_id=event.id, channel_id=channel.id)
            db.session.add(link)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is True

    def test_hide_inactive_hides_past_event(self, app):
        """Test that past events are hidden with hide_inactive"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            # Create event in the past
            past_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
            event = Event(
                external_id="test-event-2",
                scheduled_at=past_date,
                home_team_id="ufc-id",
                home_team_name="UFC",
                away_team_id="299-id",
                away_team_name="299",
                league_name="MMA",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()

            # Create channel
            channel = Channel(
                account_id=account.id,
                stream_id="1002",
                name="UFC 299: Past Event",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Link event to channel
            link = EventChannelLink(event_id=event.id, channel_id=channel.id)
            db.session.add(link)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_cancelled_event_hidden(self, app):
        """Test that cancelled events are hidden"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            # Create future event that is cancelled
            future_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
            event = Event(
                external_id="test-event-3",
                scheduled_at=future_date,
                home_team_id="ufc-id",
                home_team_name="UFC",
                away_team_id="301-id",
                away_team_name="301",
                league_name="MMA",
                status=Event.STATUS_CANCELLED,
            )
            db.session.add(event)
            db.session.commit()

            # Create channel
            channel = Channel(
                account_id=account.id,
                stream_id="1003",
                name="UFC 301: Cancelled",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Link event to channel
            link = EventChannelLink(event_id=event.id, channel_id=channel.id)
            db.session.add(link)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_finished_event_hidden(self, app):
        """Test that finished events are hidden"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            # Create past event that is finished
            past_date = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=3)
            event = Event(
                external_id="test-event-4",
                scheduled_at=past_date,
                home_team_id="ufc-id",
                home_team_name="UFC",
                away_team_id="298-id",
                away_team_name="298",
                league_name="MMA",
                status=Event.STATUS_FINISHED,
            )
            db.session.add(event)
            db.session.commit()

            # Create channel
            channel = Channel(
                account_id=account.id,
                stream_id="1004",
                name="UFC 298: Finished",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            # Link event to channel
            link = EventChannelLink(event_id=event.id, channel_id=channel.id)
            db.session.add(link)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_no_event_with_no_match_status_hidden(self, app):
        """Test that channels with no_match enrichment status are hidden"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1005",
                name="PPV 1",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="no_match",
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_no_event_with_queued_status_shown(self, app):
        """Test that channels being enriched are shown (optimistic)"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1006",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is True

    def test_no_event_with_processing_status_shown(self, app):
        """Test that channels being processed are shown (optimistic)"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1007",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="processing",
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is True

    def test_no_event_with_error_status_shown(self, app):
        """Test that channels with enrichment errors are shown (avoid hiding valid channels)"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1008",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="error",
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is True

    def test_no_event_no_status_hidden(self, app):
        """Test that channels with no event and no enrichment status are hidden (conservative)"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1009",
                name="PPV 1",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_exception_handling_shows_channel(self, app):
        """Test that exceptions default to showing channel (avoid hiding valid content)"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            # Create channel without committing (simulate DB error)
            channel = Channel(
                account_id=account.id,
                stream_id="1010",
                name="UFC 300: Main Event",
                is_ppv=True,
                is_active=True,
            )
            # Don't add to session or commit

            service = PPVVisibilityService(account)
            # Should not crash, should default to hiding (no event, no status)
            result = service.should_show_channel(channel)
            assert result is False

    def test_event_cache_used(self, app):
        """Test that event cache is used for repeated lookups"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            future_date = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7)
            event = Event(
                external_id="test-event-cache",
                scheduled_at=future_date,
                home_team_id="ufc-id",
                home_team_name="UFC",
                away_team_id="302-id",
                away_team_name="302",
                league_name="MMA",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="1011",
                name="UFC 302: Cache Test",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            link = EventChannelLink(event_id=event.id, channel_id=channel.id)
            db.session.add(link)
            db.session.commit()

            service = PPVVisibilityService(account)

            # First call - should query DB and cache
            result1 = service.should_show_channel(channel)
            assert result1 is True

            # Second call - should use cache
            result2 = service.should_show_channel(channel)
            assert result2 is True

            # Cache should have entry
            assert channel.id in service._event_cache

    def test_unknown_visibility_mode_defaults_to_hide_inactive(self, app):
        """Test that unknown visibility modes default to hide_inactive behavior"""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="invalid_mode")
            db.session.add(account)
            db.session.commit()

            # Create channel with no event (should be hidden in hide_inactive mode)
            channel = Channel(
                account_id=account.id,
                stream_id="1012",
                name="PPV 1",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False

    def test_get_visibility_options(self):
        """Test that visibility options are returned correctly"""
        options = PPVVisibilityService.get_visibility_options()

        assert len(options) == 3
        assert "hide_all" in options
        assert "hide_inactive" in options
        assert "show_all" in options

        # Check structure
        assert options["hide_all"]["value"] == "hide_all"
        assert "label" in options["hide_all"]
        assert "description" in options["hide_all"]
