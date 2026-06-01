"""Tests for stream fallback resolution service."""

from models import Account, Category, Channel, ChannelLink, Credential, db
from services.stream_fallback_service import (
    LINK_TYPE_BACKUP,
    build_upstream_url,
    get_backup_channel_ids,
    invalidate_cache,
    is_fallback_enabled,
    probe_and_select_upstream,
    resolve_sources,
    source_role_label,
)


class TestStreamFallbackService:
    def _make_channels(self):
        account = Account(
            name="Test",
            server="provider.example",
            username="u",
            password="p",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        cat_plain = Category(account_id=account.id, category_id="1", category_name="US| MILB PPV")
        cat_bk = Category(account_id=account.id, category_id="2", category_name="US| MILB PPV ⁽ᴮᴷ⁾")
        db.session.add_all([cat_plain, cat_bk])
        db.session.commit()

        primary = Channel(
            account_id=account.id,
            stream_id="100",
            name="Clearwater vs Dunedin :Milb  01",
            category_id=cat_plain.id,
            is_active=True,
        )
        backup = Channel(
            account_id=account.id,
            stream_id="200",
            name="US (MiLB 001) | Dunedin @ Clearwater (2026-05-31 12:00:00)",
            category_id=cat_bk.id,
            is_active=True,
        )
        db.session.add_all([primary, backup])
        db.session.commit()

        link = ChannelLink(
            channel_id=primary.id,
            source_channel_id=backup.id,
            link_type=LINK_TYPE_BACKUP,
            time_offset_hours=0,
            auto_detected=True,
        )
        db.session.add(link)
        db.session.commit()
        invalidate_cache()
        return account, primary, backup

    def test_resolve_sources_with_backup(self, app):
        with app.app_context():
            account, primary, backup = self._make_channels()
            sources = resolve_sources(account.id, primary.stream_id)
            assert len(sources) == 2
            assert sources[0].role == "primary"
            assert sources[0].stream_id == "100"
            assert sources[1].role == "backup"
            assert sources[1].stream_id == "200"
            assert backup.id in get_backup_channel_ids()

    def test_resolve_sources_disabled(self, app):
        with app.app_context():
            from models import Settings

            account, primary, _ = self._make_channels()
            Settings.set("stream_fallback_enabled", "false")
            invalidate_cache()
            sources = resolve_sources(account.id, primary.stream_id)
            assert len(sources) == 1
            assert get_backup_channel_ids() == set()

    def test_build_upstream_url(self, app):
        with app.app_context():
            account, primary, _ = self._make_channels()
            cred = Credential(account_id=account.id, username="user1", password="pass1", enabled=True)
            db.session.add(cred)
            db.session.commit()
            url = build_upstream_url(account, cred, primary.stream_id, "ts")
            assert url == f"https://{account.server}/live/user1/pass1/100.ts"

    def test_probe_selects_backup_when_primary_fails(self, app, monkeypatch):
        with app.app_context():
            account, primary, backup = self._make_channels()
            cred = Credential(account_id=account.id, username="user1", password="pass1", enabled=True)
            db.session.add(cred)
            db.session.commit()

            def fake_head(url, user_agent, timeout=(10, 10)):
                if primary.stream_id in url:
                    return 503, None, None
                if backup.stream_id in url:
                    return 200, {}, None
                return 404, None, None

            from services import stream_proxy_service

            monkeypatch.setattr(
                stream_proxy_service.StreamConnectivityTester, "test_upstream_head", staticmethod(fake_head)
            )

            sources = resolve_sources(account.id, primary.stream_id)
            chain, index, error = probe_and_select_upstream(
                account,
                cred,
                sources,
                "ts",
                "test-agent",
                stream_proxy_service.StreamConnectivityTester,
            )
            assert error is None
            assert index == 1
            assert chain[1][0] == backup.stream_id

    def test_source_role_label(self):
        assert source_role_label(0) == "primary"
        assert source_role_label(1) == "backup"

    def test_is_fallback_enabled_default(self, app):
        with app.app_context():
            assert is_fallback_enabled() is True
