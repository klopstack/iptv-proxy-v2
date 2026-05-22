"""Contract tests for unified channel selection."""

import json
from datetime import datetime, timedelta, timezone

from models import (
    Account,
    Category,
    Channel,
    ChannelTag,
    Event,
    EventChannelLink,
    PlaylistConfig,
    Tag,
    XtreamCredential,
    db,
)
from services.channel_query_service import ChannelQueryService


def test_tags_are_ids_detection():
    assert ChannelQueryService._tags_are_ids([1, 2], []) is True
    assert ChannelQueryService._tags_are_ids([], [5]) is True
    assert ChannelQueryService._tags_are_ids([], ["PPV"]) is False
    assert ChannelQueryService._tags_are_ids([], []) is False
    assert ChannelQueryService._tags_are_ids([1], ["PPV"]) is False


def test_apply_tag_filter_exclude_precedence():
    assert (
        ChannelQueryService.apply_tag_filter(
            {"US", "PPV"},
            include_tags=["US"],
            exclude_tags=["PPV"],
            match_mode="any",
        )
        is False
    )


def test_channels_for_account_consistency(app):
    """Single-account query returns active filtered channels."""
    with app.app_context():
        account = Account(name="CQ", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()
        db.session.add(
            Channel(account_id=account.id, stream_id=42, name="Test Ch", is_active=True)
        )
        db.session.commit()

        channels = ChannelQueryService.channels_for_account(
            account.id,
            apply_filters=False,
            apply_ppv_visibility=False,
        )
        ids = {int(ch.stream_id) for ch in channels}
        assert ids == {42}


def test_playlist_config_exclude_tag_ids_only(app):
    """exclude_tags as IDs works when include_tags is empty."""
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        ppv_tag = Tag(name="PPV")
        hd_tag = Tag(name="HD")
        db.session.add_all([ppv_tag, hd_tag])
        db.session.commit()

        ch_ppv = Channel(account_id=account.id, stream_id="ppv", name="PPV Ch", is_active=True)
        ch_hd = Channel(account_id=account.id, stream_id="hd", name="HD Ch", is_active=True)
        ch_plain = Channel(account_id=account.id, stream_id="plain", name="Plain Ch", is_active=True)
        db.session.add_all([ch_ppv, ch_hd, ch_plain])
        db.session.commit()

        db.session.add_all(
            [
                ChannelTag(account_id=account.id, stream_id="ppv", tag_id=ppv_tag.id),
                ChannelTag(account_id=account.id, stream_id="hd", tag_id=hd_tag.id),
            ]
        )
        db.session.commit()

        cfg = PlaylistConfig(
            name="No PPV",
            include_tags=json.dumps([]),
            exclude_tags=json.dumps([ppv_tag.id]),
            enabled=True,
        )
        db.session.add(cfg)
        db.session.commit()

        channels = ChannelQueryService.channels_for_playlist_config(
            cfg,
            apply_filters=False,
            apply_ppv_visibility=False,
        )
        assert {ch.stream_id for ch in channels} == {"hd", "plain"}


def test_playlist_config_exclude_tag_names_only(app):
    """exclude_tags as names works when include_tags is empty."""
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        ppv_tag = Tag(name="PPV")
        hd_tag = Tag(name="HD")
        db.session.add_all([ppv_tag, hd_tag])
        db.session.commit()

        ch_ppv = Channel(account_id=account.id, stream_id="ppv", name="PPV Ch", is_active=True)
        ch_hd = Channel(account_id=account.id, stream_id="hd", name="HD Ch", is_active=True)
        ch_plain = Channel(account_id=account.id, stream_id="plain", name="Plain Ch", is_active=True)
        db.session.add_all([ch_ppv, ch_hd, ch_plain])
        db.session.commit()

        db.session.add_all(
            [
                ChannelTag(account_id=account.id, stream_id="ppv", tag_id=ppv_tag.id),
                ChannelTag(account_id=account.id, stream_id="hd", tag_id=hd_tag.id),
            ]
        )
        db.session.commit()

        cfg = PlaylistConfig(
            name="No PPV",
            include_tags=json.dumps([]),
            exclude_tags=json.dumps(["PPV"]),
            enabled=True,
        )
        db.session.add(cfg)
        db.session.commit()

        channels = ChannelQueryService.channels_for_playlist_config(
            cfg,
            apply_filters=False,
            apply_ppv_visibility=False,
        )
        assert {ch.stream_id for ch in channels} == {"hd", "plain"}


def test_playlist_config_include_tag_ids(app):
    """include_tags as IDs still uses the ID filter path."""
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        hd_tag = Tag(name="HD")
        db.session.add(hd_tag)
        db.session.commit()

        ch_hd = Channel(account_id=account.id, stream_id="hd", name="HD Ch", is_active=True)
        ch_plain = Channel(account_id=account.id, stream_id="plain", name="Plain Ch", is_active=True)
        db.session.add_all([ch_hd, ch_plain])
        db.session.commit()

        db.session.add(ChannelTag(account_id=account.id, stream_id="hd", tag_id=hd_tag.id))
        db.session.commit()

        cfg = PlaylistConfig(
            name="HD Only",
            include_tags=json.dumps([hd_tag.id]),
            exclude_tags=json.dumps([]),
            enabled=True,
        )
        db.session.add(cfg)
        db.session.commit()

        channels = ChannelQueryService.channels_for_playlist_config(
            cfg,
            apply_filters=False,
            apply_ppv_visibility=False,
        )
        assert {ch.stream_id for ch in channels} == {"hd"}


def test_multi_account_playlist_config(app):
    """PlaylistConfig merges channels from multiple accounts."""
    with app.app_context():
        acc1 = Account(name="A1", server="s1", username="u", password="p", enabled=True)
        acc2 = Account(name="A2", server="s2", username="u", password="p", enabled=True)
        db.session.add_all([acc1, acc2])
        db.session.commit()

        for acc, sid in [(acc1, 1), (acc2, 2)]:
            db.session.add(
                Channel(
                    account_id=acc.id,
                    stream_id=sid,
                    name=f"Ch {sid}",
                    is_active=True,
                )
            )
        db.session.commit()

        cfg = PlaylistConfig(
            name="Multi",
            include_accounts=json.dumps([acc1.id, acc2.id]),
            enabled=True,
        )
        db.session.add(cfg)
        db.session.commit()

        channels = ChannelQueryService.channels_for_playlist_config(
            cfg,
            apply_filters=False,
            apply_ppv_visibility=False,
        )
        account_ids = {ch.account_id for ch in channels}
        assert account_ids == {acc1.id, acc2.id}
        assert len(channels) == 2


def test_ppv_hide_inactive_via_channel_query(app):
    """PPV channels with past events are hidden when account uses hide_inactive."""
    with app.app_context():
        account = Account(
            name="PPV",
            server="s",
            username="u",
            password="p",
            enabled=True,
            ppv_visibility="hide_inactive",
        )
        db.session.add(account)
        db.session.commit()

        past = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        event = Event(
            external_id="evt-past",
            title="Past Game",
            home_team_id="1",
            home_team_name="A",
            away_team_id="2",
            away_team_name="B",
            scheduled_at=past,
            status=Event.STATUS_FINISHED,
        )
        db.session.add(event)
        db.session.commit()

        ch = Channel(
            account_id=account.id,
            stream_id="99",
            name="PPV Past",
            is_active=True,
            is_ppv=True,
            ppv_enrichment_status="matched",
        )
        db.session.add(ch)
        db.session.commit()
        db.session.add(EventChannelLink(channel_id=ch.id, event_id=event.id))
        db.session.commit()

        channels = ChannelQueryService.channels_for_account(account.id)
        assert all(c.stream_id != "99" for c in channels)


def test_apply_ppv_visibility_to_channels_multi_account(app):
    """Shared PPV helper filters each account group independently."""
    with app.app_context():
        acc1 = Account(
            name="A1",
            server="s",
            username="u",
            password="p",
            enabled=True,
            ppv_visibility="hide_all",
        )
        acc2 = Account(
            name="A2",
            server="s",
            username="u",
            password="p",
            enabled=True,
            ppv_visibility="show_all",
        )
        db.session.add_all([acc1, acc2])
        db.session.commit()

        ch1 = Channel(account_id=acc1.id, stream_id="1", name="Hidden PPV", is_active=True, is_ppv=True)
        ch2 = Channel(account_id=acc2.id, stream_id="2", name="Visible PPV", is_active=True, is_ppv=True)
        db.session.add_all([ch1, ch2])
        db.session.commit()

        visible = ChannelQueryService.apply_ppv_visibility_to_channels([ch1, ch2])
        assert {ch.stream_id for ch in visible} == {"2"}


def test_epg_channel_id_for_ppv_event(app):
    """PPV channels with linked events use event-{id} EPG identifiers."""
    with app.app_context():
        account = Account(name="A", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()
        event = Event(
            external_id="x",
            title="Game",
            home_team_id="1",
            home_team_name="H",
            away_team_id="2",
            away_team_name="A",
            scheduled_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
        )
        db.session.add(event)
        db.session.commit()
        ch = Channel(account_id=account.id, stream_id="1", name="PPV", is_active=True, is_ppv=True)
        db.session.add(ch)
        db.session.commit()
        db.session.add(EventChannelLink(channel_id=ch.id, event_id=event.id))
        db.session.commit()

        assert ChannelQueryService.epg_channel_id_for_channel(ch) == f"event-{event.id}"


def test_playlist_and_xtream_channel_counts_match(app, client):
    """Multi-account playlist and Xtream live list expose the same channels."""
    with app.app_context():
        acc1 = Account(name="X1", server="s1", username="u", password="p", enabled=True)
        acc2 = Account(name="X2", server="s2", username="u", password="p", enabled=True)
        db.session.add_all([acc1, acc2])
        db.session.commit()
        for acc, sid in [(acc1, 10), (acc2, 20)]:
            db.session.add(
                Channel(account_id=acc.id, stream_id=str(sid), name=f"Ch{sid}", is_active=True)
            )
        db.session.commit()

        cfg = PlaylistConfig(
            name="Both",
            include_accounts=json.dumps([acc1.id, acc2.id]),
            enabled=True,
        )
        db.session.add(cfg)
        db.session.commit()

        cred = XtreamCredential(
            username="multi",
            password="multi",
            playlist_config_id=cfg.id,
            enabled=True,
            use_filters=False,
        )
        db.session.add(cred)
        db.session.commit()

        playlist_channels = ChannelQueryService.channels_for_playlist_config(
            cfg, apply_filters=False, apply_ppv_visibility=False
        )
        xtream_channels = ChannelQueryService.channels_for_xtream(cred, None, cfg)
        assert {c.stream_id for c in playlist_channels} == {c.stream_id for c in xtream_channels}
        assert len(playlist_channels) == 2


def test_multi_account_xtream_stream_routes_to_channel_account(app, client):
    """Live stream redirect uses channel.account_id, not playlist config id."""
    with app.app_context():
        acc1 = Account(name="S1", server="s1", username="u", password="p", enabled=True)
        acc2 = Account(name="S2", server="s2", username="u", password="p", enabled=True)
        db.session.add_all([acc1, acc2])
        db.session.commit()
        db.session.add(
            Channel(account_id=acc2.id, stream_id="555", name="Acc2 Ch", is_active=True)
        )
        db.session.commit()

        cfg = PlaylistConfig(
            name="Multi",
            include_accounts=json.dumps([acc1.id, acc2.id]),
            enabled=True,
        )
        db.session.add(cfg)
        db.session.commit()
        cred = XtreamCredential(
            username="route",
            password="route",
            playlist_config_id=cfg.id,
            enabled=True,
        )
        db.session.add(cred)
        db.session.commit()

        response = client.get("/live/route/route/555.ts")
        assert response.status_code == 302
        assert f"/stream/{acc2.id}/555.ts" in response.headers["Location"]
