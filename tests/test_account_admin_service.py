"""Unit tests for AccountAdminService (no Flask request context)."""

from unittest.mock import patch

from models import Account, Category, Channel, Credential, Tag, db
from services.account_admin_service import AccountAdminService
from services.serializers.credentials import serialize_credential


class TestSerializeCredential:
    def test_serialize_credential_defaults(self):
        cred = Credential(
            id=1,
            username="user",
            max_connections=None,
            active_connections=None,
            status="Active",
            exp_date="2025-01-01",
            enabled=True,
        )
        data = serialize_credential(cred)
        assert data["max_connections"] == 1
        assert data["active_connections"] == 0
        assert data["username"] == "user"


class TestAddCredential:
    def test_add_credential_missing_fields(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            result, error = AccountAdminService.add_credential(account, {"username": "u"})
            assert result is None
            assert "password" in error.lower()

    def test_add_credential_duplicate(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            result, error = AccountAdminService.add_credential(account, {"username": "test_user", "password": "pass"})
            assert result is None
            assert "already exists" in error


class TestGetCategoriesPayload:
    @patch("services.account_admin_service.cache_service")
    def test_returns_cache_when_present(self, mock_cache, app, test_account):
        mock_cache.get_cached_categories.return_value = [{"category_id": "1", "category_name": "Sports"}]
        with app.app_context():
            payload = AccountAdminService.get_categories_payload(test_account)
            assert payload == [{"category_id": "1", "category_name": "Sports"}]

    @patch("services.account_admin_service.cache_service")
    def test_returns_db_rows_when_cache_empty(self, mock_cache, app, test_account):
        mock_cache.get_cached_categories.return_value = None
        with app.app_context():
            db.session.add(Category(account_id=test_account, category_id="10", category_name="News", is_active=True))
            db.session.commit()
            payload = AccountAdminService.get_categories_payload(test_account)
            assert len(payload) == 1
            assert payload[0]["category_name"] == "News"


class TestGetAccountStats:
    def test_stats_from_database(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            category = Category(account_id=test_account, category_id="1", category_name="Test")
            db.session.add(category)
            db.session.flush()
            db.session.add(
                Channel(
                    account_id=test_account,
                    stream_id="s1",
                    name="Ch1",
                    category_id=category.id,
                    is_active=True,
                )
            )
            db.session.commit()

            stats, error = AccountAdminService.get_account_stats(account)
            assert error is None
            assert stats["total_channels"] == 1
            assert stats["using_database"] is True
            assert stats["synced"] is True


class TestPreviewFilterMatches:
    def test_disabled_account(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            account.enabled = False
            db.session.commit()

            payload, error, status = AccountAdminService.preview_filter_matches(account, "category", "News")
            assert payload is None
            assert status == 403

    def test_category_filter(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            category = Category(account_id=test_account, category_id="1", category_name="Sports News")
            db.session.add(category)
            db.session.flush()
            db.session.add(
                Channel(
                    account_id=test_account,
                    stream_id="s1",
                    name="ESPN",
                    category_id=category.id,
                    is_active=True,
                )
            )
            db.session.commit()

            payload, error, status = AccountAdminService.preview_filter_matches(account, "category", "Sports")
            assert error is None
            assert status == 200
            assert payload["match_count"] == 1
            assert payload["total_count"] == 1

    def test_invalid_regex(self, app, test_account):
        with app.app_context():
            account = db.session.get(Account, test_account)
            category = Category(account_id=test_account, category_id="1", category_name="Test")
            db.session.add(category)
            db.session.flush()
            db.session.add(
                Channel(
                    account_id=test_account,
                    stream_id="s1",
                    name="Ch1",
                    category_id=category.id,
                    is_active=True,
                )
            )
            db.session.commit()

            payload, error, status = AccountAdminService.preview_filter_matches(account, "regex", "[invalid")
            assert payload is None
            assert status == 400
            assert "Invalid regex" in error


class TestCleanupOrphanTags:
    def test_deletes_unlinked_tags(self, app):
        with app.app_context():
            orphan = Tag(name="orphan-tag")
            db.session.add(orphan)
            db.session.commit()

            result = AccountAdminService.cleanup_orphan_tags()
            assert result["tags_deleted"] == 1
            assert db.session.get(Tag, orphan.id) is None
