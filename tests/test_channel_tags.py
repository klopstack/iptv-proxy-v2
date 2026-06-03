"""Tests for centralized channel tag batch loading."""

from unittest.mock import patch

from models import Account, Channel, ChannelTag, Tag, db
from services.channel_tags import (
    load_tag_names_by_channel_id,
    load_tag_names_by_stream_keys,
    load_tag_names_for_account,
)
from services.sync_service import ChannelSyncService


def test_load_tag_names_by_stream_keys(app):
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        east_tag = Tag(name="EAST")
        west_tag = Tag(name="WEST")
        db.session.add_all([east_tag, west_tag])
        db.session.commit()

        ch1 = Channel(account_id=account.id, stream_id="1", name="CNN East", cleaned_name="CNN", is_active=True)
        ch2 = Channel(account_id=account.id, stream_id="2", name="CNN West", cleaned_name="CNN", is_active=True)
        db.session.add_all([ch1, ch2])
        db.session.commit()
        db.session.add_all(
            [
                ChannelTag(account_id=account.id, stream_id="1", tag_id=east_tag.id),
                ChannelTag(account_id=account.id, stream_id="2", tag_id=west_tag.id),
            ]
        )
        db.session.commit()

        channels = Channel.query.filter_by(account_id=account.id).order_by(Channel.stream_id).all()
        tags = load_tag_names_by_stream_keys(channels)
        assert tags[(account.id, "1")] == {"EAST"}
        assert tags[(account.id, "2")] == {"WEST"}


def test_load_tag_names_for_account(app):
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        tag = Tag(name="HD")
        db.session.add(tag)
        db.session.commit()

        ch = Channel(account_id=account.id, stream_id="1", name="HD Ch", is_active=True)
        db.session.add(ch)
        db.session.commit()
        db.session.add(ChannelTag(account_id=account.id, stream_id="1", tag_id=tag.id))
        db.session.commit()

        tags = load_tag_names_for_account(account.id, [ch])
        assert tags == {"1": ["HD"]}


def test_load_tag_names_by_channel_id_uppercase(app):
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        tag = Tag(name="east")
        db.session.add(tag)
        db.session.commit()

        ch = Channel(account_id=account.id, stream_id="1", name="Ch", cleaned_name="CNN", is_active=True)
        db.session.add(ch)
        db.session.commit()
        db.session.add(ChannelTag(account_id=account.id, stream_id="1", tag_id=tag.id))
        db.session.commit()

        tags = load_tag_names_by_channel_id([ch], uppercase=True)
        assert tags[ch.id] == {"EAST"}


def test_detect_channel_links_uses_batch_tag_query(app):
    """Tag loading should be O(1) queries per batch, not per channel."""
    with app.app_context():
        account = Account(name="Tags", server="s", username="u", password="p", enabled=True)
        db.session.add(account)
        db.session.commit()

        ch = Channel(account_id=account.id, stream_id="1", name="Ch", cleaned_name="CNN", is_active=True)
        db.session.add(ch)
        db.session.commit()

        with patch("services.channel_tags.db.session.query") as mock_query:
            mock_query.return_value.join.return_value.filter.return_value.all.return_value = []
            ChannelSyncService.detect_channel_links(account.id)
            assert mock_query.call_count == 1
