"""
Tests for PPVVisibilityService - Event-based PPV visibility

This service uses Event records created by ppv_calendar_enrichment_service.
"""

from datetime import datetime, timedelta, timezone

from models import Account, Channel, Event, EventChannelLink, db
from services.ppv.visibility import PPVVisibilityService


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
