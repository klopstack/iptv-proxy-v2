"""
Schedules Direct API Client

Schedules Direct (schedulesdirect.org) is a subscription service that provides
EPG data for North America, UK, and other regions. It's used by MythTV, Jellyfin,
Plex DVR, and other applications.

API Documentation:
- Main API: https://github.com/SchedulesDirect/JSON-Service/wiki/API-20141201
- Program Response: https://github.com/SchedulesDirect/JSON-Service/wiki/API-20141201-Program-Response

Rate Limiting:
- Trial users: 10 image downloads per day
- Subscribers: 5000 image downloads per day
- Error codes 5002/5003 indicate rate limit reached
- We implement request throttling to be a good API citizen
- Maximum 5000 items per request (programs, schedules, schedule MD5s)
- Maximum 500 items for artwork/description requests

Error Codes Reference:
- 0: OK
- 1004: TOKEN_MISSING
- 3000: SERVICE_OFFLINE
- 4001: ACCOUNT_EXPIRED
- 4002: INVALID_HASH
- 4003: INVALID_USER
- 4004: ACCOUNT_LOCKOUT
- 4006: TOKEN_EXPIRED
- 4008: ACCOUNT_INACTIVE
- 4009: TOO_MANY_LOGINS
- 5002/5003: MAX_IMAGE_DOWNLOADS
- 6000: INVALID_PROGRAMID (hard failure - don't retry)
- 6001: PROGRAMID_QUEUED (soft failure - retry)
- 7100: SCHEDULE_QUEUED (soft failure - retry)

Program ID Prefixes:
- EP: Episode
- SH: Show/Series
- MV: Movie
- SP: Sports event
"""
import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import requests

logger = logging.getLogger(__name__)

# Schedules Direct API endpoints
SD_API_BASE = "https://json.schedulesdirect.org/20141201"
SD_API_VERSION = "20141201"

# Client identification - SD requires useragent with version
CLIENT_NAME = "IPTV-Proxy"
CLIENT_VERSION = "2.0"
USER_AGENT = f"{CLIENT_NAME}/{CLIENT_VERSION}"

# Rate limiting settings
MIN_REQUEST_INTERVAL = 0.5  # Minimum seconds between requests
IMAGE_REQUEST_INTERVAL = 0.2  # Seconds between image requests
MAX_IMAGES_PER_SESSION = 100  # Stop after this many images to avoid hitting daily limits

# Request limits per API documentation
MAX_PROGRAMS_PER_REQUEST = 5000
MAX_SCHEDULES_PER_REQUEST = 5000
MAX_ARTWORK_PER_REQUEST = 500
MAX_DESCRIPTIONS_PER_REQUEST = 500

# SD Error Codes
SD_ERROR_CODES = {
    0: "OK",
    1001: "INVALID_JSON",
    1003: "USERAGENT_REQUIRED",
    1004: "TOKEN_MISSING",
    1005: "UNKNOWN_CLIENT",
    1006: "MAX_CHUNK_EXCEEDED",
    1007: "EMPTY_REQUEST",
    2055: "INVALID_PARAMETER:DEBUG",
    2100: "DUPLICATE_LINEUP",
    2101: "LINEUP_NOT_FOUND",
    2102: "UNKNOWN_LINEUP",
    2105: "INVALID_LINEUP",
    3000: "SERVICE_OFFLINE",
    4001: "ACCOUNT_EXPIRED",
    4002: "INVALID_HASH",
    4003: "INVALID_USER",
    4004: "ACCOUNT_LOCKOUT",
    4005: "JSON_ACCOUNT_ACCESS_DISABLED",
    4006: "TOKEN_EXPIRED",
    4007: "APPLICATION_DISABLED",
    4008: "ACCOUNT_INACTIVE",
    4009: "TOO_MANY_LOGINS",
    4010: "TOO_MANY_UNIQUE_IPS",
    5000: "IMAGE_NOT_FOUND",
    5002: "MAX_IMAGE_DOWNLOADS",
    5003: "MAX_IMAGE_DOWNLOADS_TRIAL",
    6000: "INVALID_PROGRAMID",
    6001: "PROGRAMID_QUEUED",
    6002: "FUTURE_PROGRAM",
    7020: "SCHEDULE_RANGE_EXCEEDED",
    7100: "SCHEDULE_QUEUED",
}

# Entity types from Schedules Direct
ENTITY_TYPES = [
    "Compilation",
    "Episode",
    "Highlights",
    "Miniseries",
    "Movie",
    "Music Video",
    "Off Air",
    "Paid Program",
    "Preview",
    "Series",
    "Short Film",
    "Show",
    "Special",
    "Sport Event",
    "Sport-Related Episode",
    "Sports",
    "TBA",
    "Team Event",
    "Trailer",
    "TV Movie",
]


# =============================================================================
# Data Classes for Program Response
# =============================================================================


@dataclass
class ProgramTitle:
    """Program title information."""

    title120: str
    title_language: Optional[str] = None


@dataclass
class ProgramDescription:
    """Program description with language."""

    description: str
    description_language: str


@dataclass
class CastMember:
    """Cast or crew member information."""

    name: str
    role: str
    billing_order: str
    person_id: Optional[str] = None
    name_id: Optional[str] = None
    character_name: Optional[str] = None


@dataclass
class ContentRating:
    """Content rating from a ratings body."""

    body: str
    code: str
    country: Optional[str] = None
    content_warning: Optional[List[str]] = None


@dataclass
class MovieInfo:
    """Movie-specific information (for MV programIDs)."""

    year: Optional[str] = None
    duration: Optional[int] = None
    quality_ratings: Optional[List[Dict[str, str]]] = None


@dataclass
class EventDetails:
    """Sports event details."""

    venue: Optional[str] = None
    game_date: Optional[str] = None
    teams: Optional[List[Dict[str, Any]]] = None


@dataclass
class ProgramMetadata:
    """Season/episode metadata from various sources."""

    source: str  # e.g., "Gracenote", "TVmaze"
    season: Optional[int] = None
    episode: Optional[int] = None
    total_episodes: Optional[int] = None
    total_seasons: Optional[int] = None
    url: Optional[str] = None  # TVmaze provides URLs


@dataclass
class Program:
    """
    Parsed Schedules Direct program data.

    This represents the full program response from the SD API.
    See: https://github.com/SchedulesDirect/JSON-Service/wiki/API-20141201-Program-Response
    """

    program_id: str
    titles: List[ProgramTitle]
    entity_type: str
    md5: str

    # Optional fields
    resource_id: Optional[str] = None
    episode_title: Optional[str] = None
    descriptions_short: Optional[List[ProgramDescription]] = None
    descriptions_long: Optional[List[ProgramDescription]] = None
    original_air_date: Optional[str] = None
    show_type: Optional[str] = None
    genres: Optional[List[str]] = None
    country: Optional[List[str]] = None
    cast: Optional[List[CastMember]] = None
    crew: Optional[List[CastMember]] = None
    content_rating: Optional[List[ContentRating]] = None
    content_advisory: Optional[List[str]] = None
    metadata: Optional[List[ProgramMetadata]] = None
    movie: Optional[MovieInfo] = None
    event_details: Optional[EventDetails] = None
    duration: Optional[int] = None
    official_url: Optional[str] = None
    keywords: Optional[Dict[str, List[str]]] = None
    recommendations: Optional[List[Dict[str, str]]] = None
    awards: Optional[List[Dict[str, Any]]] = None

    # Artwork availability flags
    has_image_artwork: bool = False
    has_episode_artwork: bool = False
    has_season_artwork: bool = False
    has_series_artwork: bool = False
    has_movie_artwork: bool = False
    has_sports_artwork: bool = False

    # Hash values
    hash: Optional[str] = None  # 32-char standard MD5 (future mandatory)

    @classmethod
    def from_api_response(cls, data: Dict[str, Any]) -> "Program":
        """
        Parse a program from the SD API response.

        Args:
            data: Raw API response dict for a single program

        Returns:
            Parsed Program object
        """
        # Parse titles
        titles = []
        for t in data.get("titles", []):
            titles.append(ProgramTitle(title120=t.get("title120", ""), title_language=t.get("titleLanguage")))

        # Parse descriptions
        descriptions = data.get("descriptions", {})
        desc_short = None
        desc_long = None
        if "description100" in descriptions:
            desc_short = [
                ProgramDescription(
                    description=d.get("description", ""), description_language=d.get("descriptionLanguage", "en")
                )
                for d in descriptions["description100"]
            ]
        if "description1000" in descriptions:
            desc_long = [
                ProgramDescription(
                    description=d.get("description", ""), description_language=d.get("descriptionLanguage", "en")
                )
                for d in descriptions["description1000"]
            ]

        # Parse cast
        cast = None
        if "cast" in data:
            cast = [
                CastMember(
                    name=c.get("name", ""),
                    role=c.get("role", ""),
                    billing_order=c.get("billingOrder", ""),
                    person_id=c.get("personId"),
                    name_id=c.get("nameId"),
                    character_name=c.get("characterName"),
                )
                for c in data["cast"]
            ]

        # Parse crew
        crew = None
        if "crew" in data:
            crew = [
                CastMember(
                    name=c.get("name", ""),
                    role=c.get("role", ""),
                    billing_order=c.get("billingOrder", ""),
                    person_id=c.get("personId"),
                    name_id=c.get("nameId"),
                )
                for c in data["crew"]
            ]

        # Parse content ratings
        content_rating = None
        if "contentRating" in data:
            content_rating = [
                ContentRating(
                    body=r.get("body", ""),
                    code=r.get("code", ""),
                    country=r.get("country"),
                    content_warning=r.get("contentWarning"),
                )
                for r in data["contentRating"]
            ]

        # Parse metadata (season/episode info)
        metadata = None
        if "metadata" in data:
            metadata = []
            for m in data["metadata"]:
                for source, info in m.items():
                    metadata.append(
                        ProgramMetadata(
                            source=source,
                            season=info.get("season"),
                            episode=info.get("episode"),
                            total_episodes=info.get("totalEpisodes"),
                            total_seasons=info.get("totalSeasons"),
                            url=info.get("url"),
                        )
                    )

        # Parse movie info
        movie = None
        if "movie" in data:
            m = data["movie"]
            movie = MovieInfo(year=m.get("year"), duration=m.get("duration"), quality_ratings=m.get("qualityRating"))

        # Parse event details (sports)
        event_details = None
        if "eventDetails" in data:
            e = data["eventDetails"]
            event_details = EventDetails(venue=e.get("venue100"), game_date=e.get("gameDate"), teams=e.get("teams"))

        return cls(
            program_id=data.get("programID", ""),
            titles=titles,
            entity_type=data.get("entityType", ""),
            md5=data.get("md5", ""),
            resource_id=data.get("resourceID"),
            episode_title=data.get("episodeTitle150"),
            descriptions_short=desc_short,
            descriptions_long=desc_long,
            original_air_date=data.get("originalAirDate"),
            show_type=data.get("showType"),
            genres=data.get("genres"),
            country=data.get("country"),
            cast=cast,
            crew=crew,
            content_rating=content_rating,
            content_advisory=data.get("contentAdvisory"),
            metadata=metadata,
            movie=movie,
            event_details=event_details,
            duration=data.get("duration"),
            official_url=data.get("officialURL"),
            keywords=data.get("keyWords"),
            recommendations=data.get("recommendations"),
            awards=data.get("awards"),
            has_image_artwork=data.get("hasImageArtwork", False),
            has_episode_artwork=data.get("hasEpisodeArtwork", False),
            has_season_artwork=data.get("hasSeasonArtwork", False),
            has_series_artwork=data.get("hasSeriesArtwork", False),
            has_movie_artwork=data.get("hasMovieArtwork", False),
            has_sports_artwork=data.get("hasSportsArtwork", False),
            hash=data.get("hash"),
        )

    @property
    def title(self) -> str:
        """Get the primary title."""
        return self.titles[0].title120 if self.titles else ""

    @property
    def description(self) -> str:
        """Get the longest available description."""
        if self.descriptions_long:
            return self.descriptions_long[0].description
        if self.descriptions_short:
            return self.descriptions_short[0].description
        return ""

    @property
    def season_episode(self) -> Optional[tuple]:
        """Get (season, episode) tuple from metadata if available."""
        if self.metadata:
            for m in self.metadata:
                if m.season is not None:
                    return (m.season, m.episode)
        return None

    def is_movie(self) -> bool:
        """Check if this is a movie."""
        return self.program_id.startswith("MV") or self.entity_type == "Movie"

    def is_episode(self) -> bool:
        """Check if this is an episode."""
        return self.program_id.startswith("EP") or self.entity_type == "Episode"

    def is_sports(self) -> bool:
        """Check if this is a sports program."""
        return self.program_id.startswith("SP") or self.entity_type in ("Sport Event", "Sports", "Team Event")


class SchedulesDirectError(Exception):
    """Base exception for Schedules Direct API errors"""

    def __init__(self, message: str, code: Optional[int] = None, response: Optional[Dict[str, Any]] = None):
        self.message = message
        self.code = code
        self.response = response
        super().__init__(message)


class RateLimitError(SchedulesDirectError):
    """Raised when SD rate limits are hit"""

    def __init__(self, message: str, code: int, retry_after: int = 86400):
        super().__init__(message, code)
        self.retry_after = retry_after  # Seconds until limit resets (default 24h)


class ServiceOfflineError(SchedulesDirectError):
    """Raised when SD service is offline (code 3000)"""

    pass


class AccountError(SchedulesDirectError):
    """Raised for account-related errors (expired, locked, etc.)"""

    pass


class RetryableError(SchedulesDirectError):
    """Raised when request should be retried (e.g., PROGRAMID_QUEUED)"""

    def __init__(self, message: str, code: int, retry_after: int = 60):
        super().__init__(message, code)
        self.retry_after = retry_after


class SchedulesDirectClient:
    """
    Client for interacting with the Schedules Direct API.

    Includes built-in rate limiting to avoid getting blocked.

    Usage:
        client = SchedulesDirectClient(username, password)
        client.authenticate()

        # Search for lineups
        lineups = client.search_lineups(country="USA", postalcode="10001")

        # Get channels in a lineup
        channels = client.get_lineup_channels("USA-NY12345-X")

        # Get program schedules
        schedules = client.get_schedules(station_ids=["12345", "67890"])
    """

    # Class-level rate limiting (shared across instances)
    _last_request_time: float = 0
    _last_image_request_time: float = 0
    _image_count_today: int = 0
    _image_count_reset: Optional[datetime] = None
    _rate_limit_lock = threading.Lock()

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.token_expires: Optional[int] = None  # Unix epoch time
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _throttle(self, is_image: bool = False) -> None:
        """
        Implement rate limiting between requests.

        Args:
            is_image: True if this is an image download request
        """
        with SchedulesDirectClient._rate_limit_lock:
            now = time.time()

            if is_image:
                # Check if we should reset the daily counter
                reset_time = SchedulesDirectClient._image_count_reset
                if reset_time is None or datetime.now() > reset_time:
                    SchedulesDirectClient._image_count_today = 0
                    SchedulesDirectClient._image_count_reset = datetime.now() + timedelta(hours=24)

                # Check if we've hit our self-imposed limit
                if SchedulesDirectClient._image_count_today >= MAX_IMAGES_PER_SESSION:
                    logger.warning(
                        f"Self-imposed image limit reached ({MAX_IMAGES_PER_SESSION}). "
                        "Skipping further image downloads this session."
                    )
                    raise RateLimitError(
                        f"Session image limit reached ({MAX_IMAGES_PER_SESSION})",
                        code=5999,  # Our internal code
                        retry_after=3600,
                    )

                # Throttle image requests more aggressively
                elapsed = now - SchedulesDirectClient._last_image_request_time
                if elapsed < IMAGE_REQUEST_INTERVAL:
                    time.sleep(IMAGE_REQUEST_INTERVAL - elapsed)

                SchedulesDirectClient._last_image_request_time = time.time()
                SchedulesDirectClient._image_count_today += 1
            else:
                # Regular API request throttling
                elapsed = now - SchedulesDirectClient._last_request_time
                if elapsed < MIN_REQUEST_INTERVAL:
                    time.sleep(MIN_REQUEST_INTERVAL - elapsed)

                SchedulesDirectClient._last_request_time = time.time()

    def _check_rate_limit_error(self, result: dict) -> None:
        """
        Check for rate limit error codes in the response.

        SD Error Codes:
        - 5002: Maximum image downloads reached (subscriber)
        - 5003: Maximum image downloads reached (trial user)
        """
        code = result.get("code", 0)

        if code == 5002:
            logger.error("Schedules Direct rate limit reached (subscriber limit)")
            raise RateLimitError(
                "Maximum image downloads reached. Counter resets every 24h.",
                code=5002,
                retry_after=86400,
            )
        elif code == 5003:
            logger.error("Schedules Direct rate limit reached (trial user limit)")
            raise RateLimitError(
                "Maximum image downloads for trial user reached. Counter resets every 24h.",
                code=5003,
                retry_after=86400,
            )

    def _check_error_response(self, result: Union[dict, list]) -> None:
        """
        Check for API error codes in the response.

        Args:
            result: API response (dict or list)

        Raises appropriate exceptions based on error code.
        """
        # List responses don't have top-level error codes
        if isinstance(result, list):
            return

        code = result.get("code", 0)
        if code == 0:
            return

        message = result.get("message", SD_ERROR_CODES.get(code, "Unknown error"))

        # Service offline
        if code == 3000:
            raise ServiceOfflineError(message, code, result)

        # Rate limits
        if code in (5002, 5003):
            raise RateLimitError(message, code, retry_after=86400)

        # Account errors
        if code in (4001, 4002, 4003, 4004, 4005, 4007, 4008, 4009, 4010):
            raise AccountError(message, code, result)

        # Token expired - needs re-auth
        if code == 4006:
            raise AccountError(message, code, result)

        # Retryable errors
        if code in (6001, 7100):
            retry_time = result.get("retryTime")
            retry_after = 60  # Default 60 seconds
            if retry_time:
                try:
                    retry_dt = datetime.fromisoformat(retry_time.replace("Z", "+00:00"))
                    retry_after = max(1, int((retry_dt - datetime.now()).total_seconds()))
                except (ValueError, TypeError):
                    pass
            raise RetryableError(message, code, retry_after)

        # Any other non-zero code with non-OK response is an error
        if result.get("response") != "OK":
            raise SchedulesDirectError(message, code, result)

    def _hash_password(self, password: str) -> str:
        """Hash password using SHA1 as required by SD API (lowercase hex)"""
        return hashlib.sha1(password.encode()).hexdigest().lower()

    def _is_token_valid(self) -> bool:
        """Check if current token is still valid (not expired)."""
        if not self.token or not self.token_expires:
            return False
        # Add 60 second buffer before expiration
        return time.time() < (self.token_expires - 60)

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Union[Dict[str, Any], List[Any]]] = None,
        authenticated: bool = True,
        is_image: bool = False,
        allow_redirects: bool = True,
    ) -> Any:
        """Make an API request to Schedules Direct with rate limiting.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (without base URL)
            data: Request body data
            authenticated: Whether to include auth token
            is_image: Whether this is an image download request
            allow_redirects: Whether to follow redirects

        Returns:
            API response (dict or list)
        """
        # Apply throttling
        self._throttle(is_image=is_image)

        url = f"{SD_API_BASE}/{endpoint}"

        headers = {}
        if authenticated:
            # Check token validity before request
            if not self._is_token_valid():
                self.authenticate()
            headers["token"] = self.token

        try:
            if method == "GET":
                response = self.session.get(url, headers=headers, timeout=30, allow_redirects=allow_redirects)
            elif method == "POST":
                response = self.session.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                response = self.session.put(url, headers=headers, json=data, timeout=30)
            elif method == "DELETE":
                response = self.session.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # Handle HTTP 429 (rate limit) if SD starts using it
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 3600))
                raise RateLimitError(
                    "Rate limited by Schedules Direct",
                    code=429,
                    retry_after=retry_after,
                )

            # Handle redirects for image downloads (return the redirect URL)
            if response.status_code == 303 and is_image:
                return {"redirect_url": response.headers.get("Location")}

            # Try to parse JSON response
            try:
                result = response.json()
            except ValueError:
                # Non-JSON response (might be image data or error page)
                if response.status_code == 200:
                    return {"data": response.content, "content_type": response.headers.get("Content-Type")}
                raise SchedulesDirectError(f"Invalid JSON response (HTTP {response.status_code})")

            # Check for token expiration and retry once
            if isinstance(result, dict) and result.get("code") == 4006:
                logger.info("Token expired, re-authenticating...")
                self.authenticate()
                headers["token"] = self.token
                # Retry the request
                if method == "GET":
                    response = self.session.get(url, headers=headers, timeout=30)
                elif method == "POST":
                    response = self.session.post(url, headers=headers, json=data, timeout=30)
                elif method == "PUT":
                    response = self.session.put(url, headers=headers, json=data, timeout=30)
                elif method == "DELETE":
                    response = self.session.delete(url, headers=headers, timeout=30)
                result = response.json()

            # Check for API-level errors
            self._check_error_response(result)

            return result

        except requests.RequestException as e:
            logger.error(f"Schedules Direct API request failed: {e}")
            raise SchedulesDirectError(f"API request failed: {e}")

    def authenticate(self, new_token: bool = False) -> Dict:
        """
        Authenticate with Schedules Direct and get a token.

        Args:
            new_token: If True, request a new token even if existing one is valid

        Returns:
            Dict with token info including:
            - token: The session token
            - tokenExpires: Unix epoch when token expires
            - datetime: Server datetime
        """
        data: Dict[str, Any] = {
            "username": self.username,
            "password": self._hash_password(self.password),
        }
        if new_token:
            data["newToken"] = True

        try:
            response = self.session.post(
                f"{SD_API_BASE}/token",
                json=data,
                timeout=30,
            )
            result = response.json()

            # Check for service offline
            if result.get("code") == 3000:
                raise ServiceOfflineError(result.get("message", "Service offline"), code=3000, response=result)

            if result.get("code", 0) != 0:
                error_msg = result.get("message", "Authentication failed")
                code = result.get("code")

                # Handle specific auth errors
                if code == 4004:
                    raise AccountError(
                        "Account locked out due to too many failed login attempts", code=code, response=result
                    )
                elif code in (4001, 4008):
                    raise AccountError(error_msg, code=code, response=result)

                raise SchedulesDirectError(error_msg, code, result)

            self.token = result.get("token")
            self.token_expires = result.get("tokenExpires")  # Unix epoch

            logger.info("Successfully authenticated with Schedules Direct")
            return result

        except requests.RequestException as e:
            logger.error(f"Schedules Direct authentication failed: {e}")
            raise SchedulesDirectError(f"Authentication failed: {e}")

    def get_status(self) -> Dict:
        """
        Get account status including lineup and system status.

        Returns:
            Dict with:
            - account: {expires, maxLineups, messages}
            - lineups: List of user's lineups with modified dates
            - lastDataUpdate: When data was last updated
            - systemStatus: List of system status messages
            - tokenExpires: Unix epoch when token expires
        """
        return self._make_request("GET", "status")

    def get_available_services(self) -> List[Dict]:
        """
        Get list of available services/countries.

        Returns:
            List of available service types with URIs for more info
        """
        return self._make_request("GET", "available", authenticated=False)

    def get_available_countries(self) -> Dict:
        """
        Get list of countries with available data.

        Returns:
            Dict grouped by region with country info including:
            - fullName, shortName (ISO 3166)
            - postalCodeExample, postalCode (regex pattern)
        """
        return self._make_request("GET", "available/countries", authenticated=False)

    def get_transmitters(self, country: str) -> Dict:
        """
        Get list of DVB-T transmitters for a country.

        Args:
            country: ISO 3166-1 alpha-3 country code (e.g., "GBR")

        Returns:
            Dict mapping transmitter name to lineup ID
        """
        return self._make_request("GET", f"transmitters/{country}", authenticated=False)

    def check_client_version(self, client_name: str) -> Dict:
        """
        Check if client is running latest version.

        Args:
            client_name: The registered client name

        Returns:
            Dict with client name and current version
        """
        return self._make_request("GET", f"version/{client_name}", authenticated=False)

    def preview_lineup(self, lineup_id: str) -> List[Dict]:
        """
        Preview a lineup before adding it to account.

        This allows seeing the channel mapping without consuming
        one of the limited lineup slots.

        Args:
            lineup_id: The lineup identifier (e.g., "USA-NY12345-X")

        Returns:
            List of channel previews with channel, name, callsign, affiliate
        """
        return self._make_request("GET", f"lineups/preview/{lineup_id}")

    def search_lineups(
        self,
        country: str = "USA",
        postalcode: Optional[str] = None,
        lineup_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        Search for available lineups (cable/satellite/OTA providers).

        Args:
            country: ISO 3166 country code (e.g., "USA", "CAN", "GBR")
            postalcode: Postal/ZIP code to search near
            lineup_id: Specific lineup ID to look up

        Returns:
            List of lineup dicts with uri, lineup, name, location, etc.
        """
        if lineup_id:
            # Direct lineup lookup
            result = self._make_request("GET", f"lineups/{lineup_id}")
            return [result] if result else []

        # Search by location
        if postalcode:
            endpoint = f"headends?country={country}&postalcode={postalcode}"
        else:
            endpoint = f"headends?country={country}"

        result = self._make_request("GET", endpoint)

        # Flatten the results - they come grouped by headend type
        lineups = []
        if isinstance(result, list):
            for headend in result:
                headend_type = headend.get("headend", "Unknown")
                headend_location = headend.get("location", "")

                for lineup in headend.get("lineups", []):
                    lineup["headend_type"] = headend_type
                    lineup["headend_location"] = headend_location
                    lineups.append(lineup)

        return lineups

    def add_lineup(self, lineup_id: str) -> Dict:
        """
        Add a lineup to your account.

        Args:
            lineup_id: The lineup identifier (e.g., "USA-NY12345-X")

        Returns:
            Dict with add result
        """
        return self._make_request("PUT", f"lineups/{lineup_id}")

    def remove_lineup(self, lineup_id: str) -> Dict:
        """
        Remove a lineup from your account.

        Args:
            lineup_id: The lineup identifier

        Returns:
            Dict with removal result
        """
        return self._make_request("DELETE", f"lineups/{lineup_id}")

    def get_lineups(self) -> List[Dict]:
        """
        Get lineups currently on your account.

        Returns:
            List of lineup dicts
        """
        result = self._make_request("GET", "status")
        return result.get("lineups", [])

    def get_lineup_map(self, lineup_id: str) -> Dict:
        """
        Get the channel map for a lineup.

        This returns station IDs and channel numbers for each channel
        in the lineup.

        Args:
            lineup_id: The lineup identifier

        Returns:
            Dict with 'map' containing list of channel mappings
            and 'stations' containing station details
        """
        return self._make_request("GET", f"lineups/{lineup_id}")

    def get_lineup_channels(self, lineup_id: str) -> List[Dict]:
        """
        Get detailed channel information for a lineup.

        Combines the lineup map with station metadata to provide
        a complete picture of each channel.

        Args:
            lineup_id: The lineup identifier

        Returns:
            List of channel dicts with:
                - stationID: Schedules Direct station ID
                - channel: Channel number
                - callsign: Station call sign (e.g., "ESPN")
                - name: Full station name
                - affiliate: Network affiliate
                - broadcastLanguage: Languages
                - logo: Logo URL info
        """
        lineup = self.get_lineup_map(lineup_id)

        # Build station lookup
        stations_by_id = {}
        for station in lineup.get("stations", []):
            stations_by_id[station["stationID"]] = station

        # Combine map with station data
        channels = []
        for mapping in lineup.get("map", []):
            station_id = mapping.get("stationID")
            station = stations_by_id.get(station_id, {})

            channel_info = {
                "stationID": station_id,
                "channel": mapping.get("channel"),
                "uhfVhf": mapping.get("uhfVhf"),  # For OTA
                "atscMajor": mapping.get("atscMajor"),
                "atscMinor": mapping.get("atscMinor"),
                "callsign": station.get("callsign"),
                "name": station.get("name"),
                "affiliate": station.get("affiliate"),
                "broadcastLanguage": station.get("broadcastLanguage", []),
                "descriptionLanguage": station.get("descriptionLanguage", []),
                "broadcaster": station.get("broadcaster", {}),
                "isCommercialFree": station.get("isCommercialFree", False),
            }

            # Add logo if available
            logo = station.get("logo")
            if logo:
                channel_info["logo"] = {
                    "url": logo.get("URL"),
                    "height": logo.get("height"),
                    "width": logo.get("width"),
                    "md5": logo.get("md5"),
                }

            channels.append(channel_info)

        return channels

    def get_schedules(
        self,
        station_ids: List[str],
        dates: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Get program schedules for stations.

        Args:
            station_ids: List of station IDs to get schedules for
            dates: List of dates in YYYY-MM-DD format (default: next 14 days)

        Returns:
            List of schedule dicts with programs
        """
        if not dates:
            # Default to next 14 days
            today = datetime.now()
            dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(14)]

        # Build request - each station with requested dates
        request_data = [{"stationID": sid, "date": dates} for sid in station_ids]

        return self._make_request("POST", "schedules", request_data)

    def get_programs(
        self,
        program_ids: List[str],
        parse: bool = False,
    ) -> Union[List[Dict], List[Program]]:
        """
        Get detailed program information.

        Note: Maximum 5000 program IDs per request.
        Some programs may return error codes instead of data:
        - Code 6001 (PROGRAMID_QUEUED): Retry later
        - Code 6000 (INVALID_PROGRAMID): Don't retry

        Args:
            program_ids: List of program IDs (from schedules)
            parse: If True, return List[Program] dataclass objects
                   If False (default), return raw List[Dict]

        Returns:
            List of program details (as dicts or Program objects)
        """
        if len(program_ids) > MAX_PROGRAMS_PER_REQUEST:
            logger.warning(f"Truncating program_ids from {len(program_ids)} " f"to {MAX_PROGRAMS_PER_REQUEST}")
            program_ids = program_ids[:MAX_PROGRAMS_PER_REQUEST]

        result = self._make_request("POST", "programs", program_ids)

        if not parse:
            return result

        # Parse into Program dataclass objects
        programs = []
        for item in result:
            # Skip error responses (code 6000, 6001)
            if "code" in item and item["code"] != 0:
                logger.warning(
                    f"Program {item.get('programID', 'unknown')}: "
                    f"code={item.get('code')}, message={item.get('message')}"
                )
                continue
            try:
                programs.append(Program.from_api_response(item))
            except Exception as e:
                logger.error(f"Failed to parse program {item.get('programID', 'unknown')}: {e}")
        return programs

    def get_schedule_md5s(
        self,
        station_ids: List[str],
        dates: Optional[List[str]] = None,
    ) -> Dict:
        """
        Get MD5 hashes for schedules to check if they've changed.

        This is useful for efficient updates - only download schedules
        where the MD5 has changed since last download.

        Args:
            station_ids: List of station IDs
            dates: Optional list of dates (YYYY-MM-DD format)

        Returns:
            Dict mapping stationID -> date -> {md5, lastModified, code, message}
        """
        request_data: List[Dict[str, Any]] = []
        for sid in station_ids:
            item: Dict[str, Any] = {"stationID": sid}
            if dates:
                item["date"] = dates
            request_data.append(item)

        return self._make_request("POST", "schedules/md5", request_data)

    def get_generic_description(self, program_ids: List[str]) -> Dict:
        """
        Get generic (series-level) descriptions for programs.

        Only available for "EP" (episode) type programs.
        Returns the parent series description.

        Note: Maximum 500 program IDs per request.

        Args:
            program_ids: List of program IDs (EP type)

        Returns:
            Dict mapping program ID -> {code, description100, description1000}
        """
        if len(program_ids) > 500:
            logger.warning(f"Truncating program_ids from {len(program_ids)} to 500")
            program_ids = program_ids[:500]
        return self._make_request("POST", "metadata/description/", program_ids)

    def get_program_cross_reference(self, program_ids: List[str]) -> Dict:
        """
        Get language cross-reference for programs.

        Returns programIDs for the same content in different languages.

        Args:
            program_ids: List of program IDs to look up

        Returns:
            Dict mapping programID -> list of cross-references with
            programID, md5, titleLanguage, descriptionLanguage
        """
        return self._make_request("POST", "xref", program_ids)

    def get_program_artwork(self, program_ids: List[str]) -> List[Dict]:
        """
        Get artwork/image index for programs (batch request).

        Note: Maximum 500 program IDs per request.
        Send full programID (not just left 10 characters) for episode-specific art.

        Args:
            program_ids: List of program IDs

        Returns:
            List of dicts with programID and data (list of image metadata)
        """
        if len(program_ids) > 500:
            logger.warning(f"Truncating program_ids from {len(program_ids)} to 500")
            program_ids = program_ids[:500]
        return self._make_request("POST", "metadata/programs/", program_ids)

    def get_program_artwork_single(self, program_id: str) -> List[Dict]:
        """
        Get artwork/image index for a single program.

        Args:
            program_id: The program ID

        Returns:
            List of image metadata dicts with:
            - uri: Image URI (may need to be fetched through /image/ endpoint)
            - width, height: Dimensions
            - ratio, aspect: Aspect ratio info
            - category: Image type (Iconic, Banner, etc.)
            - tier: Series, Season, or Episode level
            - lastUpdate: When the image was last updated
        """
        return self._make_request("GET", f"metadata/programs/{program_id}")

    def get_celebrity_images(self, person_id: str) -> List[Dict]:
        """
        Get headshot images for a celebrity/actor.

        The person_id can be found in program cast/crew data.

        Args:
            person_id: The person ID from cast/crew data

        Returns:
            List of image metadata dicts
        """
        return self._make_request("GET", f"metadata/celebrity/{person_id}")

    def get_image(self, uri: str) -> Dict:
        """
        Get an image by URI.

        Note: URIs are ephemeral - don't store them long-term.
        This will typically return a redirect to S3.

        Args:
            uri: The image URI from artwork index

        Returns:
            Dict with either:
            - redirect_url: URL to fetch image from S3
            - data: Raw image bytes (if no redirect)
        """
        return self._make_request("GET", f"image/{uri}", is_image=True, allow_redirects=False)

    def get_sports_status(self, program_id: str) -> Dict:
        """
        Check if a sporting event is still in progress.

        Useful for extending recordings for games running long.
        Supports: NFL, NHL, NBA, MLB

        Args:
            program_id: The sports program ID (SP prefix)

        Returns:
            Dict with:
            - isComplete: Boolean indicating if game is over
            - result: {homeTeam: {name, score}, awayTeam: {name, score}}

        Raises:
            RetryableError: If program status is queued (retry in 30 sec)
        """
        return self._make_request("GET", f"metadata/stillRunning/{program_id}")

    def delete_message(self, message_id: str) -> Dict:
        """
        Delete a system message from your account status.

        Args:
            message_id: The message ID to delete

        Returns:
            Dict with deletion result
        """
        return self._make_request("DELETE", f"messages/{message_id}")

    def is_ip_blocked(self) -> Dict:
        """
        Check if your IP is blocked by the load balancer.

        This endpoint can be called 100 times per 24 hours.
        Useful for debugging connectivity issues.

        Returns:
            Dict with code and blocked_on_load_balancer status
        """
        return self._make_request("GET", "ip_isblocked", authenticated=False)

    def search_stations(self, query: str) -> List[Dict]:
        """
        Search for stations by name or callsign.

        Note: This searches across ALL stations, not just those
        in your lineups.

        Args:
            query: Search term (station name or callsign)

        Returns:
            List of matching station dicts
        """
        # There's no direct search endpoint, but we can use
        # the transmitters endpoint for OTA or search lineups
        # This is a workaround - ideally you'd search your lineup channels
        logger.warning("Station search requires lineup context - use get_lineup_channels instead")
        return []

    def get_system_status(self) -> Dict:
        """
        Get Schedules Direct system status.

        Note: The /status endpoint requires authentication. We'll try to check
        if the API is reachable by hitting a public endpoint.

        Returns:
            Dict with system status info
        """
        try:
            # The /status endpoint requires authentication now
            # Instead, check if the API is reachable via a public endpoint
            response = requests.get(
                f"{SD_API_BASE}/available",
                headers={"User-Agent": USER_AGENT},
                timeout=10,
            )

            if response.status_code == 200:
                return {
                    "status": "online",
                    "message": "Schedules Direct API is reachable",
                    "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
            else:
                return {
                    "status": "degraded",
                    "message": f"API returned status code {response.status_code}",
                    "date": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
                }
        except requests.Timeout:
            return {"status": "offline", "message": "Connection timed out"}
        except requests.ConnectionError:
            return {"status": "offline", "message": "Could not connect to Schedules Direct"}
        except requests.RequestException as e:
            logger.error(f"Failed to get system status: {e}")
            return {"status": "error", "message": str(e)}
        except Exception as e:
            logger.error(f"Failed to parse system status: {e}")
            return {"status": "error", "message": str(e)}


def validate_credentials(username: str, password: str) -> Dict[str, Any]:
    """
    Validate Schedules Direct credentials without creating a persistent client.

    Args:
        username: SD username
        password: SD password (plain text)

    Returns:
        Dict with 'success', 'message', and optionally account info
    """
    try:
        client = SchedulesDirectClient(username, password)
        client.authenticate()

        # Get account status
        status = client.get_status()

        return {
            "success": True,
            "message": "Authentication successful",
            "account": {
                "max_lineups": status.get("account", {}).get("maxLineups", 0),
                "lineups": status.get("lineups", []),
                "expires": status.get("account", {}).get("expires"),
            },
        }

    except SchedulesDirectError as e:
        return {
            "success": False,
            "message": str(e),
            "code": e.code,
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"Unexpected error: {e}",
        }
