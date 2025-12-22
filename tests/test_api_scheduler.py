"""
Tests for API routes - scheduler and additional coverage
"""
from unittest.mock import MagicMock, patch

import pytest

from models import Account, Category, Channel, ChannelTag, Tag, db


@pytest.fixture
def test_account(app):
    """Create a test account"""
    with app.app_context():
        account = Account(
            name="Test Account",
            username="test_user",
            password="test_pass",
            server="http://example.com",
            enabled=True,
        )
        db.session.add(account)
        db.session.commit()
        yield account


# ============================================================================
# Scheduler API Tests
# ============================================================================


class TestSchedulerAPI:
    """Tests for scheduler management endpoints"""

    def test_scheduler_status_no_scheduler(self, app, client):
        """Test scheduler status when scheduler not initialized"""
        with patch("routes.api._scheduler", None):
            response = client.get("/api/scheduler/status")
            assert response.status_code == 500
            assert "error" in response.json

    def test_scheduler_status_success(self, app, client):
        """Test scheduler status returns correct info"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True
        mock_scheduler.interval_hours = 6
        mock_scheduler.interval_seconds = 21600

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.get("/api/scheduler/status")
            assert response.status_code == 200
            data = response.json
            assert data["running"] is True
            assert data["interval_hours"] == 6

    def test_scheduler_stop_no_scheduler(self, app, client):
        """Test stop scheduler when not initialized"""
        with patch("routes.api._scheduler", None):
            response = client.post("/api/scheduler/stop")
            assert response.status_code == 500

    def test_scheduler_stop_not_running(self, app, client):
        """Test stop scheduler when already stopped"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post("/api/scheduler/stop")
            assert response.status_code == 400
            assert "not running" in response.json["error"]

    def test_scheduler_stop_success(self, app, client):
        """Test successful scheduler stop"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post("/api/scheduler/stop")
            assert response.status_code == 200
            assert response.json["success"] is True
            mock_scheduler.stop.assert_called_once()

    def test_scheduler_start_no_scheduler(self, app, client):
        """Test start scheduler when not initialized"""
        with patch("routes.api._scheduler", None):
            response = client.post("/api/scheduler/start")
            assert response.status_code == 500

    def test_scheduler_start_already_running(self, app, client):
        """Test start scheduler when already running"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = True

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post("/api/scheduler/start")
            assert response.status_code == 400
            assert "already running" in response.json["error"]

    def test_scheduler_start_success(self, app, client):
        """Test successful scheduler start"""
        mock_scheduler = MagicMock()
        mock_scheduler.running = False

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post("/api/scheduler/start")
            assert response.status_code == 200
            assert response.json["success"] is True
            mock_scheduler.start.assert_called_once()

    def test_scheduler_restart_no_scheduler(self, app, client):
        """Test restart scheduler when not initialized"""
        with patch("routes.api._scheduler", None):
            response = client.post("/api/scheduler/restart")
            assert response.status_code == 500

    def test_scheduler_restart_success(self, app, client):
        """Test successful scheduler restart"""
        mock_scheduler = MagicMock()
        mock_scheduler.interval_hours = 6

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post(
                "/api/scheduler/restart",
                json={},
                content_type="application/json",
            )
            assert response.status_code == 200
            assert response.json["success"] is True
            mock_scheduler.stop.assert_called_once()
            mock_scheduler.start.assert_called_once()

    def test_scheduler_restart_with_new_interval(self, app, client):
        """Test scheduler restart with new interval"""
        mock_scheduler = MagicMock()
        mock_scheduler.interval_hours = 6

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post(
                "/api/scheduler/restart",
                json={"interval_hours": 12},
                content_type="application/json",
            )
            assert response.status_code == 200
            assert response.json["interval_hours"] == 12
            mock_scheduler.stop.assert_called_once()
            mock_scheduler.start.assert_called_once()

    def test_scheduler_restart_invalid_interval(self, app, client):
        """Test scheduler restart with invalid interval"""
        mock_scheduler = MagicMock()

        with patch("routes.api._scheduler", mock_scheduler):
            response = client.post(
                "/api/scheduler/restart",
                json={"interval_hours": "invalid"},
                content_type="application/json",
            )
            assert response.status_code == 400

    def test_scheduler_restart_interval_out_of_range(self, app, client):
        """Test scheduler restart with interval out of range"""
        mock_scheduler = MagicMock()

        with patch("routes.api._scheduler", mock_scheduler):
            # Test too low
            response = client.post(
                "/api/scheduler/restart",
                json={"interval_hours": 0},
                content_type="application/json",
            )
            assert response.status_code == 400
            assert "between 1 and 168" in response.json["error"]

            # Test too high
            response = client.post(
                "/api/scheduler/restart",
                json={"interval_hours": 200},
                content_type="application/json",
            )
            assert response.status_code == 400


# ============================================================================
# Cache API Tests
# ============================================================================


class TestCacheAPI:
    """Tests for cache management endpoints"""

    def test_clear_all_cache(self, app, client):
        """Test clearing all caches"""
        response = client.post("/api/cache/clear")
        assert response.status_code == 200
        assert response.json["success"] is True

    def test_clear_account_cache_not_found(self, app, client):
        """Test clearing cache for non-existent account"""
        response = client.post("/api/cache/clear/999")
        assert response.status_code == 404

    def test_clear_account_cache_success(self, app, client, test_account):
        """Test clearing cache for specific account"""
        response = client.post(f"/api/cache/clear/{test_account.id}")
        assert response.status_code == 200
        assert response.json["success"] is True


# ============================================================================
# Categories API Tests
# ============================================================================


class TestCategoriesAPI:
    """Tests for category endpoints"""

    def test_get_all_categories_empty(self, app, client):
        """Test getting categories when none exist"""
        response = client.get("/api/categories")
        assert response.status_code == 200
        assert response.json == []

    def test_get_categories_with_data(self, app, client, test_account):
        """Test getting categories with data"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()  # Get the category.id

            # Add a visible channel to the category - note: category.id is the FK
            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        # Default behavior excludes empty categories, so we need include_empty
        # or we check for visible channels which we have
        response = client.get("/api/categories?include_empty=true")
        assert response.status_code == 200
        data = response.json
        assert len(data) >= 1

    def test_get_categories_with_account_filter(self, app, client, test_account):
        """Test getting categories filtered by account"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)

            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get(f"/api/categories?account_id={test_account.id}")
        assert response.status_code == 200

    def test_get_categories_include_empty(self, app, client, test_account):
        """Test getting categories including empty ones"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Empty Category",
            )
            db.session.add(category)
            db.session.commit()

        response = client.get("/api/categories?include_empty=true")
        assert response.status_code == 200

    def test_get_categories_include_epg(self, app, client, test_account):
        """Test getting categories with EPG coverage info"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)

            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get("/api/categories?include_epg=true")
        assert response.status_code == 200

    def test_get_categories_invalid_account(self, app, client):
        """Test getting categories for non-existent account"""
        response = client.get("/api/categories?account_id=999")
        assert response.status_code == 404


# ============================================================================
# Channel Preview API Tests
# ============================================================================


class TestChannelPreviewAPI:
    """Tests for channel preview endpoint"""

    def test_preview_channels_empty(self, app, client):
        """Test channel preview when no channels exist"""
        response = client.get("/api/channels/preview")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 0
        assert data["channels"] == []

    def test_preview_channels_with_data(self, app, client, test_account):
        """Test channel preview with data"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="Movie Channel",
                cleaned_name="Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get("/api/channels/preview")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1
        assert data["channels"][0]["name"] == "Movie Channel"

    def test_preview_channels_with_account_filter(self, app, client, test_account):
        """Test channel preview filtered by account"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get(f"/api/channels/preview?account_id={test_account.id}")
        assert response.status_code == 200

    def test_preview_channels_with_category_filter(self, app, client, test_account):
        """Test channel preview filtered by category"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.commit()

        response = client.get("/api/channels/preview?category=Movies")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1

    def test_preview_channels_with_tag_filter(self, app, client, test_account):
        """Test channel preview filtered by tags"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            channel = Channel(
                account_id=test_account.id,
                stream_id="ch1",
                name="HD Movie Channel",
                category_id=category.id,
                is_active=True,
                is_visible=True,
            )
            db.session.add(channel)
            db.session.flush()

            # Add tag
            tag = Tag(name="HD")
            db.session.add(tag)
            db.session.flush()

            channel_tag = ChannelTag(
                account_id=test_account.id,
                stream_id="ch1",
                tag_id=tag.id,
            )
            db.session.add(channel_tag)
            db.session.commit()

        response = client.get("/api/channels/preview?tags=HD")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 1

    def test_preview_channels_pagination(self, app, client, test_account):
        """Test channel preview pagination"""
        with app.app_context():
            category = Category(
                account_id=test_account.id,
                category_id="cat1",
                category_name="Movies",
            )
            db.session.add(category)
            db.session.flush()

            # Create multiple channels
            for i in range(10):
                channel = Channel(
                    account_id=test_account.id,
                    stream_id=f"ch{i}",
                    name=f"Channel {i}",
                    category_id=category.id,
                    is_active=True,
                    is_visible=True,
                )
                db.session.add(channel)
            db.session.commit()

        response = client.get("/api/channels/preview?limit=5&offset=0")
        assert response.status_code == 200
        data = response.json
        assert data["total"] == 10
        assert data["showing"] == 5
        assert data["has_more"] is True

    def test_preview_channels_invalid_account(self, app, client):
        """Test channel preview with invalid account"""
        response = client.get("/api/channels/preview?account_id=999")
        assert response.status_code == 404
