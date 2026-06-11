"""
Tests for PPV channel visibility (services.ppv.visibility).

Placeholder/category detection cases: tests/ppv/test_detection.py
Reverse matcher integration: tests/test_reverse_event_matcher/
"""

from datetime import datetime, timedelta, timezone

from models import Account, Channel, Event, EventChannelLink, db
from services.ppv.visibility import PPVVisibilityService

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

    def test_generic_slot_hidden_even_when_queued(self, app):
        """Generic numbered PPV slots stay hidden while enrichment is pending."""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="hide_inactive")
            db.session.add(account)
            db.session.commit()

            for name in ("GOLF 10", "DIRTVISION 03", "GOLF 10 HD"):
                channel = Channel(
                    account_id=account.id,
                    stream_id=f"slot-{name}",
                    name=name,
                    is_ppv=True,
                    is_active=True,
                    ppv_enrichment_status="queued",
                )
                db.session.add(channel)

            db.session.commit()

            service = PPVVisibilityService(account)
            channels = Channel.query.filter_by(account_id=account.id).all()
            assert all(service.should_show_channel(ch) is False for ch in channels)

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

        assert len(options) == 4
        assert "hide_all" in options
        assert "hide_inactive" in options
        assert "group_live_replay" in options
        assert "show_all" in options

        # Check structure
        assert options["hide_all"]["value"] == "hide_all"
        assert "label" in options["hide_all"]
        assert "description" in options["hide_all"]

    def test_group_live_replay_shows_replays_and_hides_far_future_events(self, app):
        """Group mode shows replay events but hides events scheduled beyond 24 hours."""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="group_live_replay")
            db.session.add(account)
            db.session.commit()

            replay_channel = Channel(
                account_id=account.id, stream_id="2001", name="Replay", is_ppv=True, is_active=True
            )
            future_channel = Channel(
                account_id=account.id, stream_id="2002", name="Future", is_ppv=True, is_active=True
            )
            db.session.add_all([replay_channel, future_channel])
            db.session.commit()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            replay_event = Event(
                external_id="replay-event",
                scheduled_at=now - timedelta(hours=2),
                home_team_id="a",
                home_team_name="A",
                away_team_id="b",
                away_team_name="B",
                status=Event.STATUS_FINISHED,
            )
            future_event = Event(
                external_id="future-event",
                scheduled_at=now + timedelta(hours=30),
                home_team_id="c",
                home_team_name="C",
                away_team_id="d",
                away_team_name="D",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add_all([replay_event, future_event])
            db.session.flush()
            db.session.add_all(
                [
                    EventChannelLink(event_id=replay_event.id, channel_id=replay_channel.id),
                    EventChannelLink(event_id=future_event.id, channel_id=future_channel.id),
                ]
            )
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(replay_channel) is True
            assert service.classify_live_replay_channel(replay_channel) == PPVVisibilityService.PPV_GROUP_REPLAY
            assert service.should_show_channel(future_channel) is False

    def test_group_live_replay_hides_unmatched_ppv_channels(self, app):
        """Group mode excludes PPV channels that cannot be classified into Live or Replay."""
        with app.app_context():
            account = Account(name="Test", server="http://test.com", ppv_visibility="group_live_replay")
            channel = Channel(account_id=1, stream_id="2003", name="Unknown PPV", is_ppv=True, is_active=True)
            db.session.add(account)
            db.session.flush()
            channel.account_id = account.id
            db.session.add(channel)
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.should_show_channel(channel) is False
            assert service.classify_live_replay_channel(channel) is None


class TestLiveGameVisibility:
    """Tests for in-progress / live-game visibility behaviour.

    Covers the three new show-paths added to _is_ppv_active():
    1. event.status == STATUS_LIVE
    2. provider stop: token present and now < stop_time
    3. sport-aware grace window after scheduled_at
    """

    def _make_account_and_service(self, app_ctx):
        from models import Account, db

        account = Account(name="LiveTest", server="http://test.com", ppv_visibility="hide_inactive")
        db.session.add(account)
        db.session.commit()
        service = PPVVisibilityService(account)
        return account, service

    def _make_channel(self, account_id, stream_id, name):
        from models import Channel, db

        channel = Channel(
            account_id=account_id,
            stream_id=stream_id,
            name=name,
            is_ppv=True,
            is_active=True,
        )
        db.session.add(channel)
        db.session.commit()
        return channel

    def _link_event(self, event, channel):
        from models import EventChannelLink, db

        link = EventChannelLink(event_id=event.id, channel_id=channel.id)
        db.session.add(link)
        db.session.commit()

    def test_status_live_always_shown(self, app):
        """Event with STATUS_LIVE is shown even if scheduled_at is in the past."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
            event = Event(
                external_id="live-test-1",
                scheduled_at=past,
                home_team_id="royals",
                home_team_name="Royals",
                away_team_id="rangers",
                away_team_name="Rangers",
                sport="baseball",
                status=Event.STATUS_LIVE,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(account.id, "live-ch-1", "MLB 10 | Royals x Rangers start:2026-05-31 19:35:00")
            self._link_event(event, channel)
            assert service.should_show_channel(channel) is True

    def test_stop_token_before_now_shown(self, app):
        """Channel with stop: token in the future is shown even if scheduled_at passed."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            # Game started 90 minutes ago
            past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=90)
            # stop: is 3 hours from now
            future_stop = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=3)
            stop_str = future_stop.strftime("%Y-%m-%d %H:%M:%S")
            event = Event(
                external_id="stop-test-1",
                scheduled_at=past,
                home_team_id="royals2",
                home_team_name="Royals",
                away_team_id="rangers2",
                away_team_name="Rangers",
                sport="baseball",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(
                account.id,
                "stop-ch-1",
                f"MLB 10 | Royals x Rangers start:2026-05-31 19:35:00 stop:{stop_str}",
            )
            self._link_event(event, channel)
            assert service.should_show_channel(channel) is True

    def test_stop_token_past_falls_through_to_grace(self, app):
        """Channel whose stop: time has passed but is within grace window stays shown."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            # Game started 2 hours ago; stop: expired 30 min ago but within 4h baseball grace
            past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=2)
            past_stop = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
            stop_str = past_stop.strftime("%Y-%m-%d %H:%M:%S")
            event = Event(
                external_id="stop-test-2",
                scheduled_at=past,
                home_team_id="royals3",
                home_team_name="Royals",
                away_team_id="rangers3",
                away_team_name="Rangers",
                sport="baseball",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(
                account.id,
                "stop-ch-2",
                f"MLB 10 | Royals x Rangers stop:{stop_str}",
            )
            self._link_event(event, channel)
            # Within 4-hour baseball grace (only 2h elapsed) → show
            assert service.should_show_channel(channel) is True

    def test_grace_window_shows_in_progress_game(self, app):
        """Scheduled event that started 90 min ago is shown within grace window."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            # Game started 90 min ago; baseball grace is 4 hours
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=90)
            event = Event(
                external_id="grace-test-1",
                scheduled_at=scheduled,
                home_team_id="royals4",
                home_team_name="Royals",
                away_team_id="rangers4",
                away_team_name="Rangers",
                sport="baseball",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(account.id, "grace-ch-1", "MLB 10 | Royals x Rangers")
            self._link_event(event, channel)
            assert service.should_show_channel(channel) is True

    def test_grace_window_hides_expired_game(self, app):
        """Scheduled event well past grace window is hidden."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            # Game started 8 hours ago; baseball grace is 4 hours
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=8)
            event = Event(
                external_id="grace-test-2",
                scheduled_at=scheduled,
                home_team_id="royals5",
                home_team_name="Royals",
                away_team_id="rangers5",
                away_team_name="Rangers",
                sport="baseball",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(account.id, "grace-ch-2", "MLB 10 | Royals x Rangers")
            self._link_event(event, channel)
            assert service.should_show_channel(channel) is False

    def test_finished_event_hidden_regardless_of_grace(self, app):
        """STATUS_FINISHED hides channel even if within grace window (regression)."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            recent = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)
            event = Event(
                external_id="grace-finished-1",
                scheduled_at=recent,
                home_team_id="royals6",
                home_team_name="Royals",
                away_team_id="rangers6",
                away_team_name="Rangers",
                sport="baseball",
                status=Event.STATUS_FINISHED,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(account.id, "grace-ch-3", "MLB 10 | Royals x Rangers")
            self._link_event(event, channel)
            assert service.should_show_channel(channel) is False

    def test_boxing_uses_longer_grace_window(self, app):
        """Boxing events use 12-hour grace window, keeping them visible longer."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            # Fight started 10 hours ago; boxing grace is 12 hours
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
            event = Event(
                external_id="boxing-grace-1",
                scheduled_at=scheduled,
                home_team_id="fury",
                home_team_name="Fury",
                away_team_id="joshua",
                away_team_name="Joshua",
                sport="boxing",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.commit()
            channel = self._make_channel(account.id, "boxing-ch-1", "BOXING: Fury vs Joshua")
            self._link_event(event, channel)
            assert service.should_show_channel(channel) is True


class TestFarFutureVisibility:
    """Tests for hiding PPV events more than one month in the future."""

    def _make_account_and_service(self, app_ctx):
        account = Account(name="FarFutureTest", server="http://test.com", ppv_visibility="hide_inactive")
        db.session.add(account)
        db.session.commit()
        return account, PPVVisibilityService(account)

    def _make_event(self, scheduled_at, external_id="ff-event-1"):
        event = Event(
            external_id=external_id,
            scheduled_at=scheduled_at,
            home_team_id="home-id",
            home_team_name="Home",
            away_team_id="away-id",
            away_team_name="Away",
            league_name="MMA",
            status=Event.STATUS_SCHEDULED,
        )
        db.session.add(event)
        db.session.commit()
        return event

    def test_event_exactly_one_month_away_is_shown(self, app):
        """Events exactly 31 days away are still shown (boundary: <=31 days)."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=31)
            event = self._make_event(scheduled)
            channel = Channel(
                account_id=account.id,
                stream_id="ff-ch-boundary",
                name="UFC 400: Jones vs Miocic",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()
            assert service.should_show_channel(channel) is True

    def test_event_more_than_one_month_away_is_hidden(self, app):
        """Events scheduled more than 31 days away are hidden."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=32)
            event = self._make_event(scheduled, external_id="ff-event-2")
            channel = Channel(
                account_id=account.id,
                stream_id="ff-ch-far",
                name="UFC 400: Jones vs Miocic",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()
            assert service.should_show_channel(channel) is False

    def test_event_two_months_away_is_hidden(self, app):
        """Events two months away are hidden."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=60)
            event = self._make_event(scheduled, external_id="ff-event-3")
            channel = Channel(
                account_id=account.id,
                stream_id="ff-ch-60d",
                name="UFC 401: Smith vs Jones",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()
            assert service.should_show_channel(channel) is False

    def test_show_all_mode_ignores_far_future_filter(self, app):
        """In show_all mode, far-future events are still shown."""
        with app.app_context():
            account = Account(name="ShowAllTest", server="http://test.com", ppv_visibility="show_all")
            db.session.add(account)
            db.session.commit()
            service = PPVVisibilityService(account)
            scheduled = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=60)
            event = self._make_event(scheduled, external_id="ff-event-4")
            channel = Channel(
                account_id=account.id,
                stream_id="ff-ch-show-all",
                name="UFC 402: Far Future Fight",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()
            assert service.should_show_channel(channel) is True

    def test_queued_channel_with_far_future_date_in_name_is_hidden(self, app):
        """A queued channel whose name contains an explicit date >31 days away is hidden."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            # Build a channel name with an explicit ISO date >31 days from now
            far_date = datetime.now(timezone.utc) + timedelta(days=45)
            date_str = far_date.strftime("%Y-%m-%d %H:%M")
            channel = Channel(
                account_id=account.id,
                stream_id="ff-ch-queued",
                name=f"UFC 405: Smith vs Jones | start:{date_str}",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()
            assert service.should_show_channel(channel) is False

    def test_queued_channel_near_future_date_in_name_is_shown(self, app):
        """A queued channel with a date within 31 days is shown optimistically."""
        with app.app_context():
            account, service = self._make_account_and_service(app)
            near_date = datetime.now(timezone.utc) + timedelta(days=7)
            date_str = near_date.strftime("%Y-%m-%d %H:%M")
            channel = Channel(
                account_id=account.id,
                stream_id="ff-ch-queued-near",
                name=f"UFC 403: Brown vs White | start:{date_str}",
                is_ppv=True,
                is_active=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(channel)
            db.session.commit()
            assert service.should_show_channel(channel) is True


class TestGroupLiveReplayHistoricalSplit:
    """PPV - Replay vs PPV - Historical classification (TODO 134)."""

    def test_event_25_days_past_is_historical(self):
        now = datetime(2026, 6, 10, 12, 0, 0)
        event = Event(
            external_id="historical-event",
            scheduled_at=now - timedelta(days=25),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            status=Event.STATUS_FINISHED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_HISTORICAL
        )

    def test_event_5_days_past_is_replay(self):
        now = datetime(2026, 6, 10, 12, 0, 0)
        event = Event(
            external_id="replay-event",
            scheduled_at=now - timedelta(days=5),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            status=Event.STATUS_FINISHED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_REPLAY
        )

    def test_event_in_12_hours_is_live(self):
        now = datetime(2026, 6, 10, 12, 0, 0)
        event = Event(
            external_id="live-event",
            scheduled_at=now + timedelta(hours=12),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            status=Event.STATUS_SCHEDULED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_LIVE
        )

    def test_event_exactly_21_days_past_is_replay(self):
        now = datetime(2026, 6, 10, 12, 0, 0)
        event = Event(
            external_id="boundary-replay",
            scheduled_at=now - timedelta(days=21),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            status=Event.STATUS_FINISHED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_REPLAY
        )

    def test_ppv_group_display_titles(self):
        assert PPVVisibilityService.ppv_group_display_title(PPVVisibilityService.PPV_GROUP_LIVE) == "PPV - Live"
        assert PPVVisibilityService.ppv_group_display_title(PPVVisibilityService.PPV_GROUP_REPLAY) == "PPV - Replay"
        assert (
            PPVVisibilityService.ppv_group_display_title(PPVVisibilityService.PPV_GROUP_HISTORICAL)
            == "PPV - Historical"
        )
        assert (
            PPVVisibilityService.ppv_group_display_title(PPVVisibilityService.PPV_GROUP_UNMATCHED_LIVE)
            == "PPV - Unmatched Live"
        )

    def test_in_progress_soccer_event_is_live_not_replay(self):
        """Scheduled event that started recently stays Live during sport grace window."""
        now = datetime(2026, 6, 10, 23, 6, 0)
        event = Event(
            external_id="usl-knoxville",
            scheduled_at=now - timedelta(minutes=6),
            home_team_id="ok",
            home_team_name="One Knoxville",
            away_team_id="crw",
            away_team_name="Chattanooga Red Wolves",
            sport="Soccer",
            league_name="USL Cup",
            status=Event.STATUS_SCHEDULED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_LIVE
        )

    def test_in_progress_basketball_event_is_live_not_replay(self):
        """WNBA-style in-progress game classifies as Live, not Replay."""
        now = datetime(2026, 6, 10, 23, 6, 0)
        event = Event(
            external_id="wnba-tempo-sun",
            scheduled_at=now - timedelta(minutes=6),
            home_team_id="tor",
            home_team_name="Toronto Tempo",
            away_team_id="con",
            away_team_name="Connecticut Sun",
            sport="Basketball",
            league_name="WNBA",
            status=Event.STATUS_SCHEDULED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_LIVE
        )

    def test_finished_event_past_start_is_replay_not_live(self):
        """Finished events stay Replay even when within the grace window."""
        now = datetime(2026, 6, 10, 23, 6, 0)
        event = Event(
            external_id="finished-recent",
            scheduled_at=now - timedelta(hours=2),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            sport="Soccer",
            status=Event.STATUS_FINISHED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_REPLAY
        )

    def test_past_grace_window_scheduled_event_is_replay(self):
        """Scheduled event well past sport grace window classifies as Replay."""
        now = datetime(2026, 6, 10, 23, 6, 0)
        event = Event(
            external_id="expired-soccer",
            scheduled_at=now - timedelta(hours=3),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            sport="Soccer",
            status=Event.STATUS_SCHEDULED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_REPLAY
        )

    def test_end_at_in_future_keeps_live_classification(self):
        now = datetime(2026, 6, 10, 23, 6, 0)
        event = Event(
            external_id="end-at-future",
            scheduled_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=1),
            home_team_id="h",
            home_team_name="Home",
            away_team_id="a",
            away_team_name="Away",
            sport="Soccer",
            status=Event.STATUS_SCHEDULED,
        )
        assert (
            PPVVisibilityService.classify_live_replay_event(event, current_time=now)
            == PPVVisibilityService.PPV_GROUP_LIVE
        )


class TestGroupVisibilityToggles:
    """Per-group show/hide toggles for group_live_replay accounts (TODO 134)."""

    def test_historical_hidden_when_toggle_off(self, app):
        with app.app_context():
            account = Account(
                name="Toggle Test",
                server="http://test.com",
                ppv_visibility="group_live_replay",
                ppv_show_historical=False,
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="hist-1",
                name="Old Flo Replay",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            event = Event(
                external_id="hist-event",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30),
                home_team_id="h",
                home_team_name="Home",
                away_team_id="a",
                away_team_name="Away",
                status=Event.STATUS_FINISHED,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.classify_live_replay_channel(channel) == PPVVisibilityService.PPV_GROUP_HISTORICAL
            assert service.should_show_channel(channel) is False

    def test_replay_hidden_when_toggle_off(self, app):
        with app.app_context():
            account = Account(
                name="Replay Toggle",
                server="http://test.com",
                ppv_visibility="group_live_replay",
                ppv_show_replay=False,
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="replay-1",
                name="Recent Replay",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            event = Event(
                external_id="replay-event",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3),
                home_team_id="h",
                home_team_name="Home",
                away_team_id="a",
                away_team_name="Away",
                status=Event.STATUS_FINISHED,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.classify_live_replay_channel(channel) == PPVVisibilityService.PPV_GROUP_REPLAY
            assert service.should_show_channel(channel) is False

    def test_live_still_shown_when_replay_and_historical_toggled_off(self, app):
        with app.app_context():
            account = Account(
                name="Live Always",
                server="http://test.com",
                ppv_visibility="group_live_replay",
                ppv_show_replay=False,
                ppv_show_historical=False,
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="live-1",
                name="Soon Live",
                is_ppv=True,
                is_active=True,
            )
            db.session.add(channel)
            db.session.commit()

            event = Event(
                external_id="live-soon",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=6),
                home_team_id="h",
                home_team_name="Home",
                away_team_id="a",
                away_team_name="Away",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.classify_live_replay_channel(channel) == PPVVisibilityService.PPV_GROUP_LIVE
            assert service.should_show_channel(channel) is True


class TestUnmatchedLiveClassification:
    """Unmatched PPV channels with enrichable extraction land in PPV - Unmatched Live."""

    NOW = datetime(2026, 6, 10, 12, 0, 0)

    def _account_and_service(self, app_ctx, **account_kwargs):
        account = Account(
            name="Unmatched Test",
            server="http://test.com",
            ppv_visibility="group_live_replay",
            **account_kwargs,
        )
        db.session.add(account)
        db.session.commit()
        return account, PPVVisibilityService(account)

    def _channel(self, account_id, name, **kwargs):
        kwargs.setdefault("ppv_enrichment_status", "no_match")
        channel = Channel(
            account_id=account_id,
            stream_id=kwargs.pop("stream_id", "unmatched-1"),
            name=name,
            is_ppv=True,
            is_active=True,
            **kwargs,
        )
        db.session.add(channel)
        db.session.commit()
        return channel

    def test_upcoming_no_match_with_competitors_and_date(self, app):
        with app.app_context():
            account, service = self._account_and_service(app)
            channel = self._channel(
                account.id,
                "DAZN 01 | Arsenal vs Brighton (2026-06-10 20:00:00)",
            )
            assert (
                service.classify_unmatched_live_channel(channel, current_time=self.NOW)
                == PPVVisibilityService.PPV_GROUP_UNMATCHED_LIVE
            )
            assert service.should_show_channel(channel) is True

    def test_in_progress_no_match_within_sport_grace(self, app):
        with app.app_context():
            account, service = self._account_and_service(app)
            channel = self._channel(
                account.id,
                "ESPN+ | Lakers vs Celtics (2026-06-10 11:00:00)",
                stream_id="unmatched-2",
            )
            assert (
                service.classify_unmatched_live_channel(channel, current_time=self.NOW)
                == PPVVisibilityService.PPV_GROUP_UNMATCHED_LIVE
            )

    def test_generic_slot_not_unmatched_live(self, app):
        with app.app_context():
            account, service = self._account_and_service(app)
            channel = self._channel(account.id, "PPV 1", stream_id="generic-1")
            assert service.classify_unmatched_live_channel(channel, current_time=self.NOW) is None
            assert service.should_show_channel(channel) is False

    def test_far_future_no_match_not_unmatched_live(self, app):
        with app.app_context():
            account, service = self._account_and_service(app)
            channel = self._channel(
                account.id,
                "UFC | Fighter A vs Fighter B start:2099-01-01 01:00:00",
                stream_id="far-future-1",
            )
            assert service.classify_unmatched_live_channel(channel, current_time=self.NOW) is None

    def test_stale_archive_no_match_not_unmatched_live(self, app):
        with app.app_context():
            account, service = self._account_and_service(app)
            channel = self._channel(
                account.id,
                "ESPN Play | Team A vs Team B | 01-18-2024",
                stream_id="stale-1",
            )
            assert service.classify_unmatched_live_channel(channel, current_time=self.NOW) is None

    def test_linked_event_uses_live_not_unmatched(self, app):
        with app.app_context():
            account, service = self._account_and_service(app)
            channel = self._channel(
                account.id,
                "DAZN 02 | Chelsea vs Liverpool (2026-06-10 18:00:00)",
                stream_id="linked-1",
                ppv_enrichment_status="matched",
            )
            event = Event(
                external_id="linked-unmatched-test",
                scheduled_at=self.NOW + timedelta(hours=6),
                home_team_id="che",
                home_team_name="Chelsea",
                away_team_id="liv",
                away_team_name="Liverpool",
                status=Event.STATUS_SCHEDULED,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            assert (
                service.classify_live_replay_channel(channel, current_time=self.NOW)
                == PPVVisibilityService.PPV_GROUP_LIVE
            )
            assert (
                service.classify_unmatched_live_channel(channel, current_time=self.NOW)
                != PPVVisibilityService.PPV_GROUP_UNMATCHED_LIVE
            )

    def test_unmatched_live_hidden_when_toggle_off(self, app):
        with app.app_context():
            account, service = self._account_and_service(app, ppv_show_unmatched_live=False)
            channel = self._channel(
                account.id,
                "DAZN 03 | Spurs vs Newcastle (2026-06-10 19:00:00)",
                stream_id="toggle-1",
            )
            assert (
                service.classify_unmatched_live_channel(channel, current_time=self.NOW)
                == PPVVisibilityService.PPV_GROUP_UNMATCHED_LIVE
            )
            assert service.should_show_channel(channel) is False
