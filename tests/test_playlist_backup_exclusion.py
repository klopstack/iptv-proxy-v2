"""Tests for hiding backup channels from client playlists."""

from models import Account, Category, Channel, ChannelLink, db
from services.channel_query_service import ChannelQueryService
from services.stream_fallback_service import LINK_TYPE_BACKUP, invalidate_cache


class TestPlaylistBackupExclusion:
    def test_channels_for_account_excludes_backup_targets(self, app):
        with app.app_context():
            account = Account(
                name="Test",
                server="provider.example",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="1", category_name="PPV")
            db.session.add(category)
            db.session.commit()

            primary = Channel(
                account_id=account.id,
                stream_id="1",
                name="Primary Event",
                category_id=category.id,
                is_active=True,
            )
            backup = Channel(
                account_id=account.id,
                stream_id="2",
                name="Backup Event",
                category_id=category.id,
                is_active=True,
            )
            other = Channel(
                account_id=account.id,
                stream_id="3",
                name="Regular Channel",
                category_id=category.id,
                is_active=True,
            )
            db.session.add_all([primary, backup, other])
            db.session.commit()

            db.session.add(
                ChannelLink(
                    channel_id=primary.id,
                    source_channel_id=backup.id,
                    link_type=LINK_TYPE_BACKUP,
                    time_offset_hours=0,
                )
            )
            db.session.commit()
            invalidate_cache()

            channels = ChannelQueryService.channels_for_account(account.id, apply_filters=False)
            stream_ids = {ch.stream_id for ch in channels}
            assert "1" in stream_ids
            assert "3" in stream_ids
            assert "2" not in stream_ids

    def test_playlist_m3u_excludes_backup(self, app, client):
        with app.app_context():
            account = Account(
                name="M3U Test",
                server="provider.example",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="1", category_name="Sports")
            db.session.add(category)
            db.session.commit()

            primary = Channel(
                account_id=account.id,
                stream_id="10",
                name="Game Primary",
                category_id=category.id,
                is_active=True,
            )
            backup = Channel(
                account_id=account.id,
                stream_id="20",
                name="Game Backup",
                category_id=category.id,
                is_active=True,
            )
            db.session.add_all([primary, backup])
            db.session.commit()

            db.session.add(
                ChannelLink(
                    channel_id=primary.id,
                    source_channel_id=backup.id,
                    link_type=LINK_TYPE_BACKUP,
                )
            )
            db.session.commit()
            invalidate_cache()
            account_id = account.id

        response = client.get(f"/playlist/{account_id}.m3u?proxy_icons=false")
        assert response.status_code == 200
        body = response.data.decode("utf-8")
        assert body.count("#EXTINF") == 1
        assert "Game Primary" in body
        assert "Game Backup" not in body
