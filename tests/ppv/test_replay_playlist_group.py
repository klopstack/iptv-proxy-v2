"""Integration: matched Flo archive events appear under Replay group (TODO 129 Track C)."""

from datetime import datetime, timedelta, timezone

import pytest

from models import Account, Channel, Event, EventChannelLink, db
from services.playlist_format_service import render_account_m3u_playlist
from services.ppv.visibility import PPVVisibilityService
from services.url_service import get_proxy_base_url


class TestFloReplayPlaylistGroup:
    def test_matched_past_flosp_event_in_replay_group(self, app):
        with app.app_context():
            account = Account(
                name="Flo Test",
                server="http://test.com",
                username="flo",
                password="test",
                ppv_visibility="group_live_replay",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="flosp-110",
                name="Flo (FLSP) 110: 2025 Occidental vs Chapman - Mens - 22/10 19:00",
                is_ppv=True,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

            past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)
            event = Event(
                external_id="flosp-occidental-chapman",
                scheduled_at=past,
                home_team_id="occ",
                home_team_name="Occidental Tigers",
                away_team_id="chap",
                away_team_name="Chapman Panthers",
                status=Event.STATUS_FINISHED,
                is_ppv=True,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.classify_live_replay_channel(channel) == PPVVisibilityService.PPV_GROUP_HISTORICAL

            with app.test_request_context("/"):
                m3u = render_account_m3u_playlist(
                    [channel],
                    account=account,
                    proxy_base=get_proxy_base_url(),
                    use_proxy=True,
                    proxy_icons=False,
                    primary_cred=None,
                )
            assert 'group-title="PPV - Historical"' in m3u
            assert 'group-title="PPV - Replay"' not in m3u
            assert channel.name in m3u

    def test_recent_live_event_stays_live_group(self, app):
        with app.app_context():
            account = Account(
                name="Live Test",
                server="http://test.com",
                ppv_visibility="group_live_replay",
            )
            db.session.add(account)
            db.session.commit()

            channel = Channel(
                account_id=account.id,
                stream_id="live-1",
                name="US: World Cup: Team A vs Team B",
                is_ppv=True,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

            soon = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=2)
            event = Event(
                external_id="wc-live",
                scheduled_at=soon,
                home_team_id="a",
                home_team_name="Team A",
                away_team_id="b",
                away_team_name="Team B",
                status=Event.STATUS_SCHEDULED,
                is_ppv=True,
            )
            db.session.add(event)
            db.session.flush()
            db.session.add(EventChannelLink(event_id=event.id, channel_id=channel.id))
            db.session.commit()

            service = PPVVisibilityService(account)
            assert service.classify_live_replay_channel(channel) == PPVVisibilityService.PPV_GROUP_LIVE
