"""Contract tests for unified channel selection."""

import json

from models import Account, Category, Channel, PlaylistConfig, Tag, ChannelTag, db
from services.channel_query_service import ChannelQueryService


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
