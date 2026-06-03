"""Tests for broadcast language detection and client language preference."""

import json
from datetime import datetime, timezone

import pytest

from models import Account, Category, Channel, ChannelLink, Event, EventChannelLink, XtreamCredential, db
from services.backup_pair_detection import detect_backup_pairs
from services.channel_query_service import ChannelQueryService
from services.language_detection_service import detect_broadcast_language
from services.language_preference_service import select_preferred_channels
from services.quality_service import QualityService
from services.stream_fallback_service import LINK_TYPE_BACKUP, invalidate_cache


class TestLanguageDetection:
    def test_explicit_espanol_pattern(self):
        result = detect_broadcast_language("US (Peacock 099) | Rangers vs. Red Sox (Español)")
        assert result.broadcast_language == "es"
        assert result.language_source == "explicit_name"
        assert result.language_confidence >= 0.9

    def test_peacock_network_default_english(self):
        result = detect_broadcast_language("US (Peacock 098) | Rangers at Red Sox")
        assert result.broadcast_language == "en"
        assert result.language_source == "network_default"

    def test_explicit_wins_over_network_default(self):
        result = detect_broadcast_language("US (Peacock 099) | Game (Español)")
        assert result.broadcast_language == "es"
        assert result.language_source == "explicit_name"

    def test_unknown_channel_has_no_detection(self):
        result = detect_broadcast_language("Random Sports Channel HD")
        assert result.broadcast_language is None
        assert result.language_source is None


class TestLanguagePreferenceSelection:
    def _make_event_group(self, app):
        with app.app_context():
            account = Account(
                name="Lang Test",
                server="provider.example",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(
                account_id=account.id,
                category_id="ppv1",
                category_name="US| PPV EVENT",
            )
            db.session.add(category)
            db.session.commit()

            event = Event(
                external_id="evt-lang-1",
                source="thesportsdb",
                title="Rangers vs Red Sox",
                sport="Baseball",
                home_team_id="1",
                home_team_name="Red Sox",
                away_team_id="2",
                away_team_name="Rangers",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
                status="scheduled",
            )
            db.session.add(event)
            db.session.commit()

            ch_en = Channel(
                account_id=account.id,
                stream_id="098",
                name="US (Peacock 098) | Rangers at Red Sox",
                category_id=category.id,
                is_active=True,
                is_ppv=True,
                broadcast_language="en",
            )
            ch_es = Channel(
                account_id=account.id,
                stream_id="099",
                name="US (Peacock 099) | Rangers vs. Red Sox (Español)",
                category_id=category.id,
                is_active=True,
                is_ppv=True,
                broadcast_language="es",
            )
            db.session.add_all([ch_en, ch_es])
            db.session.commit()

            db.session.add_all(
                [
                    EventChannelLink(
                        event_id=event.id,
                        channel_id=ch_en.id,
                        match_confidence=0.95,
                        match_method="calendar_high_confidence",
                    ),
                    EventChannelLink(
                        event_id=event.id,
                        channel_id=ch_es.id,
                        match_confidence=0.95,
                        match_method="calendar_high_confidence",
                    ),
                ]
            )
            db.session.commit()

            return account.id, ch_en.id, ch_es.id

    def test_preferred_english_keeps_only_en_feed(self, app):
        account_id, ch_en_id, ch_es_id = self._make_event_group(app)
        with app.app_context():
            channels = Channel.query.filter_by(account_id=account_id).all()
            result = select_preferred_channels(channels, ["en"], fallback="unknown")
            result_ids = {ch.id for ch in result}
            assert ch_en_id in result_ids
            assert ch_es_id not in result_ids

    def test_xtream_output_applies_language_preference(self, app, client):
        account_id, ch_en_id, ch_es_id = self._make_event_group(app)
        with app.app_context():
            cred = XtreamCredential(
                username="lang_user",
                password="lang_pass",
                account_id=account_id,
                enabled=True,
                use_filters=False,
                preferred_languages=json.dumps(["en"]),
                language_fallback="unknown",
            )
            db.session.add(cred)
            db.session.commit()

        response = client.get(
            "/player_api.php",
            query_string={
                "username": "lang_user",
                "password": "lang_pass",
                "action": "get_live_streams",
            },
        )
        assert response.status_code == 200
        streams = response.json
        names = {item.get("name", "") for item in streams}
        assert any("Peacock 098" in name for name in names)
        assert not any("Español" in name for name in names)

    def test_channel_query_service_pipeline_order(self, app):
        account_id, ch_en_id, ch_es_id = self._make_event_group(app)
        with app.app_context():
            channels = ChannelQueryService.channels_for_account(
                account_id,
                apply_filters=False,
                preferred_languages='["en"]',
                language_fallback="unknown",
            )
            result_ids = {ch.id for ch in channels}
            assert ch_en_id in result_ids
            assert ch_es_id not in result_ids


class TestBackupPairLanguageSkip:
    def test_event_multi_feed_does_not_pair_cross_language(self, app):
        with app.app_context():
            account = Account(
                name="Backup Lang",
                server="provider.example",
                username="u",
                password="p",
                enabled=True,
            )
            db.session.add(account)
            db.session.commit()

            category = Category(
                account_id=account.id,
                category_id="ppv2",
                category_name="US| PPV EVENT",
            )
            db.session.add(category)
            db.session.commit()

            event = Event(
                external_id="evt-backup-lang",
                source="thesportsdb",
                title="Cross Language Event",
                sport="Baseball",
                home_team_id="1",
                home_team_name="Team A",
                away_team_id="2",
                away_team_name="Team B",
                scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None),
                status="scheduled",
            )
            db.session.add(event)
            db.session.commit()

            ch_en = Channel(
                account_id=account.id,
                stream_id="en1",
                name="Peacock EN Feed",
                category_id=category.id,
                is_active=True,
                broadcast_language="en",
            )
            ch_es = Channel(
                account_id=account.id,
                stream_id="es1",
                name="Peacock ES Feed (Español)",
                category_id=category.id,
                is_active=True,
                broadcast_language="es",
            )
            db.session.add_all([ch_en, ch_es])
            db.session.commit()

            db.session.add_all(
                [
                    EventChannelLink(event_id=event.id, channel_id=ch_en.id, match_confidence=0.9),
                    EventChannelLink(event_id=event.id, channel_id=ch_es.id, match_confidence=0.9),
                ]
            )
            db.session.commit()

            stats = detect_backup_pairs(account.id)
            assert stats["links_created"] == 0
            assert ChannelLink.query.filter_by(link_type=LINK_TYPE_BACKUP).count() == 0
            invalidate_cache()


class TestCollapseDuplicatesLanguage:
    def test_keeps_both_when_languages_differ_but_names_match(self):
        channels = [
            {
                "stream_id": "1",
                "cleaned_name": "Same Game Name",
                "broadcast_language": "en",
                "tags": ["HD"],
            },
            {
                "stream_id": "2",
                "cleaned_name": "Same Game Name",
                "broadcast_language": "es",
                "tags": ["HD"],
            },
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 2
        langs = {item.get("broadcast_language") for item in result}
        assert langs == {"en", "es"}

    def test_collapses_same_language_duplicates(self):
        channels = [
            {
                "stream_id": "1",
                "cleaned_name": "Same Game Name",
                "broadcast_language": "en",
                "tags": ["HD"],
            },
            {
                "stream_id": "2",
                "cleaned_name": "Same Game Name",
                "broadcast_language": "en",
                "tags": ["FHD"],
            },
        ]
        result = QualityService.collapse_duplicates(channels)
        assert len(result) == 1


class TestXtreamLanguageCredentialCrud:
    def test_create_and_update_language_fields(self, app, client, test_account):
        with app.app_context():
            account_id = test_account

        create_resp = client.post(
            "/api/xtream-credentials",
            json={
                "username": "lang_crud",
                "password": "secret",
                "account_id": account_id,
                "preferred_languages": ["en", "es"],
                "language_fallback": "hide",
            },
        )
        assert create_resp.status_code == 201
        data = create_resp.json
        assert data["preferred_languages"] == ["en", "es"]
        assert data["language_fallback"] == "hide"

        cred_id = data["id"]
        update_resp = client.put(
            f"/api/xtream-credentials/{cred_id}",
            json={
                "preferred_languages": "en,fr",
                "language_fallback": "show_all",
            },
        )
        assert update_resp.status_code == 200
        updated = update_resp.json
        assert updated["preferred_languages"] == ["en", "fr"]
        assert updated["language_fallback"] == "show_all"

    def test_rejects_invalid_language_fallback(self, app, client, test_account):
        with app.app_context():
            account_id = test_account

        response = client.post(
            "/api/xtream-credentials",
            json={
                "username": "bad_fallback",
                "password": "secret",
                "account_id": account_id,
                "language_fallback": "invalid_mode",
            },
        )
        assert response.status_code == 400
