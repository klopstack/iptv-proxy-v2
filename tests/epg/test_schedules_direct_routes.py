"""Tests for Schedules Direct HTTP endpoints."""
from unittest.mock import MagicMock, patch

from models import EpgSource, db


class TestSchedulesDirectAPI:
    """Tests for Schedules Direct API endpoints"""

    def test_test_sd_credentials_missing_username(self, app, client):
        """Test testing SD credentials without username"""
        response = client.post(
            "/api/epg/sd/test",
            json={"password": "testpass"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "required" in response.json["error"].lower()

    def test_test_sd_credentials_missing_password(self, app, client):
        """Test testing SD credentials without password"""
        response = client.post(
            "/api/epg/sd/test",
            json={"username": "testuser"},
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "required" in response.json["error"].lower()

    @patch("services.schedules_direct.validate_credentials")
    def test_test_sd_credentials_success(self, mock_validate, app, client):
        """Test successful SD credential validation"""
        mock_validate.return_value = {
            "success": True,
            "message": "Authentication successful",
            "account": {"max_lineups": 5},
        }

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "testuser", "password": "testpass"},
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json["success"] is True

    @patch("services.schedules_direct.validate_credentials")
    def test_test_sd_credentials_failure(self, mock_validate, app, client):
        """Test failed SD credential validation"""
        mock_validate.return_value = {
            "success": False,
            "message": "Invalid credentials",
        }

        response = client.post(
            "/api/epg/sd/test",
            json={"username": "testuser", "password": "wrongpass"},
            content_type="application/json",
        )
        assert response.status_code == 401
        assert response.json["success"] is False

    def test_search_sd_lineups_missing_source_id(self, app, client):
        """Test searching SD lineups without source_id"""
        response = client.get("/api/epg/sd/lineups/search?postalcode=10001")
        assert response.status_code == 400
        assert "source_id" in response.json["error"].lower()

    def test_search_sd_lineups_wrong_source_type(self, app, client, test_epg_source):
        """Test searching SD lineups with non-SD source"""
        response = client.get(f"/api/epg/sd/lineups/search?source_id={test_epg_source}&postalcode=10001")
        assert response.status_code == 400
        assert "schedules direct" in response.json["error"].lower()

    def test_search_sd_lineups_no_credentials(self, app, client):
        """Test searching SD lineups without credentials configured"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.get(f"/api/epg/sd/lineups/search?source_id={source_id}&postalcode=10001")
        assert response.status_code == 400
        assert "credentials" in response.json["error"].lower()

    @patch("routes.epg.schedules_direct.SchedulesDirectClient")
    def test_search_sd_lineups_success(self, MockClient, app, client):
        """Test successful SD lineup search"""
        # Create SD source with credentials
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="testuser",
                sd_password="testpass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        # Mock the client
        mock_client = MagicMock()
        mock_client.search_lineups.return_value = [{"lineup": "USA-NY12345-X", "name": "Test Lineup"}]
        MockClient.return_value = mock_client

        response = client.get(f"/api/epg/sd/lineups/search?source_id={source_id}&postalcode=10001")
        assert response.status_code == 200
        assert response.json["success"] is True
        assert len(response.json["lineups"]) == 1

    @patch("routes.epg.schedules_direct.SchedulesDirectClient")
    def test_search_sd_lineups_error(self, MockClient, app, client):
        """Test SD lineup search with error"""
        from services.schedules_direct import SchedulesDirectError

        # Create SD source with credentials
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                sd_username="testuser",
                sd_password="testpass",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        # Mock the client to raise an error
        mock_client = MagicMock()
        mock_client.authenticate.side_effect = SchedulesDirectError("Test error", code=4003)
        MockClient.return_value = mock_client

        response = client.get(f"/api/epg/sd/lineups/search?source_id={source_id}&postalcode=10001")
        assert response.status_code == 400
        assert "Test error" in response.json["error"]

    def test_get_sd_lineups_missing_source_id(self, app, client):
        """Test getting SD lineups without source_id"""
        response = client.get("/api/epg/sd/lineups")
        assert response.status_code == 400
        assert "source_id" in response.json["error"].lower()

    def test_get_sd_lineups_success(self, app, client):
        """Test getting SD lineups successfully"""
        with app.app_context():
            source = EpgSource(
                name="SD Source",
                source_type="schedules_direct",
                enabled=True,
            )
            db.session.add(source)
            db.session.commit()
            source_id = source.id

        response = client.get(f"/api/epg/sd/lineups?source_id={source_id}")
        assert response.status_code == 200
        # Response is a dict with lineups array and metadata
        assert "lineups" in response.json
        assert isinstance(response.json["lineups"], list)
