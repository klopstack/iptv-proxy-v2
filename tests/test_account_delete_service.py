"""Tests for AccountDeleteService — account deletion with no orphan rows."""

import pytest

from models import (
    Account,
    Category,
    Channel,
    ChannelEpgMapping,
    ChannelTag,
    Credential,
    EpgChannel,
    EpgSource,
    Filter,
    Tag,
    db,
)
from services.account_delete_service import AccountDeleteService


@pytest.fixture
def account_with_data(app):
    """Account with channels, tags, filters, credentials, and EPG source."""
    with app.app_context():
        account = Account(
            name="Delete Me",
            server="example.com",
            username="user",
            password="pass",
            enabled=True,
        )
        db.session.add(account)
        db.session.flush()

        cred = Credential(account_id=account.id, username="u", password="p")
        filt = Filter(
            account_id=account.id,
            name="Test Filter",
            filter_type="category",
            filter_action="whitelist",
            filter_value="US",
            enabled=True,
        )
        category = Category(
            account_id=account.id,
            category_id="1",
            category_name="US| Sports",
        )
        db.session.add_all([cred, filt, category])
        db.session.flush()

        channel = Channel(
            account_id=account.id,
            stream_id="100",
            name="ESPN",
            category_id=category.id,
            is_active=True,
        )
        db.session.add(channel)
        db.session.flush()

        tag = Tag(name="SPORTS")
        db.session.add(tag)
        db.session.flush()
        db.session.add(ChannelTag(account_id=account.id, stream_id="100", tag_id=tag.id))

        epg_source = EpgSource(
            name="Provider EPG",
            source_type="xmltv_url",
            url="http://example.com/epg.xml",
            account_id=account.id,
            enabled=True,
        )
        db.session.add(epg_source)
        db.session.flush()

        epg_channel = EpgChannel(
            source_id=epg_source.id,
            channel_id="espn.us",
            display_name="ESPN",
        )
        db.session.add(epg_channel)
        db.session.flush()

        db.session.add(
            ChannelEpgMapping(
                channel_id=channel.id,
                epg_channel_id=epg_channel.id,
                mapping_type="manual",
            )
        )
        db.session.commit()

        yield account.id


class TestAccountDeleteService:
    def test_delete_removes_all_account_scoped_rows(self, app, account_with_data):
        with app.app_context():
            account_id = account_with_data
            result = AccountDeleteService.delete_account(account_id)
            assert result["success"] is True
            assert db.session.get(Account, account_id) is None
            assert Channel.query.filter_by(account_id=account_id).count() == 0
            assert Category.query.filter_by(account_id=account_id).count() == 0
            assert ChannelTag.query.filter_by(account_id=account_id).count() == 0
            assert Filter.query.filter_by(account_id=account_id).count() == 0
            assert Credential.query.filter_by(account_id=account_id).count() == 0
            assert EpgSource.query.filter_by(account_id=account_id).count() == 0
            assert ChannelEpgMapping.query.count() == 0
            assert EpgChannel.query.count() == 0
            # Global tag preserved
            assert Tag.query.filter_by(name="SPORTS").count() == 1

    def test_delete_nonexistent_account(self, app):
        with app.app_context():
            result = AccountDeleteService.delete_account(99999)
            assert result["success"] is False


class TestDeleteAccountRoute:
    def test_delete_account_api(self, app, client, account_with_data):
        response = client.delete(f"/api/accounts/{account_with_data}")
        assert response.status_code == 204

        with app.app_context():
            assert db.session.get(Account, account_with_data) is None
            assert Channel.query.filter_by(account_id=account_with_data).count() == 0
