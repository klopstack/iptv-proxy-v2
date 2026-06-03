"""Tests for data retention helpers."""

from datetime import datetime, timedelta, timezone

from models import (
    Account,
    CachedImage,
    Category,
    Channel,
    ChannelHealthCheck,
    ChannelTag,
    EpgProgram,
    Event,
    EventChannelLink,
    Tag,
    db,
)
from services.channel_health_service import cleanup_old_health_checks
from services.epg.programs import cleanup_expired_programs
from services.event_retention import cleanup_old_events, get_event_retention_days
from services.image_cache_service import ImageCacheService
from services.scheduler_constants import DEFAULT_EVENT_RETENTION_DAYS
from services.sync_service import ChannelSyncService


class TestCleanupExpiredPrograms:
    def test_deletes_old_programs(self, app, db):
        from models import EpgChannel, EpgSource

        with app.app_context():
            source = EpgSource(name="Test", source_type="xmltv_url", url="http://example.com/epg.xml")
            db.session.add(source)
            db.session.flush()
            epg_ch = EpgChannel(source_id=source.id, channel_id="ch1", display_name="Ch1")
            db.session.add(epg_ch)
            db.session.flush()

            old_stop = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=10)
            db.session.add(
                EpgProgram(
                    epg_channel_id=epg_ch.id,
                    start_time=old_stop - timedelta(hours=2),
                    stop_time=old_stop,
                    title="Old Show",
                )
            )
            db.session.commit()

            deleted = cleanup_expired_programs(days_old=7)
            assert deleted == 1
            assert EpgProgram.query.count() == 0


class TestCleanupOldHealthChecks:
    def test_deletes_old_checks(self, app):
        with app.app_context():
            account = Account(name="Health", server="example.com", username="u", password="p")
            db.session.add(account)
            db.session.flush()
            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Cat",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="Ch",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            old = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=60)
            db.session.add(
                ChannelHealthCheck(
                    channel_id=channel.id,
                    result=ChannelHealthCheck.RESULT_SUCCESS,
                    checked_at=old,
                )
            )
            db.session.commit()

            deleted = cleanup_old_health_checks(days_old=30)
            assert deleted == 1


class TestPruneInactiveChannelTags:
    def test_prunes_tags_for_inactive_streams(self, app):
        with app.app_context():
            account = Account(name="Prune", server="example.com", username="u", password="p")
            db.session.add(account)
            db.session.flush()
            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Cat",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="inactive-1",
                name="Inactive",
                category_id=category.id,
                is_active=False,
            )
            db.session.add(channel)
            tag = Tag(name="OLDTAG")
            db.session.add(tag)
            db.session.flush()
            db.session.add(ChannelTag(account_id=account.id, stream_id="inactive-1", tag_id=tag.id))
            db.session.commit()

            pruned = ChannelSyncService.prune_inactive_channel_tags(account.id)
            assert pruned == 1
            assert ChannelTag.query.filter_by(account_id=account.id).count() == 0


class TestCleanupOldEvents:
    def test_default_retention_days(self):
        assert get_event_retention_days() == DEFAULT_EVENT_RETENTION_DAYS

    def test_deletes_old_events_and_links(self, app):
        with app.app_context():
            account = Account(name="Events", server="example.com", username="u", password="p")
            db.session.add(account)
            db.session.flush()
            category = Category(
                account_id=account.id,
                category_id="1",
                category_name="Cat",
            )
            db.session.add(category)
            db.session.flush()
            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="PPV",
                category_id=category.id,
                is_active=True,
            )
            db.session.add(channel)
            db.session.flush()

            now = datetime.now(timezone.utc).replace(tzinfo=None)
            old_event = Event(
                external_id="old-event",
                scheduled_at=now - timedelta(days=100),
                home_team_id="h1",
                home_team_name="Home",
                away_team_id="a1",
                away_team_name="Away",
                status=Event.STATUS_FINISHED,
            )
            recent_event = Event(
                external_id="recent-event",
                scheduled_at=now - timedelta(days=10),
                home_team_id="h2",
                home_team_name="Home2",
                away_team_id="a2",
                away_team_name="Away2",
                status=Event.STATUS_FINISHED,
            )
            db.session.add_all([old_event, recent_event])
            db.session.flush()
            old_event_id = old_event.id
            db.session.add(EventChannelLink(event_id=old_event_id, channel_id=channel.id))
            db.session.commit()

            deleted = cleanup_old_events(max_age_days=90)
            assert deleted == 1
            assert Event.query.count() == 1
            assert Event.query.filter_by(external_id="recent-event").count() == 1
            assert EventChannelLink.query.filter_by(event_id=old_event_id).count() == 0


class TestCleanupExpiredImageCache:
    def test_marks_expired_entries(self, app, tmp_path):
        with app.app_context():
            service = ImageCacheService(cache_dir=str(tmp_path))
            expired = CachedImage(
                url_hash="expired" + "0" * 57,
                original_url="https://example.com/old.png",
                status="cached",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=1),
            )
            fresh = CachedImage(
                url_hash="freshhh" + "0" * 57,
                original_url="https://example.com/new.png",
                status="cached",
                expires_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
            )
            db.session.add_all([expired, fresh])
            db.session.commit()

            removed = service.cleanup_expired(delete_files=False)
            assert removed == 1
            assert expired.status == "expired"
            assert fresh.status == "cached"
