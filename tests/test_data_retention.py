"""Tests for data retention helpers."""

from datetime import datetime, timedelta, timezone

import pytest

from models import Account, Category, Channel, ChannelHealthCheck, ChannelTag, EpgProgram, Tag, db
from services.channel_health_service import cleanup_old_health_checks
from services.epg.programs import cleanup_expired_programs
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
