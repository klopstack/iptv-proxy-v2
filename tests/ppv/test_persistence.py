"""Unit tests for services.ppv.persistence — no enrichment or reverse matcher mocks."""

from datetime import datetime, timedelta, timezone

import pytest

from models import Account, Category, Channel, Event, EventChannelLink, db
from services.ppv.constants import MAX_EVENT_AGE_DAYS, MAX_EVENT_FUTURE_DAYS
from services.ppv.matching.enhanced import EnhancedMatchResult
from services.ppv.persistence import (
    clear_event_links_for_channels,
    create_or_update_event,
    link_channel_to_event,
    persist_enhanced_match,
    persist_match,
    sync_enrichment_status_from_links,
)
from services.thesportsdb_calendar_scraper import CalendarEvent


@pytest.fixture
def fixed_now(monkeypatch):
    """Pin persistence age checks to a stable UTC instant."""
    now = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
    import services.ppv.persistence as persistence_mod

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is not None:
                return now
            return now.replace(tzinfo=None)

    monkeypatch.setattr(persistence_mod, "datetime", FixedDateTime)
    return now


def _calendar_event(
    *,
    event_id: str = "evt-1",
    days_from_now: int = 0,
    source: str = "thesportsdb",
    scheduled_at: datetime | None = None,
    **kwargs,
) -> CalendarEvent:
    if scheduled_at is None:
        base = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)
        scheduled_at = base + timedelta(days=days_from_now)
    cal = CalendarEvent(
        event_id=event_id,
        event_name=kwargs.get("event_name", "Team A vs Team B"),
        league_name=kwargs.get("league_name", "Test League"),
        time_utc=scheduled_at.strftime("%H:%M:%S"),
        date=scheduled_at.strftime("%Y-%m-%d"),
        home_team=kwargs.get("home_team", "Team A"),
        away_team=kwargs.get("away_team", "Team B"),
        source=source,
        sport=kwargs.get("sport"),
    )
    cal._scheduled_at_cached = scheduled_at.replace(tzinfo=None) if scheduled_at.tzinfo else scheduled_at
    cal._scheduled_at_computed = True
    return cal


def _ppv_channel(app, *, status: str = "pending", is_ppv: bool = True) -> Channel:
    with app.app_context():
        account = Account(name="Persist Test", server="test.local", enabled=True)
        db.session.add(account)
        db.session.flush()
        category = Category(
            account_id=account.id,
            category_id="ppv",
            category_name="US| PPV",
            is_ppv=True,
        )
        db.session.add(category)
        db.session.flush()
        channel = Channel(
            account_id=account.id,
            stream_id="9001",
            name="Test PPV Channel",
            category_id=category.id,
            is_ppv=is_ppv,
            ppv_enrichment_status=status,
        )
        db.session.add(channel)
        db.session.commit()
        channel_id = channel.id
    with app.app_context():
        return db.session.get(Channel, channel_id)


class TestCreateOrUpdateEvent:
    @pytest.mark.parametrize(
        "days_from_now,expect_event",
        [
            pytest.param(-(MAX_EVENT_AGE_DAYS + 1), False, id="reject_old_event"),
            pytest.param(MAX_EVENT_FUTURE_DAYS + 1, False, id="reject_far_future_event"),
            pytest.param(0, True, id="accept_valid_event"),
        ],
    )
    def test_age_validation(self, app, fixed_now, days_from_now, expect_event):
        with app.app_context():
            cal = _calendar_event(event_id=f"age-{days_from_now}", days_from_now=days_from_now)
            event, was_created = create_or_update_event(cal)
            if expect_event:
                assert event is not None
                assert was_created is True
                assert event.external_id == f"age-{days_from_now}"
            else:
                assert event is None
                assert was_created is False
                assert Event.query.count() == 0

    def test_updates_existing_event_without_duplicate(self, app, fixed_now):
        with app.app_context():
            cal = _calendar_event(event_id="dup-1", event_name="Old Title")
            first, created = create_or_update_event(cal)
            assert created is True
            db.session.commit()

            updated_cal = _calendar_event(
                event_id="dup-1",
                event_name="New Title",
                home_team="Home",
                away_team="Away",
            )
            event, was_created = create_or_update_event(updated_cal)
            db.session.commit()

            assert was_created is False
            assert event.id == first.id
            assert event.title == "New Title"
            assert Event.query.filter_by(external_id="dup-1").count() == 1

    def test_milb_source_normalized_to_model_constant(self, app, fixed_now):
        with app.app_context():
            cal = _calendar_event(event_id="milb-1", source="mlb_stats_api", sport="MiLB")
            event, was_created = create_or_update_event(cal)
            assert was_created is True
            assert event.source == Event.SOURCE_MLB_STATS

    def test_thesportsdb_baseball_sport_preserved_over_league_default(self, app, fixed_now):
        with app.app_context():
            cal = _calendar_event(
                event_id="mlb-baseball-sport",
                league_name="MLB",
                sport="Baseball",
                home_team="Boston Red Sox",
                away_team="New York Yankees",
            )
            event, was_created = create_or_update_event(cal)
            assert was_created is True
            assert event.sport == "Baseball"
            assert event.league_name == "MLB"

    def test_thesportsdb_mlb_league_sets_sport_not_milb_default(self, app, fixed_now):
        with app.app_context():
            cal = _calendar_event(
                event_id="mlb-giants-cubs",
                league_name="MLB",
                home_team="Chicago Cubs",
                away_team="San Francisco Giants",
            )
            event, was_created = create_or_update_event(cal)
            assert was_created is True
            assert event.sport == "MLB"
            assert event.league_name == "MLB"

    def test_update_corrects_stale_milb_sport_when_league_is_mlb(self, app, fixed_now):
        with app.app_context():
            cal = _calendar_event(
                event_id="stale-sport-1",
                league_name="MLB",
                home_team="Chicago Cubs",
                away_team="San Francisco Giants",
            )
            event, _ = create_or_update_event(cal)
            db.session.commit()
            event.sport = "MiLB"
            db.session.commit()

            event, was_created = create_or_update_event(cal)
            assert was_created is False
            assert event.sport == "MLB"

    def test_sync_event_sport_from_league_fixes_yankees_red_sox_row(self, app, fixed_now):
        with app.app_context():
            from services.ppv.persistence import sync_event_sport_from_league

            cal = _calendar_event(
                event_id="nyy-bos-1",
                league_name="MLB",
                home_team="Boston Red Sox",
                away_team="New York Yankees",
            )
            event, _ = create_or_update_event(cal)
            db.session.commit()
            event.sport = "MiLB"
            db.session.commit()

            assert sync_event_sport_from_league(event) is True
            assert event.sport == "MLB"


class TestLinkChannelToEvent:
    def test_creates_link_and_sets_matched_status(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            cal = _calendar_event(event_id="link-1")
            event, _ = create_or_update_event(cal)
            db.session.flush()

            link = link_channel_to_event(channel, event, 0.75, "calendar_high_confidence")
            db.session.commit()

            assert link.match_confidence == 0.75
            assert link.match_method == "calendar_high_confidence"
            assert channel.ppv_enrichment_status == "matched"
            assert channel.ppv_enrichment_error is None

    def test_upgrades_confidence_on_existing_link(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app)
            cal = _calendar_event(event_id="link-2")
            event, _ = create_or_update_event(cal)
            db.session.flush()
            link_channel_to_event(channel, event, 0.5, "calendar_low_confidence")
            db.session.commit()

            link_channel_to_event(channel, event, 0.9, "calendar_high_confidence")
            db.session.commit()

            link = EventChannelLink.query.filter_by(channel_id=channel.id, event_id=event.id).one()
            assert link.match_confidence == 0.9
            assert link.match_method == "calendar_high_confidence"

    def test_does_not_downgrade_confidence(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app)
            cal = _calendar_event(event_id="link-3")
            event, _ = create_or_update_event(cal)
            db.session.flush()
            link_channel_to_event(channel, event, 0.9, "calendar_high_confidence")
            db.session.commit()

            link_channel_to_event(channel, event, 0.4, "calendar_low_confidence")
            db.session.commit()

            link = EventChannelLink.query.filter_by(channel_id=channel.id, event_id=event.id).one()
            assert link.match_confidence == 0.9
            assert link.match_method == "calendar_high_confidence"


class TestPersistMatch:
    def test_sets_no_match_when_event_rejected(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            cal = _calendar_event(event_id="reject-1", days_from_now=-(MAX_EVENT_AGE_DAYS + 5))

            event, was_created = persist_match(channel, cal, 0.85, "calendar_high_confidence")

            assert event is None
            assert was_created is False
            assert channel.ppv_enrichment_status == "no_match"
            assert channel.ppv_enrichment_error is None
            assert EventChannelLink.query.count() == 0

    def test_persists_valid_match(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            cal = _calendar_event(event_id="match-1")

            event, was_created = persist_match(channel, cal, 0.85, "calendar_high_confidence")
            db.session.commit()

            assert event is not None
            assert was_created is True
            assert channel.ppv_enrichment_status == "matched"
            assert EventChannelLink.query.filter_by(channel_id=channel.id).count() == 1

    def test_sets_retry_pending_on_flush_error(self, app, fixed_now, monkeypatch):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            cal = _calendar_event(event_id="err-1")

            def boom():
                raise RuntimeError("simulated flush failure")

            monkeypatch.setattr(db.session, "flush", boom)

            event, was_created = persist_match(channel, cal, 0.85, "calendar_high_confidence")

            assert event is None
            assert was_created is False
            assert channel.ppv_enrichment_status == "retry_pending"
            assert "simulated flush failure" in channel.ppv_enrichment_error


class TestPersistEnhancedMatch:
    def test_delegates_to_persist_match(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            cal = _calendar_event(event_id="enh-1")
            result = EnhancedMatchResult(event=cal, confidence=0.88, match_method="enhanced")

            event, was_created = persist_enhanced_match(channel, result)
            db.session.commit()

            assert event is not None
            assert was_created is True
            assert channel.ppv_enrichment_status == "matched"

    def test_no_op_without_event(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            event, was_created = persist_enhanced_match(channel, EnhancedMatchResult())
            assert event is None
            assert was_created is False
            assert channel.ppv_enrichment_status == "pending"


class TestSyncEnrichmentStatusFromLinks:
    def test_updates_unmatched_ppv_channels_with_links(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app, status="pending")
            cal = _calendar_event(event_id="sync-1")
            event, _ = create_or_update_event(cal)
            db.session.flush()
            link = EventChannelLink(
                event_id=event.id,
                channel_id=channel.id,
                match_confidence=0.8,
                match_method="test",
            )
            db.session.add(link)
            channel.ppv_enrichment_status = "pending"
            db.session.commit()

            updated = sync_enrichment_status_from_links([channel.id])
            db.session.commit()

            assert updated == 1
            refreshed = db.session.get(Channel, channel.id)
            assert refreshed.ppv_enrichment_status == "matched"
            assert refreshed.ppv_enrichment_error is None

    def test_empty_channel_ids_returns_zero(self, app):
        with app.app_context():
            assert sync_enrichment_status_from_links([]) == 0


class TestClearEventLinksForChannels:
    def test_removes_links_for_channels(self, app, fixed_now):
        with app.app_context():
            channel = _ppv_channel(app)
            cal = _calendar_event(event_id="clear-1")
            event, _ = create_or_update_event(cal)
            db.session.flush()
            db.session.add(
                EventChannelLink(
                    event_id=event.id,
                    channel_id=channel.id,
                    match_confidence=0.7,
                    match_method="test",
                )
            )
            db.session.commit()

            deleted = clear_event_links_for_channels([channel.id])
            db.session.commit()

            assert deleted == 1
            assert EventChannelLink.query.filter_by(channel_id=channel.id).count() == 0

    def test_empty_ids_returns_zero(self, app):
        with app.app_context():
            assert clear_event_links_for_channels([]) == 0
