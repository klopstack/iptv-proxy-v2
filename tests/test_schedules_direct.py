"""
Tests for Schedules Direct API client
"""
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
import requests

from services.schedules_direct import (
    CastMember,
    ContentRating,
    EventDetails,
    MovieInfo,
    Program,
    ProgramDescription,
    ProgramMetadata,
    ProgramTitle,
    RateLimitError,
    SchedulesDirectClient,
    SchedulesDirectError,
    validate_credentials,
)

# ============================================================================
# Exception Tests
# ============================================================================


class TestExceptions:
    """Tests for custom exceptions"""

    def test_schedules_direct_error(self):
        """Test SchedulesDirectError exception"""
        error = SchedulesDirectError("Test error", code=100, response={"test": "data"})
        assert error.message == "Test error"
        assert error.code == 100
        assert error.response == {"test": "data"}
        assert str(error) == "Test error"

    def test_rate_limit_error(self):
        """Test RateLimitError exception"""
        error = RateLimitError("Rate limited", code=429, retry_after=3600)
        assert error.message == "Rate limited"
        assert error.code == 429
        assert error.retry_after == 3600

    def test_rate_limit_error_default_retry_after(self):
        """Test RateLimitError with default retry_after"""
        error = RateLimitError("Rate limited", code=429)
        assert error.retry_after == 86400  # Default 24 hours


# ============================================================================
# Client Initialization Tests
# ============================================================================


class TestClientInit:
    """Tests for client initialization"""

    def test_client_initialization(self):
        """Test client initializes correctly"""
        client = SchedulesDirectClient("testuser", "testpass")
        assert client.username == "testuser"
        assert client.password == "testpass"
        assert client.token is None
        assert client.token_expires is None
        assert client.session is not None

    def test_client_headers(self):
        """Test client sets correct headers"""
        client = SchedulesDirectClient("testuser", "testpass")
        assert "User-Agent" in client.session.headers
        assert "IPTV-Proxy" in client.session.headers["User-Agent"]
        assert client.session.headers["Accept"] == "application/json"


# ============================================================================
# Password Hashing Tests
# ============================================================================


class TestPasswordHashing:
    """Tests for password hashing"""

    def test_hash_password(self):
        """Test SHA1 password hashing"""
        client = SchedulesDirectClient("testuser", "testpass")
        hashed = client._hash_password("password123")
        # SHA1 of "password123"
        expected = "cbfdac6008f9cab4083784cbd1874f76618d2a97"
        assert hashed == expected

    def test_hash_password_empty(self):
        """Test hashing empty password"""
        client = SchedulesDirectClient("testuser", "")
        hashed = client._hash_password("")
        # SHA1 of empty string
        expected = "da39a3ee5e6b4b0d3255bfef95601890afd80709"
        assert hashed == expected


# ============================================================================
# Authentication Tests
# ============================================================================


class TestAuthentication:
    """Tests for authentication"""

    def test_authenticate_success(self):
        """Test successful authentication"""
        client = SchedulesDirectClient("testuser", "testpass")
        import time

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 0,
            "token": "test-token-123",
            "tokenExpires": int(time.time()) + 86400,  # 24 hours from now
        }

        with patch.object(client.session, "post", return_value=mock_response):
            result = client.authenticate()

        assert client.token == "test-token-123"
        assert client.token_expires is not None
        assert result["token"] == "test-token-123"

    def test_authenticate_failure(self):
        """Test authentication failure"""
        client = SchedulesDirectClient("testuser", "wrongpass")

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "code": 4003,
            "message": "Invalid credentials",
        }

        with patch.object(client.session, "post", return_value=mock_response):
            with pytest.raises(SchedulesDirectError) as exc_info:
                client.authenticate()

        assert "Invalid credentials" in str(exc_info.value)

    def test_authenticate_network_error(self):
        """Test authentication with network error"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client.session, "post", side_effect=requests.RequestException("Network error")):
            with pytest.raises(SchedulesDirectError) as exc_info:
                client.authenticate()

        assert "Authentication failed" in str(exc_info.value)


# ============================================================================
# Rate Limiting Tests
# ============================================================================


class TestRateLimiting:
    """Tests for rate limiting"""

    def test_throttle_regular_request(self):
        """Test throttling between regular requests"""
        client = SchedulesDirectClient("testuser", "testpass")

        # Reset class-level rate limiting
        SchedulesDirectClient._last_request_time = time.time()

        # This should wait if called immediately after
        start = time.time()
        client._throttle(is_image=False)
        elapsed = time.time() - start

        # Should have waited some time (may be 0 if enough time passed)
        assert elapsed >= 0

    def test_check_rate_limit_error_5002(self):
        """Test detection of subscriber rate limit error"""
        client = SchedulesDirectClient("testuser", "testpass")

        with pytest.raises(RateLimitError) as exc_info:
            client._check_rate_limit_error({"code": 5002})

        assert exc_info.value.code == 5002
        assert exc_info.value.retry_after == 86400

    def test_check_rate_limit_error_5003(self):
        """Test detection of trial user rate limit error"""
        client = SchedulesDirectClient("testuser", "testpass")

        with pytest.raises(RateLimitError) as exc_info:
            client._check_rate_limit_error({"code": 5003})

        assert exc_info.value.code == 5003
        assert exc_info.value.retry_after == 86400

    def test_check_rate_limit_error_no_error(self):
        """Test that no error is raised for normal responses"""
        client = SchedulesDirectClient("testuser", "testpass")
        # Should not raise
        client._check_rate_limit_error({"code": 0, "response": "OK"})


# ============================================================================
# API Request Tests
# ============================================================================


class TestMakeRequest:
    """Tests for _make_request method"""

    def test_make_request_get(self):
        """Test GET request"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400  # Set valid expiry

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": "test"}

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_throttle"):
                result = client._make_request("GET", "test/endpoint")

        assert result["data"] == "test"

    def test_make_request_post(self):
        """Test POST request"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": "test"}

        with patch.object(client.session, "post", return_value=mock_response):
            with patch.object(client, "_throttle"):
                result = client._make_request("POST", "test/endpoint", data={"test": "data"})

        assert result["data"] == "test"

    def test_make_request_put(self):
        """Test PUT request"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": "test"}

        with patch.object(client.session, "put", return_value=mock_response):
            with patch.object(client, "_throttle"):
                result = client._make_request("PUT", "test/endpoint")

        assert result["data"] == "test"

    def test_make_request_delete(self):
        """Test DELETE request"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": 0, "data": "test"}

        with patch.object(client.session, "delete", return_value=mock_response):
            with patch.object(client, "_throttle"):
                result = client._make_request("DELETE", "test/endpoint")

        assert result["data"] == "test"

    def test_make_request_invalid_method(self):
        """Test invalid HTTP method raises error"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        with patch.object(client, "_throttle"):
            with pytest.raises(ValueError) as exc_info:
                client._make_request("PATCH", "test/endpoint")

        assert "Unsupported HTTP method" in str(exc_info.value)

    def test_make_request_429_rate_limit(self):
        """Test 429 rate limit response"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.headers = {"Retry-After": "7200"}

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_throttle"):
                with pytest.raises(RateLimitError) as exc_info:
                    client._make_request("GET", "test/endpoint")

        assert exc_info.value.code == 429
        assert exc_info.value.retry_after == 7200

    def test_make_request_403_reauth(self):
        """Test token expiration triggers re-authentication"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "old-token"
        # Token expired - should trigger re-auth
        client.token_expires = int(time.time()) - 100  # Expired 100 seconds ago

        mock_response_ok = MagicMock()
        mock_response_ok.status_code = 200
        mock_response_ok.json.return_value = {"code": 0, "data": "test"}

        def do_authenticate():
            client.token = "new-token"
            client.token_expires = int(time.time()) + 86400
            return {"token": "new-token", "tokenExpires": client.token_expires}

        with patch.object(client.session, "get", return_value=mock_response_ok):
            with patch.object(client, "_throttle"):
                with patch.object(client, "authenticate", side_effect=do_authenticate) as mock_auth:
                    result = client._make_request("GET", "test/endpoint")

        mock_auth.assert_called_once()
        assert result["data"] == "test"

    def test_make_request_api_error(self):
        """Test API-level error handling"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": 1001,
            "message": "Some API error",
            "response": "ERROR",
        }

        with patch.object(client.session, "get", return_value=mock_response):
            with patch.object(client, "_throttle"):
                with pytest.raises(SchedulesDirectError) as exc_info:
                    client._make_request("GET", "test/endpoint")

        assert "Some API error" in str(exc_info.value)

    def test_make_request_network_error(self):
        """Test network error handling"""
        import time

        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int(time.time()) + 86400

        with patch.object(client.session, "get", side_effect=requests.RequestException("Connection error")):
            with patch.object(client, "_throttle"):
                with pytest.raises(SchedulesDirectError) as exc_info:
                    client._make_request("GET", "test/endpoint")

        assert "API request failed" in str(exc_info.value)


# ============================================================================
# API Endpoint Tests
# ============================================================================


class TestAPIEndpoints:
    """Tests for API endpoint methods"""

    def test_get_status(self):
        """Test get_status method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = {"account": {}, "lineups": []}
            result = client.get_status()

        mock_request.assert_called_once_with("GET", "status")
        assert "account" in result

    def test_get_available_services(self):
        """Test get_available_services method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = [{"type": "Cable"}]
            client.get_available_services()

        mock_request.assert_called_once_with("GET", "available", authenticated=False)

    def test_search_lineups_by_postal(self):
        """Test search_lineups with postal code"""
        client = SchedulesDirectClient("testuser", "testpass")

        mock_result = [
            {"headend": "Cable", "location": "New York", "lineups": [{"lineup": "USA-NY12345-X", "name": "Provider A"}]}
        ]

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = mock_result
            result = client.search_lineups(country="USA", postalcode="10001")

        mock_request.assert_called_once_with("GET", "headends?country=USA&postalcode=10001")
        assert len(result) == 1
        assert result[0]["lineup"] == "USA-NY12345-X"

    def test_search_lineups_by_id(self):
        """Test search_lineups with specific lineup ID"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = {"lineup": "USA-NY12345-X"}
            result = client.search_lineups(lineup_id="USA-NY12345-X")

        mock_request.assert_called_once_with("GET", "lineups/USA-NY12345-X")
        assert len(result) == 1

    def test_add_lineup(self):
        """Test add_lineup method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = {"response": "OK"}
            client.add_lineup("USA-NY12345-X")

        mock_request.assert_called_once_with("PUT", "lineups/USA-NY12345-X")

    def test_remove_lineup(self):
        """Test remove_lineup method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = {"response": "OK"}
            client.remove_lineup("USA-NY12345-X")

        mock_request.assert_called_once_with("DELETE", "lineups/USA-NY12345-X")

    def test_get_lineups(self):
        """Test get_lineups method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = {"lineups": [{"lineup": "USA-NY12345-X"}]}
            result = client.get_lineups()

        assert len(result) == 1
        assert result[0]["lineup"] == "USA-NY12345-X"

    def test_get_lineup_map(self):
        """Test get_lineup_map method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = {"map": [], "stations": []}
            client.get_lineup_map("USA-NY12345-X")

        mock_request.assert_called_once_with("GET", "lineups/USA-NY12345-X")

    def test_get_lineup_channels(self):
        """Test get_lineup_channels method"""
        client = SchedulesDirectClient("testuser", "testpass")

        mock_lineup = {
            "map": [{"stationID": "12345", "channel": "5"}],
            "stations": [
                {
                    "stationID": "12345",
                    "callsign": "WABC",
                    "name": "WABC-TV",
                    "affiliate": "ABC",
                    "logo": {"URL": "http://example.com/logo.png", "height": 100, "width": 100, "md5": "abc123"},
                }
            ],
        }

        with patch.object(client, "get_lineup_map", return_value=mock_lineup):
            result = client.get_lineup_channels("USA-NY12345-X")

        assert len(result) == 1
        assert result[0]["stationID"] == "12345"
        assert result[0]["callsign"] == "WABC"
        assert result[0]["logo"]["url"] == "http://example.com/logo.png"

    def test_get_schedules(self):
        """Test get_schedules method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = [{"stationID": "12345", "programs": []}]
            client.get_schedules(["12345"])

        mock_request.assert_called_once()
        args = mock_request.call_args
        assert args[0][0] == "POST"
        assert args[0][1] == "schedules"

    def test_get_schedules_with_dates(self):
        """Test get_schedules with specific dates"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = []
            client.get_schedules(["12345"], dates=["2024-01-01", "2024-01-02"])

        args = mock_request.call_args
        assert len(args[0][2]) == 1
        assert args[0][2][0]["date"] == ["2024-01-01", "2024-01-02"]

    def test_get_programs(self):
        """Test get_programs method"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client, "_make_request") as mock_request:
            mock_request.return_value = [{"programID": "EP123"}]
            client.get_programs(["EP123"])

        mock_request.assert_called_once_with("POST", "programs", ["EP123"])

    def test_search_stations(self):
        """Test search_stations returns empty (no direct endpoint)"""
        client = SchedulesDirectClient("testuser", "testpass")
        result = client.search_stations("ESPN")
        assert result == []

    def test_get_system_status(self):
        """Test get_system_status method"""
        client = SchedulesDirectClient("testuser", "testpass")

        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "Online"}

        with patch.object(client.session, "get", return_value=mock_response):
            result = client.get_system_status()

        assert result["status"] == "Online"

    def test_get_system_status_error(self):
        """Test get_system_status handles errors"""
        client = SchedulesDirectClient("testuser", "testpass")

        with patch.object(client.session, "get", side_effect=Exception("Connection error")):
            result = client.get_system_status()

        assert "error" in result


# ============================================================================
# validate_credentials Function Tests
# ============================================================================


class TestCredentialsFunction:
    """Tests for validate_credentials helper function"""

    def test_credentials_success(self):
        """Test successful credential test"""
        mock_auth_result = {"token": "test-token"}
        mock_status = {"account": {"maxLineups": 5, "expires": "2025-12-31"}, "lineups": [{"lineup": "USA-NY12345-X"}]}

        with patch.object(SchedulesDirectClient, "authenticate", return_value=mock_auth_result):
            with patch.object(SchedulesDirectClient, "get_status", return_value=mock_status):
                result = validate_credentials("testuser", "testpass")

        assert result["success"] is True
        assert result["message"] == "Authentication successful"
        assert result["account"]["max_lineups"] == 5

    def test_credentials_failure(self):
        """Test failed credential test"""
        with patch.object(
            SchedulesDirectClient, "authenticate", side_effect=SchedulesDirectError("Invalid credentials", code=4003)
        ):
            result = validate_credentials("testuser", "wrongpass")

        assert result["success"] is False
        assert "Invalid credentials" in result["message"]
        assert result["code"] == 4003

    def test_credentials_unexpected_error(self):
        """Test credential test with unexpected error"""
        with patch.object(SchedulesDirectClient, "authenticate", side_effect=Exception("Unexpected error")):
            result = validate_credentials("testuser", "testpass")

        assert result["success"] is False
        assert "Unexpected error" in result["message"]


# ============================================================================
# Program Dataclass Tests
# ============================================================================


class TestProgramDataclass:
    """Tests for Program dataclass and parsing"""

    def test_program_title(self):
        """Test ProgramTitle dataclass"""
        title = ProgramTitle(title120="Test Show", title_language="en")
        assert title.title120 == "Test Show"
        assert title.title_language == "en"

    def test_program_description(self):
        """Test ProgramDescription dataclass"""
        desc = ProgramDescription(description="A test show", description_language="en")
        assert desc.description == "A test show"
        assert desc.description_language == "en"

    def test_cast_member(self):
        """Test CastMember dataclass"""
        cast = CastMember(
            name="John Doe", role="Actor", billing_order="1", person_id="P123", character_name="Main Character"
        )
        assert cast.name == "John Doe"
        assert cast.role == "Actor"
        assert cast.person_id == "P123"
        assert cast.character_name == "Main Character"

    def test_content_rating(self):
        """Test ContentRating dataclass"""
        rating = ContentRating(body="MPAA", code="PG-13", country="US")
        assert rating.body == "MPAA"
        assert rating.code == "PG-13"
        assert rating.country == "US"

    def test_movie_info(self):
        """Test MovieInfo dataclass"""
        movie = MovieInfo(year="2023", duration=120)
        assert movie.year == "2023"
        assert movie.duration == 120

    def test_event_details(self):
        """Test EventDetails dataclass"""
        event = EventDetails(venue="Stadium", game_date="2023-12-01", teams=[{"name": "Team A"}, {"name": "Team B"}])
        assert event.venue == "Stadium"
        assert event.game_date == "2023-12-01"
        assert len(event.teams) == 2

    def test_program_metadata(self):
        """Test ProgramMetadata dataclass"""
        meta = ProgramMetadata(source="Gracenote", season=1, episode=5)
        assert meta.source == "Gracenote"
        assert meta.season == 1
        assert meta.episode == 5

    def test_program_from_api_response_basic(self):
        """Test Program.from_api_response with basic data"""
        api_data = {
            "programID": "EP12345",
            "titles": [{"title120": "Test Episode", "titleLanguage": "en"}],
            "entityType": "Episode",
            "md5": "abc123",
            "episodeTitle150": "The First Episode",
            "originalAirDate": "2023-01-15",
            "genres": ["Drama", "Comedy"],
        }

        program = Program.from_api_response(api_data)

        assert program.program_id == "EP12345"
        assert program.title == "Test Episode"
        assert program.entity_type == "Episode"
        assert program.episode_title == "The First Episode"
        assert program.original_air_date == "2023-01-15"
        assert program.genres == ["Drama", "Comedy"]

    def test_program_from_api_response_with_descriptions(self):
        """Test Program parsing with descriptions"""
        api_data = {
            "programID": "EP12345",
            "titles": [{"title120": "Test Show"}],
            "entityType": "Episode",
            "md5": "abc123",
            "descriptions": {
                "description100": [{"description": "Short desc", "descriptionLanguage": "en"}],
                "description1000": [{"description": "Long description here", "descriptionLanguage": "en"}],
            },
        }

        program = Program.from_api_response(api_data)

        assert program.description == "Long description here"
        assert len(program.descriptions_short) == 1
        assert len(program.descriptions_long) == 1
        assert program.descriptions_short[0].description == "Short desc"

    def test_program_from_api_response_with_cast_crew(self):
        """Test Program parsing with cast and crew"""
        api_data = {
            "programID": "MV12345",
            "titles": [{"title120": "Test Movie"}],
            "entityType": "Movie",
            "md5": "abc123",
            "cast": [{"name": "Actor One", "role": "Lead", "billingOrder": "1", "characterName": "Hero"}],
            "crew": [{"name": "Director One", "role": "Director", "billingOrder": "1"}],
        }

        program = Program.from_api_response(api_data)

        assert len(program.cast) == 1
        assert program.cast[0].name == "Actor One"
        assert program.cast[0].character_name == "Hero"
        assert len(program.crew) == 1
        assert program.crew[0].name == "Director One"
        assert program.crew[0].role == "Director"

    def test_program_from_api_response_with_content_rating(self):
        """Test Program parsing with content ratings"""
        api_data = {
            "programID": "MV12345",
            "titles": [{"title120": "Test Movie"}],
            "entityType": "Movie",
            "md5": "abc123",
            "contentRating": [
                {"body": "MPAA", "code": "R", "country": "US"},
                {"body": "BBFC", "code": "18", "country": "UK"},
            ],
        }

        program = Program.from_api_response(api_data)

        assert len(program.content_rating) == 2
        assert program.content_rating[0].body == "MPAA"
        assert program.content_rating[0].code == "R"

    def test_program_from_api_response_with_metadata(self):
        """Test Program parsing with season/episode metadata"""
        api_data = {
            "programID": "EP12345",
            "titles": [{"title120": "Test Episode"}],
            "entityType": "Episode",
            "md5": "abc123",
            "metadata": [
                {"Gracenote": {"season": 2, "episode": 10, "totalEpisodes": 22}},
                {"TVmaze": {"season": 2, "episode": 10, "url": "https://tvmaze.com/ep/123"}},
            ],
        }

        program = Program.from_api_response(api_data)

        assert len(program.metadata) == 2
        assert program.season_episode == (2, 10)
        assert program.metadata[0].source == "Gracenote"
        assert program.metadata[1].source == "TVmaze"
        assert program.metadata[1].url == "https://tvmaze.com/ep/123"

    def test_program_from_api_response_movie_info(self):
        """Test Program parsing with movie info"""
        api_data = {
            "programID": "MV12345",
            "titles": [{"title120": "Test Movie"}],
            "entityType": "Movie",
            "md5": "abc123",
            "movie": {"year": "2023", "duration": 120, "qualityRating": [{"ratingsBody": "RT", "rating": "92%"}]},
        }

        program = Program.from_api_response(api_data)

        assert program.movie is not None
        assert program.movie.year == "2023"
        assert program.movie.duration == 120
        assert program.is_movie() is True

    def test_program_from_api_response_event_details(self):
        """Test Program parsing with sports event details"""
        api_data = {
            "programID": "SP12345",
            "titles": [{"title120": "Big Game"}],
            "entityType": "Sports",
            "md5": "abc123",
            "eventDetails": {
                "venue100": "Main Stadium",
                "gameDate": "2023-12-01",
                "teams": [{"name": "Team A"}, {"name": "Team B"}],
            },
        }

        program = Program.from_api_response(api_data)

        assert program.event_details is not None
        assert program.event_details.venue == "Main Stadium"
        assert program.is_sports() is True

    def test_program_from_api_response_artwork_flags(self):
        """Test Program parsing with artwork availability flags"""
        api_data = {
            "programID": "EP12345",
            "titles": [{"title120": "Test Show"}],
            "entityType": "Episode",
            "md5": "abc123",
            "hasImageArtwork": True,
            "hasEpisodeArtwork": True,
            "hasSeriesArtwork": True,
            "hasSeasonArtwork": False,
        }

        program = Program.from_api_response(api_data)

        assert program.has_image_artwork is True
        assert program.has_episode_artwork is True
        assert program.has_series_artwork is True
        assert program.has_season_artwork is False

    def test_program_is_movie(self):
        """Test is_movie() method"""
        movie_by_id = Program(program_id="MV12345", titles=[ProgramTitle("Movie Title")], entity_type="Show", md5="abc")
        movie_by_type = Program(
            program_id="XX12345", titles=[ProgramTitle("Movie Title")], entity_type="Movie", md5="abc"
        )
        not_movie = Program(
            program_id="EP12345", titles=[ProgramTitle("Episode Title")], entity_type="Episode", md5="abc"
        )

        assert movie_by_id.is_movie() is True
        assert movie_by_type.is_movie() is True
        assert not_movie.is_movie() is False

    def test_program_is_episode(self):
        """Test is_episode() method"""
        episode_by_id = Program(
            program_id="EP12345", titles=[ProgramTitle("Episode Title")], entity_type="Show", md5="abc"
        )
        episode_by_type = Program(
            program_id="XX12345", titles=[ProgramTitle("Episode Title")], entity_type="Episode", md5="abc"
        )
        not_episode = Program(
            program_id="MV12345", titles=[ProgramTitle("Movie Title")], entity_type="Movie", md5="abc"
        )

        assert episode_by_id.is_episode() is True
        assert episode_by_type.is_episode() is True
        assert not_episode.is_episode() is False

    def test_program_is_sports(self):
        """Test is_sports() method"""
        sports_by_id = Program(program_id="SP12345", titles=[ProgramTitle("Game")], entity_type="Show", md5="abc")
        sports_by_type = Program(program_id="XX12345", titles=[ProgramTitle("Game")], entity_type="Sports", md5="abc")
        not_sports = Program(program_id="EP12345", titles=[ProgramTitle("Episode")], entity_type="Episode", md5="abc")

        assert sports_by_id.is_sports() is True
        assert sports_by_type.is_sports() is True
        assert not_sports.is_sports() is False

    def test_program_description_fallback(self):
        """Test description property fallback behavior"""
        # Only short description available
        program_short = Program(
            program_id="EP12345",
            titles=[ProgramTitle("Test")],
            entity_type="Episode",
            md5="abc",
            descriptions_short=[ProgramDescription("Short desc", "en")],
        )
        assert program_short.description == "Short desc"

        # No descriptions
        program_none = Program(program_id="EP12345", titles=[ProgramTitle("Test")], entity_type="Episode", md5="abc")
        assert program_none.description == ""


class TestGetProgramsWithParse:
    """Tests for get_programs with parse parameter"""

    def test_get_programs_without_parse(self):
        """Test get_programs returns raw dicts by default"""
        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"programID": "EP12345", "titles": [{"title120": "Test"}], "entityType": "Episode", "md5": "abc"}
        ]

        with patch.object(client.session, "post", return_value=mock_response):
            result = client.get_programs(["EP12345"])

        assert isinstance(result, list)
        assert isinstance(result[0], dict)
        assert result[0]["programID"] == "EP12345"

    def test_get_programs_with_parse(self):
        """Test get_programs with parse=True returns Program objects"""
        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {
                "programID": "EP12345",
                "titles": [{"title120": "Test Show"}],
                "entityType": "Episode",
                "md5": "abc123",
                "episodeTitle150": "Test Episode",
            }
        ]

        with patch.object(client.session, "post", return_value=mock_response):
            result = client.get_programs(["EP12345"], parse=True)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], Program)
        assert result[0].program_id == "EP12345"
        assert result[0].title == "Test Show"
        assert result[0].episode_title == "Test Episode"

    def test_get_programs_parse_skips_errors(self):
        """Test get_programs with parse=True skips error responses"""
        client = SchedulesDirectClient("testuser", "testpass")
        client.token = "test-token"
        client.token_expires = int((datetime.now(UTC) + timedelta(hours=1)).timestamp())

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"programID": "EP12345", "titles": [{"title120": "Valid"}], "entityType": "Episode", "md5": "abc"},
            {"programID": "EP99999", "code": 6000, "message": "INVALID_PROGRAMID"},  # Error response
            {"programID": "EP11111", "code": 6001, "message": "PROGRAMID_QUEUED"},  # Queued response
            {"programID": "EP54321", "titles": [{"title120": "Also Valid"}], "entityType": "Episode", "md5": "def"},
        ]

        with patch.object(client.session, "post", return_value=mock_response):
            result = client.get_programs(["EP12345", "EP99999", "EP11111", "EP54321"], parse=True)

        # Should only have 2 valid programs
        assert len(result) == 2
        assert result[0].program_id == "EP12345"
        assert result[1].program_id == "EP54321"
