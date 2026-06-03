"""Tests for XMLTV grabber HTTP endpoints."""

from unittest.mock import MagicMock, patch


class TestXmltvGrabber:
    """Tests for XMLTV grabber endpoints."""

    @patch("services.xmltv_grabber_service.XmltvGrabberService.get_installed_grabbers")
    def test_get_xmltv_grabbers(self, mock_grabbers, app, client):
        """Test getting list of installed grabbers."""
        mock_grabber = MagicMock()
        mock_grabber.name = "tv_grab_zz_sdjson"
        mock_grabber.description = "Schedules Direct JSON grabber"
        mock_grabber.path = "/usr/bin/tv_grab_zz_sdjson"
        mock_grabber.capabilities = ["baseline"]
        mock_grabbers.return_value = [mock_grabber]

        response = client.get("/api/xmltv/grabbers")
        assert response.status_code == 200
        assert len(response.json) == 1
        assert response.json[0]["name"] == "tv_grab_zz_sdjson"

    @patch("services.xmltv_grabber_service.XmltvGrabberService.get_grabber_by_name")
    def test_get_xmltv_grabber_success(self, mock_get, app, client):
        """Test getting info about a specific grabber."""
        mock_grabber = MagicMock()
        mock_grabber.name = "tv_grab_zz_sdjson"
        mock_grabber.description = "SD JSON"
        mock_grabber.path = "/usr/bin/tv_grab_zz_sdjson"
        mock_grabber.capabilities = ["baseline"]
        mock_get.return_value = mock_grabber

        response = client.get("/api/xmltv/grabbers/tv_grab_zz_sdjson")
        assert response.status_code == 200
        assert response.json["name"] == "tv_grab_zz_sdjson"

    @patch("services.xmltv_grabber_service.XmltvGrabberService.get_grabber_by_name")
    def test_get_xmltv_grabber_not_found(self, mock_get, app, client):
        """Test getting non-existent grabber."""
        mock_get.return_value = None

        response = client.get("/api/xmltv/grabbers/nonexistent")
        assert response.status_code == 404
