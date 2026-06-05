"""Tests for PPV channel rename formatting with timezone support."""

from datetime import datetime, timezone

import pytest

from models import Account, Category, Channel, Event, EventChannelLink, db
from services.datetime_utils import DEFAULT_DISPLAY_TIMEZONE, resolve_ppv_rename_timezone, to_display_timezone
from services.playlist_format_service import _apply_ppv_rename_format, channel_display_name, render_account_m3u_playlist


class TestToDisplayTimezone:
    def test_converts_utc_to_eastern(self):
        utc_dt = datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc)
        local = to_display_timezone(utc_dt, "America/New_York")
        assert local.hour == 20
        assert local.day == 5

    def test_treats_naive_as_utc(self):
        naive = datetime(2026, 1, 6, 1, 20)
        local = to_display_timezone(naive, "America/New_York")
        assert local.hour == 20
        assert local.day == 5

    def test_defaults_to_eastern_when_timezone_unset(self):
        utc_dt = datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc)
        local = to_display_timezone(utc_dt, None)
        assert local.tzinfo.key == DEFAULT_DISPLAY_TIMEZONE

    def test_invalid_timezone_falls_back_to_default(self):
        utc_dt = datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc)
        local = to_display_timezone(utc_dt, "Not/A/Timezone")
        assert local.tzinfo.key == DEFAULT_DISPLAY_TIMEZONE


class TestResolvePpvRenameTimezone:
    def test_credential_override_wins(self):
        assert (
            resolve_ppv_rename_timezone(
                credential_tz="America/Los_Angeles",
                account_tz="America/New_York",
            )
            == "America/Los_Angeles"
        )

    def test_falls_back_to_account(self):
        assert resolve_ppv_rename_timezone(credential_tz=None, account_tz="America/Chicago") == "America/Chicago"

    def test_returns_none_when_both_unset(self):
        assert resolve_ppv_rename_timezone(credential_tz=None, account_tz=None) is None


class TestChannelDisplayName:
    def test_credential_timezone_override(self, app):
        with app.app_context():
            channel = Channel(id=1, name="PPV 1", cleaned_name="PPV 1")
            account = Account(
                name="Test",
                server="example.com",
                ppv_rename_format="{home_team} vs {away_team} - {start_time} {date}",
                ppv_rename_timezone="America/New_York",
            )
            event = Event(
                home_team_id="1",
                away_team_id="2",
                home_team_name="Chiefs",
                away_team_name="Eagles",
                external_id="evt-display-1",
                scheduled_at=datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc),
            )

            eastern = channel_display_name(
                channel,
                account=account,
                event=event,
                ppv_rename_timezone_override="America/New_York",
            )
            pacific = channel_display_name(
                channel,
                account=account,
                event=event,
                ppv_rename_timezone_override="America/Los_Angeles",
            )

            assert eastern == "Chiefs vs Eagles - 8:20 PM Jan 5"
            assert pacific == "Chiefs vs Eagles - 5:20 PM Jan 5"


class TestApplyPpvRenameFormat:
    def test_formats_start_time_and_date_in_configured_timezone(self, app):
        with app.app_context():
            channel = Channel(id=1, name="PPV 1", cleaned_name="PPV 1")
            event = Event(
                league_name="NFL",
                sport="Football",
                home_team_name="Chiefs",
                away_team_name="Eagles",
                home_team_id="1",
                away_team_id="2",
                external_id="evt-1",
                scheduled_at=datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc),
            )
            fmt = "{league} {sport}: {home_team} vs {away_team} - {start_time} {date}"

            result = _apply_ppv_rename_format(
                channel,
                fmt,
                event,
                timezone_name="America/New_York",
            )

            assert result == "NFL Football: Chiefs vs Eagles - 8:20 PM Jan 5"

    def test_utc_timezone_shows_utc_values(self, app):
        with app.app_context():
            channel = Channel(id=1, name="PPV 1", cleaned_name="PPV 1")
            event = Event(
                league_name="NFL",
                sport="Football",
                home_team_name="Chiefs",
                away_team_name="Eagles",
                home_team_id="1",
                away_team_id="2",
                external_id="evt-2",
                scheduled_at=datetime(2026, 1, 6, 1, 20, tzinfo=timezone.utc),
            )
            fmt = "{start_time} {date}"

            result = _apply_ppv_rename_format(
                channel,
                fmt,
                event,
                timezone_name="UTC",
            )

            assert result == "1:20 AM Jan 6"


class TestPpvRenameFormatPlaylistIntegration:
    @pytest.fixture
    def ppv_account_with_rename(self, app):
        with app.app_context():
            account = Account(
                name="PPV Provider",
                server="ppv.example.com",
                username="user",
                password="pass",
                enabled=True,
                ppv_rename_format="{home_team} vs {away_team} - {start_time} {date}",
                ppv_rename_timezone="America/Los_Angeles",
            )
            db.session.add(account)
            db.session.commit()

            category = Category(account_id=account.id, category_id="ppv", category_name="PPV")
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=account.id,
                stream_id="1",
                name="PPV 1",
                cleaned_name="PPV 1",
                category_id=category.id,
                is_active=True,
                is_visible=True,
                is_ppv=True,
            )
            db.session.add(channel)
            db.session.flush()

            event = Event(
                external_id="evt-playlist-1",
                home_team_id="1",
                away_team_id="2",
                home_team_name="Lakers",
                away_team_name="Warriors",
                scheduled_at=datetime(2026, 1, 6, 3, 0, tzinfo=timezone.utc),
            )
            db.session.add(event)
            db.session.flush()

            db.session.add(
                EventChannelLink(
                    event_id=event.id,
                    channel_id=channel.id,
                    match_confidence=0.95,
                    match_method="test",
                )
            )
            db.session.commit()
            yield account.id

    def test_playlist_uses_timezone_for_ppv_rename(self, app, ppv_account_with_rename):
        with app.app_context():
            account = db.session.get(Account, ppv_account_with_rename)
            channels = Channel.query.filter_by(account_id=account.id, is_active=True).all()
            m3u = render_account_m3u_playlist(
                channels,
                account=account,
                proxy_base="http://proxy.example.com",
                use_proxy=False,
                proxy_icons=False,
                primary_cred=account.get_primary_credential(),
            )

        assert "Lakers vs Warriors - 7:00 PM Jan 5" in m3u


class TestPpvRenameFormatApi:
    def test_update_ppv_rename_timezone(self, app, client, test_account):
        response = client.put(
            f"/api/accounts/{test_account}/ppv-rename-format",
            json={
                "ppv_rename_format": "{home_team} vs {away_team}",
                "ppv_rename_timezone": "America/Chicago",
            },
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["ppv_rename_timezone"] == "America/Chicago"

        with app.app_context():
            account = db.session.get(Account, test_account)
            assert account.ppv_rename_timezone == "America/Chicago"

    def test_rejects_invalid_timezone(self, app, client, test_account):
        response = client.put(
            f"/api/accounts/{test_account}/ppv-rename-format",
            json={"ppv_rename_timezone": "Not/A/Timezone"},
        )
        assert response.status_code == 400


class TestXtreamCredentialPpvRenameTimezone:
    def test_create_credential_with_timezone(self, app, client, test_account):
        response = client.post(
            "/api/xtream-credentials",
            json={
                "username": "tz_user",
                "password": "tz_pass",
                "account_id": test_account,
                "ppv_rename_timezone": "America/Chicago",
            },
        )
        assert response.status_code == 201
        assert response.json["ppv_rename_timezone"] == "America/Chicago"

    def test_rejects_invalid_xtream_timezone(self, app, client, test_account):
        response = client.post(
            "/api/xtream-credentials",
            json={
                "username": "bad_tz_user",
                "password": "tz_pass",
                "account_id": test_account,
                "ppv_rename_timezone": "Not/A/Timezone",
            },
        )
        assert response.status_code == 400
