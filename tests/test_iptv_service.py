"""
Tests for IPTV Service
"""

from unittest.mock import Mock, patch

import pytest
import requests

from services.iptv_service import IPTVService


class TestIPTVService:
    """Test suite for IPTVService"""

    def test_init(self):
        """Test service initialization"""
        service = IPTVService("example.com:8080", "testuser", "testpass")

        assert service.server == "example.com:8080"
        assert service.username == "testuser"
        assert service.password == "testpass"
        assert service.base_url == "https://example.com:8080"
        assert service.user_agent == "okhttp/3.14.9"

    def test_init_custom_user_agent(self):
        """Test service initialization with custom user agent"""
        service = IPTVService("example.com:8080", "user", "pass", user_agent="CustomAgent/1.0")

        assert service.user_agent == "CustomAgent/1.0"

    @patch("requests.get")
    def test_authenticate_success(self, mock_get):
        """Test successful authentication"""
        mock_response = Mock()
        mock_response.json.return_value = {
            "user_info": {"username": "testuser", "status": "Active", "exp_date": "1735689600"},
            "server_info": {"url": "http://example.com:8080", "time_now": "2024-12-19 10:00:00"},
        }
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        result = service.authenticate()

        assert result["user_info"]["username"] == "testuser"
        assert result["user_info"]["status"] == "Active"
        mock_get.assert_called_once()

    @patch("requests.get")
    def test_authenticate_http_error(self, mock_get):
        """Test authentication with HTTP error"""
        mock_get.side_effect = requests.exceptions.HTTPError("401 Unauthorized")

        service = IPTVService("example.com:8080", "baduser", "badpass")

        with pytest.raises(requests.exceptions.HTTPError):
            service.authenticate()

    @patch("requests.get")
    def test_authenticate_timeout(self, mock_get):
        """Test authentication timeout"""
        mock_get.side_effect = requests.exceptions.Timeout("Connection timeout")

        service = IPTVService("example.com:8080", "testuser", "testpass")

        with pytest.raises(requests.exceptions.Timeout):
            service.authenticate()

    @patch("requests.get")
    def test_get_live_categories(self, mock_get):
        """Test fetching live categories"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"category_id": "1", "category_name": "Sports", "parent_id": 0},
            {"category_id": "2", "category_name": "Movies", "parent_id": 0},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        categories = service.get_live_categories()

        assert len(categories) == 2
        assert categories[0]["category_name"] == "Sports"
        assert categories[1]["category_name"] == "Movies"

    @patch("requests.get")
    def test_get_live_streams_no_filter(self, mock_get):
        """Test fetching all live streams"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"stream_id": 101, "name": "ESPN", "category_id": "1"},
            {"stream_id": 102, "name": "CNN", "category_id": "2"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        streams = service.get_live_streams()

        assert len(streams) == 2
        assert streams[0]["name"] == "ESPN"

    @patch("requests.get")
    def test_get_live_streams_with_category(self, mock_get):
        """Test fetching live streams filtered by category"""
        mock_response = Mock()
        mock_response.json.return_value = [{"stream_id": 101, "name": "ESPN", "category_id": "1"}]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        streams = service.get_live_streams(category_id="1")

        assert len(streams) == 1
        assert streams[0]["category_id"] == "1"

        # Check that category_id was passed in params
        call_args = mock_get.call_args
        assert call_args[1]["params"]["category_id"] == "1"

    @patch("requests.get")
    def test_get_vod_categories(self, mock_get):
        """Test fetching VOD categories"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"category_id": "10", "category_name": "Action Movies"},
            {"category_id": "11", "category_name": "Comedy Movies"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        categories = service.get_vod_categories()

        assert len(categories) == 2
        assert categories[0]["category_name"] == "Action Movies"

    @patch("requests.get")
    def test_get_vod_streams(self, mock_get):
        """Test fetching VOD streams"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"stream_id": 201, "name": "Die Hard", "category_id": "10"},
            {"stream_id": 202, "name": "The Matrix", "category_id": "10"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        streams = service.get_vod_streams()

        assert len(streams) == 2
        assert streams[0]["name"] == "Die Hard"

    @patch("requests.get")
    def test_get_xmltv(self, mock_get):
        """Test fetching XMLTV/EPG data"""
        mock_response = Mock()
        mock_response.content = b'<?xml version="1.0"?><tv></tv>'
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        xmltv = service.get_xmltv()

        assert b'<?xml version="1.0"?>' in xmltv
        assert b"<tv></tv>" in xmltv

    @patch("requests.get")
    def test_make_request_includes_auth(self, mock_get):
        """Test that requests include authentication parameters"""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        service.get_live_streams()

        call_args = mock_get.call_args
        params = call_args[1]["params"]

        assert params["username"] == "testuser"
        assert params["password"] == "testpass"
        assert params["action"] == "get_live_streams"

    @patch("requests.get")
    def test_make_request_includes_user_agent(self, mock_get):
        """Test that requests include user agent header"""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        service.get_live_streams()

        call_args = mock_get.call_args
        headers = call_args[1]["headers"]

        assert headers["User-Agent"] == "okhttp/3.14.9"

    @patch("requests.get")
    def test_make_request_timeout(self, mock_get):
        """Test that requests have timeout set"""
        mock_response = Mock()
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        service.authenticate()

        call_args = mock_get.call_args
        assert call_args[1]["timeout"] == 30

    @patch("requests.get")
    def test_get_series_categories(self, mock_get):
        """Test fetching series categories"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"category_id": "20", "category_name": "Drama Series"},
            {"category_id": "21", "category_name": "Comedy Series"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        categories = service.get_series_categories()

        assert len(categories) == 2
        assert categories[0]["category_name"] == "Drama Series"
        assert categories[1]["category_name"] == "Comedy Series"

        # Verify correct action was passed
        call_args = mock_get.call_args
        assert call_args[1]["params"]["action"] == "get_series_categories"

    @patch("requests.get")
    def test_get_series_no_filter(self, mock_get):
        """Test fetching all series"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"series_id": 301, "name": "Breaking Bad", "category_id": "20"},
            {"series_id": 302, "name": "Game of Thrones", "category_id": "20"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        series = service.get_series()

        assert len(series) == 2
        assert series[0]["name"] == "Breaking Bad"
        assert series[1]["name"] == "Game of Thrones"

        # Verify correct action was passed
        call_args = mock_get.call_args
        assert call_args[1]["params"]["action"] == "get_series"
        assert "category_id" not in call_args[1]["params"]

    @patch("requests.get")
    def test_get_series_with_category(self, mock_get):
        """Test fetching series filtered by category"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"series_id": 301, "name": "Breaking Bad", "category_id": "20"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        series = service.get_series(category_id="20")

        assert len(series) == 1
        assert series[0]["category_id"] == "20"

        # Check that category_id was passed in params
        call_args = mock_get.call_args
        assert call_args[1]["params"]["category_id"] == "20"
        assert call_args[1]["params"]["action"] == "get_series"

    @patch("requests.get")
    def test_get_vod_streams_with_category(self, mock_get):
        """Test fetching VOD streams filtered by category"""
        mock_response = Mock()
        mock_response.json.return_value = [
            {"stream_id": 401, "name": "Inception", "category_id": "10"},
        ]
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        streams = service.get_vod_streams(category_id="10")

        assert len(streams) == 1
        assert streams[0]["category_id"] == "10"

        # Check that category_id was passed in params
        call_args = mock_get.call_args
        assert call_args[1]["params"]["category_id"] == "10"
        assert call_args[1]["params"]["action"] == "get_vod_streams"

    @patch("requests.get")
    def test_get_xmltv_timeout(self, mock_get):
        """Test that XMLTV requests have extended timeout"""
        mock_response = Mock()
        mock_response.content = b"<tv></tv>"
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        service.get_xmltv()

        call_args = mock_get.call_args
        # XMLTV has 120s timeout (longer than regular API calls)
        assert call_args[1]["timeout"] == 120

    @patch("requests.get")
    def test_get_xmltv_user_agent(self, mock_get):
        """Test that XMLTV requests use special user agent"""
        mock_response = Mock()
        mock_response.content = b"<tv></tv>"
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        service.get_xmltv()

        call_args = mock_get.call_args
        # XMLTV uses different user agent
        assert call_args[1]["headers"]["User-Agent"] == "9XtreamPlayer"

    @patch("requests.get")
    def test_get_xmltv_correct_url(self, mock_get):
        """Test that XMLTV requests use xmltv.php endpoint"""
        mock_response = Mock()
        mock_response.content = b"<tv></tv>"
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")
        service.get_xmltv()

        call_args = mock_get.call_args
        url = call_args[0][0]
        assert "xmltv.php" in url
        assert "player_api.php" not in url

    @patch("requests.get")
    def test_connection_error(self, mock_get):
        """Test handling of connection errors"""
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")

        service = IPTVService("example.com:8080", "testuser", "testpass")

        with pytest.raises(requests.exceptions.ConnectionError):
            service.authenticate()

    @patch("requests.get")
    def test_json_decode_error(self, mock_get):
        """Test handling of invalid JSON response"""
        mock_response = Mock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_get.return_value = mock_response

        service = IPTVService("example.com:8080", "testuser", "testpass")

        with pytest.raises(ValueError):
            service.get_live_categories()
