"""
Additional tests to boost route coverage to 80%+
Tests cover: channel_health, channel_links, rulesets, playlists, filters routes
"""
import json

import pytest

from models import Account, Category, Channel, ChannelHealthConfig, Credential, Filter, db


@pytest.fixture
def app():
    """Create test Flask app with in-memory database."""
    from app import app as flask_app

    flask_app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///:memory:"
    flask_app.config["TESTING"] = True
    flask_app.config["WTF_CSRF_ENABLED"] = False

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def test_account(app):
    """Create a test account with credentials."""
    with app.app_context():
        account = Account(
            name="Test Account",
            server="test.server.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()

        credential = Credential(
            account_id=account.id,
            username="testuser",
            password="testpass",
            max_connections=3,
        )
        db.session.add(credential)
        db.session.commit()

        return account.id


@pytest.fixture
def test_category(app, test_account):
    """Create a test category."""
    with app.app_context():
        category = Category(
            account_id=test_account,
            category_id="1",
            category_name="Test Category",
        )
        db.session.add(category)
        db.session.commit()
        return category.id


@pytest.fixture
def test_channel(app, test_account, test_category):
    """Create a test channel."""
    with app.app_context():
        channel = Channel(
            account_id=test_account,
            stream_id="12345",
            name="Test Channel",
            cleaned_name="Test Channel",
            category_id=test_category,
            is_active=True,
            is_visible=True,
        )
        db.session.add(channel)
        db.session.commit()
        return channel.id


# ============================================================================
# Channel Health Routes - Additional Tests
# ============================================================================


class TestChannelHealthRoutesExtended:
    """Extended tests for channel health routes."""

    def test_get_channels_paginated(self, client, app, test_channel):
        """Test getting paginated channels."""
        response = client.get("/api/channel-health/channels")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "channels" in data

    def test_get_channels_paginated_with_filters(self, client, app, test_account, test_channel):
        """Test getting paginated channels with various filters."""
        response = client.get(
            f"/api/channel-health/channels?account_id={test_account}&status=unknown"
            "&visibility=visible&page=1&per_page=50"
        )
        assert response.status_code == 200

    def test_get_channels_invalid_status(self, client, app):
        """Test getting channels with invalid status filter."""
        response = client.get("/api/channel-health/channels?status=invalid_status")
        assert response.status_code == 400

    def test_get_channels_invalid_visibility(self, client, app):
        """Test getting channels with invalid visibility filter."""
        response = client.get("/api/channel-health/channels?visibility=invalid")
        assert response.status_code == 400

    def test_get_channels_invalid_epg_filter(self, client, app):
        """Test getting channels with invalid EPG filter."""
        response = client.get("/api/channel-health/channels?epg=invalid")
        assert response.status_code == 400

    def test_get_categories(self, client, app, test_account, test_category):
        """Test getting categories list."""
        response = client.get("/api/channel-health/categories")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["success"] is True
        assert "categories" in data

    def test_get_categories_with_account_filter(self, client, app, test_account, test_category):
        """Test getting categories filtered by account."""
        response = client.get(f"/api/channel-health/categories?account_id={test_account}")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data["categories"]) > 0

    def test_trigger_scan(self, client, app, test_account, test_channel):
        """Test triggering a channel scan."""
        with app.app_context():
            ChannelHealthConfig.set("scanning_enabled", "false")

        response = client.post(
            f"/api/channel-health/scan/{test_account}",
            data=json.dumps({"max_channels": 5}),
            content_type="application/json",
        )
        # Should succeed even if scanning was disabled (temporarily enabled)
        assert response.status_code == 200

    def test_update_config_missing_key_value(self, client, app):
        """Test updating config without proper key/value."""
        response = client.put(
            "/api/channel-health/config",
            data=json.dumps({"invalid": "data"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_update_config_by_key(self, client, app):
        """Test updating a specific config key."""
        response = client.put(
            "/api/channel-health/config/failure_threshold",
            data=json.dumps({"value": "7"}),
            content_type="application/json",
        )
        assert response.status_code == 200

    def test_update_config_by_key_no_value(self, client, app):
        """Test updating config key without value."""
        response = client.put(
            "/api/channel-health/config/failure_threshold",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_bulk_reenable_channels(self, client, app, test_channel):
        """Test bulk re-enabling channels."""
        response = client.post(
            "/api/channel-health/bulk/reenable",
            data=json.dumps({"channel_ids": [test_channel]}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["processed"] == 1

    def test_bulk_ignore_channels(self, client, app, test_channel):
        """Test bulk ignoring channels."""
        response = client.post(
            "/api/channel-health/bulk/ignore",
            data=json.dumps({"channel_ids": [test_channel], "reason": "Test bulk ignore"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["processed"] == 1

    def test_bulk_ignore_invalid_type(self, client, app):
        """Test bulk ignore with invalid type."""
        response = client.post(
            "/api/channel-health/bulk/ignore",
            data=json.dumps({"channel_ids": "not_a_list"}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_get_channel_history_with_limit(self, client, app, test_channel):
        """Test getting channel history with limit."""
        response = client.get(f"/api/channel-health/history/{test_channel}?limit=10")
        assert response.status_code == 200

    def test_test_channel(self, client, app, test_account, test_channel):
        """Test testing a specific channel."""
        response = client.post(f"/api/channel-health/test/{test_channel}")
        # May fail due to no credentials, but should not crash
        assert response.status_code in [200, 400]


# ============================================================================
# Filter Routes Tests
# ============================================================================


class TestFilterRoutes:
    """Test filter CRUD routes."""

    def test_get_filters_empty(self, client, app):
        """Test getting filters when none exist."""
        response = client.get("/api/filters")
        assert response.status_code == 200
        assert response.json == []

    def test_create_filter(self, client, app, test_account):
        """Test creating a filter."""
        response = client.post(
            "/api/filters",
            json={
                "account_id": test_account,
                "name": "Test Filter",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "US|",
                "enabled": True,
            },
        )
        assert response.status_code == 201
        data = response.json
        assert data["name"] == "Test Filter"
        assert data["filter_type"] == "category"

    def test_create_filter_invalid_account(self, client, app):
        """Test creating filter for non-existent account."""
        response = client.post(
            "/api/filters",
            json={
                "account_id": 99999,
                "name": "Test Filter",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "US|",
            },
        )
        assert response.status_code == 404

    def test_update_filter(self, client, app, test_account):
        """Test updating a filter."""
        # Create filter first
        create_response = client.post(
            "/api/filters",
            json={
                "account_id": test_account,
                "name": "Original Filter",
                "filter_type": "category",
                "filter_action": "whitelist",
                "filter_value": "US|",
            },
        )
        filter_id = create_response.json["id"]

        # Update it
        response = client.put(
            f"/api/filters/{filter_id}",
            json={
                "name": "Updated Filter",
                "filter_value": "UK|",
                "enabled": False,
            },
        )
        assert response.status_code == 200
        assert response.json["name"] == "Updated Filter"
        assert response.json["filter_value"] == "UK|"

    def test_delete_filter(self, client, app, test_account):
        """Test deleting a filter."""
        # Create filter first
        create_response = client.post(
            "/api/filters",
            json={
                "account_id": test_account,
                "name": "To Delete",
                "filter_type": "category",
                "filter_action": "blacklist",
                "filter_value": "XXX",
            },
        )
        filter_id = create_response.json["id"]

        # Delete it
        response = client.delete(f"/api/filters/{filter_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = client.get("/api/filters")
        assert len(response.json) == 0

    def test_delete_nonexistent_filter(self, client, app):
        """Test deleting a filter that doesn't exist."""
        response = client.delete("/api/filters/99999")
        assert response.status_code == 404


# ============================================================================
# Ruleset Routes - Extended Tests
# ============================================================================


class TestRulesetRoutesExtended:
    """Extended tests for ruleset routes."""

    def test_get_ruleset_not_found(self, client, app):
        """Test getting a non-existent ruleset."""
        response = client.get("/api/rulesets/99999")
        assert response.status_code == 404

    def test_update_ruleset_not_found(self, client, app):
        """Test updating a non-existent ruleset."""
        response = client.put(
            "/api/rulesets/99999",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 404

    def test_delete_ruleset_not_found(self, client, app):
        """Test deleting a non-existent ruleset."""
        response = client.delete("/api/rulesets/99999")
        assert response.status_code == 404

    def test_get_ruleset_rules(self, client, app):
        """Test getting rules for a ruleset."""
        # Create a ruleset
        create_response = client.post(
            "/api/rulesets",
            json={"name": "Test Ruleset", "description": "For testing", "enabled": True},
        )
        ruleset_id = create_response.json["id"]

        # Get rules
        response = client.get(f"/api/rulesets/{ruleset_id}/rules")
        assert response.status_code == 200
        assert isinstance(response.json, list)

    def test_get_ruleset_rules_not_found(self, client, app):
        """Test getting rules for non-existent ruleset."""
        response = client.get("/api/rulesets/99999/rules")
        assert response.status_code == 404

    def test_get_tag_rules(self, client, app):
        """Test getting all tag rules."""
        response = client.get("/api/tag-rules")
        assert response.status_code == 200
        assert isinstance(response.json, list)

    def test_get_tag_rules_filtered_by_ruleset(self, client, app):
        """Test getting tag rules filtered by ruleset."""
        # Create a ruleset first
        create_response = client.post(
            "/api/rulesets",
            json={"name": "Test Ruleset", "enabled": True},
        )
        ruleset_id = create_response.json["id"]

        response = client.get(f"/api/tag-rules?ruleset_id={ruleset_id}")
        assert response.status_code == 200

    def test_create_tag_rule(self, client, app):
        """Test creating a tag rule."""
        # Create ruleset first
        ruleset_response = client.post(
            "/api/rulesets",
            json={"name": "Rule Container", "enabled": True},
        )
        ruleset_id = ruleset_response.json["id"]

        response = client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": ruleset_id,
                "name": "US Prefix",
                "pattern": "US|",
                "pattern_type": "prefix",
                "tag_name": "US",
                "source": "both",
                "remove_from_name": True,
                "priority": 10,
                "enabled": True,
            },
        )
        assert response.status_code == 201
        assert response.json["name"] == "US Prefix"

    def test_update_tag_rule(self, client, app):
        """Test updating a tag rule."""
        # Create ruleset and rule
        ruleset_response = client.post(
            "/api/rulesets",
            json={"name": "Rule Container", "enabled": True},
        )
        ruleset_id = ruleset_response.json["id"]

        rule_response = client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": ruleset_id,
                "name": "Original Rule",
                "pattern": "US|",
                "pattern_type": "prefix",
                "tag_name": "US",
                "source": "both",
            },
        )
        assert rule_response.status_code == 201, f"Failed to create rule: {rule_response.json}"
        rule_id = rule_response.json["id"]

        # Update it
        response = client.put(
            f"/api/tag-rules/{rule_id}",
            json={
                "name": "Updated Rule",
                "pattern": "UK|",
                "tag_name": "UK",
            },
        )
        assert response.status_code == 200
        assert response.json["name"] == "Updated Rule"

    def test_delete_tag_rule(self, client, app):
        """Test deleting a tag rule."""
        # Create ruleset and rule
        ruleset_response = client.post(
            "/api/rulesets",
            json={"name": "Rule Container", "enabled": True},
        )
        ruleset_id = ruleset_response.json["id"]

        rule_response = client.post(
            "/api/tag-rules",
            json={
                "ruleset_id": ruleset_id,
                "name": "To Delete",
                "pattern": "US|",
                "pattern_type": "prefix",
                "tag_name": "US",
                "source": "both",
            },
        )
        assert rule_response.status_code == 201, f"Failed to create rule: {rule_response.json}"
        rule_id = rule_response.json["id"]

        # Delete it
        response = client.delete(f"/api/tag-rules/{rule_id}")
        assert response.status_code == 204


# ============================================================================
# Filter Service Tests
# ============================================================================


class TestFilterService:
    """Test FilterService functionality."""

    def test_compute_visibility_no_filters(self, app, test_account, test_channel):
        """Test that channels are visible when no filters exist."""
        from services.filter_service import FilterService

        with app.app_context():
            result = FilterService.compute_visibility_for_account(test_account)
            assert result["success"] is True
            assert result["channels_visible"] > 0

    def test_compute_visibility_account_not_found(self, app):
        """Test handling of non-existent account."""
        from services.filter_service import FilterService

        with app.app_context():
            result = FilterService.compute_visibility_for_account(99999)
            assert result["success"] is False
            assert "not found" in result["error"]

    def test_compute_visibility_with_whitelist(self, app, test_account, test_channel, test_category):
        """Test channel visibility with whitelist filter."""
        from services.filter_service import FilterService

        with app.app_context():
            # Create a whitelist filter for category
            filter_obj = Filter(
                account_id=test_account,
                name="Test Whitelist",
                filter_type="category",
                filter_action="whitelist",
                filter_value="Test Category",
                enabled=True,
            )
            db.session.add(filter_obj)
            db.session.commit()

            result = FilterService.compute_visibility_for_account(test_account)
            assert result["success"] is True

    def test_compute_visibility_with_blacklist(self, app, test_account, test_channel, test_category):
        """Test channel visibility with blacklist filter."""
        from services.filter_service import FilterService

        with app.app_context():
            # Create a blacklist filter that matches our test channel
            filter_obj = Filter(
                account_id=test_account,
                name="Test Blacklist",
                filter_type="channel_name",
                filter_action="blacklist",
                filter_value="Test Channel",
                enabled=True,
            )
            db.session.add(filter_obj)
            db.session.commit()

            result = FilterService.compute_visibility_for_account(test_account)
            assert result["success"] is True
            # Channel should be hidden by blacklist
            assert result["channels_hidden"] > 0

    def test_compute_visibility_with_regex_filter(self, app, test_account, test_channel, test_category):
        """Test channel visibility with regex filter."""
        from services.filter_service import FilterService

        with app.app_context():
            filter_obj = Filter(
                account_id=test_account,
                name="Regex Filter",
                filter_type="regex",
                filter_action="whitelist",
                filter_value="Test.*",
                enabled=True,
            )
            db.session.add(filter_obj)
            db.session.commit()

            result = FilterService.compute_visibility_for_account(test_account)
            assert result["success"] is True

    def test_compute_visibility_invalid_regex(self, app, test_account, test_channel, test_category):
        """Test handling of invalid regex pattern."""
        from services.filter_service import FilterService

        with app.app_context():
            filter_obj = Filter(
                account_id=test_account,
                name="Invalid Regex",
                filter_type="regex",
                filter_action="blacklist",
                filter_value="[invalid",  # Invalid regex
                enabled=True,
            )
            db.session.add(filter_obj)
            db.session.commit()

            # Should not crash, just log warning
            result = FilterService.compute_visibility_for_account(test_account)
            assert result["success"] is True

    def test_invalidate_account(self, app, test_account):
        """Test invalidate_account calls compute_visibility."""
        from services.filter_service import FilterService

        with app.app_context():
            # Should not crash even with no channels
            FilterService.invalidate_account(test_account)


# ============================================================================
# Web Routes Tests
# ============================================================================


class TestWebRoutes:
    """Test web UI routes."""

    def test_index_page(self, client, app):
        """Test index page loads."""
        response = client.get("/")
        assert response.status_code == 200

    def test_accounts_page(self, client, app):
        """Test accounts page loads."""
        response = client.get("/accounts")
        assert response.status_code == 200

    def test_filters_page(self, client, app):
        """Test filters page loads."""
        response = client.get("/filters")
        assert response.status_code == 200

    def test_rulesets_page(self, client, app):
        """Test rulesets page loads."""
        response = client.get("/rulesets")
        assert response.status_code == 200

    def test_settings_page(self, client, app):
        """Test settings page loads."""
        response = client.get("/settings")
        assert response.status_code == 200

    def test_channel_health_page(self, client, app):
        """Test channel health page loads."""
        response = client.get("/channel-health")
        assert response.status_code == 200

    def test_categories_page(self, client, app):
        """Test categories page loads."""
        response = client.get("/categories")
        assert response.status_code == 200

    def test_test_page(self, client, app):
        """Test test page loads."""
        response = client.get("/test")
        assert response.status_code == 200


# ============================================================================
# Playlist Config Tests
# ============================================================================


class TestPlaylistConfigRoutes:
    """Test playlist configuration routes."""

    def test_get_playlist_configs_empty(self, client, app):
        """Test getting playlist configs when none exist."""
        response = client.get("/api/playlist-configs")
        assert response.status_code == 200
        assert response.json == []

    def test_create_playlist_config(self, client, app, test_account):
        """Test creating a playlist config."""
        response = client.post(
            "/api/playlist-configs",
            json={
                "name": "Test Playlist",
                "description": "Test description",
                "include_accounts": [test_account],
                "exclude_accounts": [],
                "include_tags": ["US"],
                "exclude_tags": ["XXX"],
                "tag_match_mode": "any",
            },
        )
        assert response.status_code == 201
        data = response.json
        assert data["name"] == "Test Playlist"

    def test_get_playlist_configs(self, client, app, test_account):
        """Test getting list of playlist configs."""
        # Create one first
        client.post(
            "/api/playlist-configs",
            json={
                "name": "Test Config",
                "include_accounts": [test_account],
            },
        )

        response = client.get("/api/playlist-configs")
        assert response.status_code == 200
        assert len(response.json) > 0

    def test_update_playlist_config(self, client, app, test_account):
        """Test updating a playlist config."""
        # Create one first
        create_response = client.post(
            "/api/playlist-configs",
            json={
                "name": "Original Name",
                "include_accounts": [test_account],
            },
        )
        config_id = create_response.json["id"]

        response = client.put(
            f"/api/playlist-configs/{config_id}",
            json={
                "name": "Updated Name",
                "enabled": False,
            },
        )
        assert response.status_code == 200
        assert response.json["name"] == "Updated Name"

    def test_delete_playlist_config(self, client, app, test_account):
        """Test deleting a playlist config."""
        # Create one first
        create_response = client.post(
            "/api/playlist-configs",
            json={
                "name": "To Delete",
                "include_accounts": [test_account],
            },
        )
        config_id = create_response.json["id"]

        response = client.delete(f"/api/playlist-configs/{config_id}")
        assert response.status_code == 204


# ============================================================================
# Cache Service Tests
# ============================================================================


class TestCacheService:
    """Test CacheService functionality."""

    def test_cache_streams(self, app, test_account):
        """Test caching and retrieving streams."""
        from services.cache_service import CacheService

        cache = CacheService()

        with app.app_context():
            test_streams = [{"id": 1, "name": "Stream 1"}]
            cache.cache_streams(test_account, test_streams)
            result = cache.get_cached_streams(test_account)
            assert result == test_streams

    def test_cache_categories(self, app, test_account):
        """Test caching and retrieving categories."""
        from services.cache_service import CacheService

        cache = CacheService()

        with app.app_context():
            test_categories = [{"id": 1, "name": "Category 1"}]
            cache.cache_categories(test_account, test_categories)
            result = cache.get_cached_categories(test_account)
            assert result == test_categories

    def test_cache_miss(self, app, test_account):
        """Test cache miss returns None."""
        from services.cache_service import CacheService

        cache = CacheService()

        with app.app_context():
            result = cache.get_cached_streams(test_account)
            assert result is None

    def test_clear_account_cache(self, app, test_account):
        """Test clearing cache for specific account."""
        from services.cache_service import CacheService

        cache = CacheService()

        with app.app_context():
            cache.cache_streams(test_account, [{"test": "data"}])
            cache.clear_account_cache(test_account)
            # Cache should be cleared
            result = cache.get_cached_streams(test_account)
            assert result is None

    def test_clear_all_cache(self, app, test_account):
        """Test clearing all cache."""
        from services.cache_service import CacheService

        cache = CacheService()

        with app.app_context():
            cache.cache_streams(test_account, [{"test": "data"}])
            cache.cache_categories(test_account, [{"cat": "data"}])
            cache.clear_all()
            # All should be cleared
            assert cache.get_cached_streams(test_account) is None
            assert cache.get_cached_categories(test_account) is None


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling decorator."""

    def test_handle_errors_decorator(self, client, app):
        """Test that errors are handled gracefully."""
        # The channel health routes use @handle_errors
        response = client.get("/api/channel-health/report")
        # Should not return 500 even if something goes wrong
        assert response.status_code in [200, 400, 404]

    def test_invalid_json_request(self, client, app):
        """Test handling of invalid JSON in request."""
        response = client.post(
            "/api/rulesets",
            data="not valid json",
            content_type="application/json",
        )
        # Should return 400, not 500
        assert response.status_code == 400


# ============================================================================
# API Routes Tests
# ============================================================================


class TestAPIRoutes:
    """Test general API routes."""

    def test_get_accounts_list(self, client, app, test_account):
        """Test getting accounts list."""
        response = client.get("/api/accounts")
        assert response.status_code == 200
        assert isinstance(response.json, list)
        assert len(response.json) > 0

    def test_get_tags(self, client, app):
        """Test getting tags list."""
        response = client.get("/api/tags")
        assert response.status_code == 200
        assert isinstance(response.json, list)

    def test_get_categories(self, client, app, test_account, test_category):
        """Test getting categories list."""
        response = client.get("/api/categories")
        assert response.status_code == 200
        assert isinstance(response.json, list)
