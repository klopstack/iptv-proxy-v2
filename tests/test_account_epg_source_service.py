"""Tests for account-linked XMLTV EPG source helpers."""

import pytest

from models import Account, db
from services.account_epg_source_service import (
    ACCOUNT_XMLTV_NAME_SUFFIX,
    build_account_xmltv_url,
    find_account_xmltv_epg_source,
    normalize_account_server,
    upsert_account_xmltv_epg_source,
)


class TestAccountXmltvUrl:
    def test_normalize_account_server(self):
        assert normalize_account_server("https://example.com/") == "example.com"
        assert normalize_account_server("http://foo.bar") == "foo.bar"

    def test_build_account_xmltv_url(self):
        url = build_account_xmltv_url("example.com", "user@1", "p&ss")
        assert url.startswith("https://example.com/xmltv.php?")
        assert "username=user%401" in url
        assert "password=p%26ss" in url


class TestUpsertAccountXmltvEpgSource:
    def test_creates_xmltv_url_source(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            cred = account.get_primary_credential()
            source, created = upsert_account_xmltv_epg_source(account, cred)
            db.session.commit()

            assert created is True
            assert source.source_type == "xmltv_url"
            assert source.account_id == account.id
            assert ACCOUNT_XMLTV_NAME_SUFFIX in source.name
            assert "xmltv.php" in source.url
            assert cred.username in source.url or "username=" in source.url

    def test_updates_existing_source(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            cred = account.get_primary_credential()
            upsert_account_xmltv_epg_source(account, cred)
            db.session.commit()

            account.server = "newserver.example"
            cred.password = "newpass"
            source, created = upsert_account_xmltv_epg_source(account, cred)
            db.session.commit()

            assert created is False
            assert source.url == build_account_xmltv_url("newserver.example", cred.username, "newpass")
            assert find_account_xmltv_epg_source(account.id).id == source.id

    def test_raises_without_credentials(self, app):
        with app.app_context():
            account = Account(name="Empty", server="example.com", enabled=True)
            db.session.add(account)
            db.session.commit()

            with pytest.raises(ValueError, match="no credentials"):
                upsert_account_xmltv_epg_source(account)
