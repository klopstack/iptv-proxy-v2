"""Tests for Wave 1 route cleanup (TODO 74, 75)."""

from unittest.mock import MagicMock, patch


class TestBlueprintRegistration:
    """Every registered blueprint must expose at least one route."""

    def test_all_blueprints_have_routes(self, app):
        empty = []
        for name in app.blueprints:
            has_route = any(rule.endpoint.startswith(f"{name}.") for rule in app.url_map.iter_rules())
            if not has_route:
                empty.append(name)
        assert empty == [], f"Blueprints with zero routes: {empty}"


class TestAccountCategoriesSemantics:
    """GET categories is idempotent; sync is explicit POST."""

    def test_get_categories_account_not_found(self, app, client):
        response = client.get("/api/accounts/999/categories")
        assert response.status_code == 404

    @patch("services.account_admin_service.get_iptv_service_for_account")
    @patch("services.account_admin_service.cache_service")
    def test_get_categories_from_cache_no_upstream(self, mock_cache, mock_get_service, app, client, test_account):
        mock_cache.get_cached_categories.return_value = [{"category_id": "1", "category_name": "Cached Category"}]

        response = client.get(f"/api/accounts/{test_account}/categories")

        assert response.status_code == 200
        assert response.json == [{"category_id": "1", "category_name": "Cached Category"}]
        mock_get_service.assert_not_called()

    @patch("services.account_admin_service.get_iptv_service_for_account")
    @patch("services.account_admin_service.cache_service")
    def test_get_categories_empty_without_upstream(self, mock_cache, mock_get_service, app, client, test_account):
        mock_cache.get_cached_categories.return_value = None

        response = client.get(f"/api/accounts/{test_account}/categories")

        assert response.status_code == 200
        assert response.json == []
        mock_get_service.assert_not_called()

    @patch("services.account_admin_service.get_iptv_service_for_account")
    @patch("services.account_admin_service.cache_service")
    def test_get_categories_from_database(self, mock_cache, mock_get_service, app, client, test_account):
        from models import Category, db

        mock_cache.get_cached_categories.return_value = None
        with app.app_context():
            db.session.add(
                Category(
                    account_id=test_account,
                    category_id="db-1",
                    category_name="DB Sports",
                    cleaned_name="Sports",
                )
            )
            db.session.commit()

        response = client.get(f"/api/accounts/{test_account}/categories")

        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["category_id"] == "db-1"
        assert response.json[0]["category_name"] == "DB Sports"
        mock_get_service.assert_not_called()

    @patch("services.account_admin_service.AccountAdminService._process_extraction_tags")
    @patch("services.account_admin_service.get_iptv_service_for_account")
    @patch("services.account_admin_service.cache_service")
    def test_sync_categories_calls_upstream(
        self, mock_cache, mock_get_service, mock_process_tags, app, client, test_account
    ):
        mock_service = MagicMock()
        mock_service.get_live_categories.return_value = [{"category_id": "1", "category_name": "Live Category"}]
        mock_get_service.return_value = mock_service
        mock_cache.get_cached_streams.return_value = [{"stream_id": "1", "name": "Ch1", "category_id": "1"}]

        response = client.post(f"/api/accounts/{test_account}/categories/sync")

        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert data["count"] == 1
        mock_service.get_live_categories.assert_called_once()
        mock_cache.cache_categories.assert_called_once()
        mock_process_tags.assert_called_once()


class TestFccSyncCanonicalPath:
    """FCC sync uses a single canonical stations endpoint."""

    @patch("services.fcc_facility_service.FccFacilityService.full_sync")
    def test_sync_fcc_facilities_success(self, mock_full_sync, app, client):
        mock_full_sync.return_value = {
            "success": True,
            "message": "Synced",
            "stats": {"added": 10, "updated": 5, "unchanged": 100, "total": 115},
        }

        response = client.post("/api/fcc/facilities/sync")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_legacy_fcc_sync_route_removed(self, app, client):
        response = client.post("/api/sync/fcc")
        assert response.status_code == 404


class TestAppScopedCacheService:
    """Cache service is shared via app.extensions."""

    def test_single_cache_instance(self, app):
        from services.cache_service import get_cache_service

        with app.app_context():
            a = get_cache_service()
            b = get_cache_service()
            assert a is b

    def test_cache_clear_visible_across_imports(self, app):
        from routes.api import cache_service as api_cache
        from routes.filters import cache_service as filters_cache

        with app.app_context():
            api_cache.cache_categories(99, [{"category_id": "x"}])
            assert filters_cache.get_cached_categories(99) is not None
            api_cache.clear_account_cache(99)
            assert filters_cache.get_cached_categories(99) is None


def test_account_epg_channels_blueprint_not_registered(app):
    assert "account_epg_channels" not in app.blueprints
