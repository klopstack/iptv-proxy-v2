"""
TheSportsDB Calendar Scraper Service

Scrapes the TheSportsDB calendar page to get event information without using the API.
This bypasses the API rate limit for bulk event discovery.

The calendar page at https://www.thesportsdb.com/browse_calendar/?s=&d=YYYY-MM-DD
contains a table of all events for a given date with:
- Time (UTC)
- League name and icon
- Event name (e.g., "Team A vs Team B")
- Link to event detail page (contains event ID)
"""

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)

# Calendar page URL template
CALENDAR_URL_TEMPLATE = "https://www.thesportsdb.com/browse_calendar/?s={sport}&d={date}"
SITE_LOGIN_URL = "https://www.thesportsdb.com/user_login.php"

# Cache TTL in seconds (12 hours - calendar data doesn't change frequently)
CACHE_TTL_SECONDS = 3600 * 12

# Persistent cache file path (relative to app data directory)
PERSISTENT_CACHE_FILENAME = "calendar_cache.json"

# Cache key version — bump when calendar fetch logic changes (invalidates stale entries)
CACHE_KEY_VERSION = "api-v1"

# Request timeout
REQUEST_TIMEOUT = 30

# Delay between requests to be nice to the server
REQUEST_DELAY_SECONDS = 0.5

# Sports to supplement via TheSportsDB API when HTML calendar is incomplete
API_SUPPLEMENT_SPORTS = (
    "Soccer",
    "Baseball",
    "American Football",
    "Basketball",
    "Ice Hockey",
)

# eventsDay is only useful near-term; skip far-future channel dates to avoid API noise
MAX_API_SUPPLEMENT_DAYS_AHEAD = 90
MAX_API_SUPPLEMENT_DAYS_BACK = 14


class CalendarEvent:
    """Represents an event parsed from the calendar page."""

    def __init__(
        self,
        event_id: str,
        event_name: str,
        league_name: str,
        time_utc: str,
        date: str,
        home_team: Optional[str] = None,
        away_team: Optional[str] = None,
        event_url: Optional[str] = None,
        league_icon_url: Optional[str] = None,
        country_flag_url: Optional[str] = None,
        timezone: Optional[str] = None,
    ):
        self.event_id = event_id
        self.event_name = event_name
        self.league_name = league_name
        self.time_utc = time_utc
        self.date = date
        self.home_team = home_team
        self.away_team = away_team
        self.event_url = event_url
        self.league_icon_url = league_icon_url
        self.country_flag_url = country_flag_url
        self.timezone = timezone
        # Cache the scheduled_at value to avoid recomputing and logging multiple times
        self._scheduled_at_cached: Optional[datetime] = None
        self._scheduled_at_computed: bool = False

    @property
    def scheduled_at(self) -> Optional[datetime]:
        """Parse the scheduled datetime from date and time_utc (cached)."""
        # Return cached value if already computed
        if self._scheduled_at_computed:
            return self._scheduled_at_cached

        # Mark as computed to avoid repeated warnings
        self._scheduled_at_computed = True

        try:
            # Validate inputs are not empty
            if not self.time_utc or not self.date:
                logger.warning(
                    f"Empty time or date for event {self.event_id}: " f"time_utc='{self.time_utc}', date='{self.date}'"
                )
                self._scheduled_at_cached = None
                return None

            # Parse time like "00:00" or "14:30"
            time_parts = self.time_utc.replace(" UTC", "").strip().split(":")
            if not time_parts[0]:  # Empty hour part
                logger.warning(f"Empty hour in time_utc for event {self.event_id}: '{self.time_utc}'")
                self._scheduled_at_cached = None
                return None

            hour = int(time_parts[0])
            minute = int(time_parts[1]) if len(time_parts) > 1 and time_parts[1] else 0

            # Parse date (YYYY-MM-DD)
            date_parts = self.date.split("-")
            if len(date_parts) != 3 or not all(date_parts):
                logger.warning(f"Invalid date format for event {self.event_id}: '{self.date}'")
                self._scheduled_at_cached = None
                return None

            year = int(date_parts[0])
            month = int(date_parts[1])
            day = int(date_parts[2])

            self._scheduled_at_cached = datetime(year, month, day, hour, minute, tzinfo=timezone.utc)
            return self._scheduled_at_cached
        except (ValueError, IndexError) as e:
            logger.warning(f"Failed to parse datetime for event {self.event_id}: {e}")
            self._scheduled_at_cached = None
            return None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "league_name": self.league_name,
            "time_utc": self.time_utc,
            "date": self.date,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "event_url": self.event_url,
            "league_icon_url": self.league_icon_url,
            "country_flag_url": self.country_flag_url,
            "scheduled_at": serialize_utc_iso(self.scheduled_at),
        }

    def __repr__(self) -> str:
        return f"CalendarEvent({self.event_id}: {self.event_name} @ {self.time_utc})"

    @classmethod
    def from_thesportsdb_api(cls, raw: Dict[str, Any], date: Optional[str] = None) -> Optional["CalendarEvent"]:
        """Build a CalendarEvent from TheSportsDB API event dict with canonical time parsing."""
        from services.datetime_utils import parse_thesportsdb_scheduled_at

        event_id = str(raw.get("idEvent") or "")
        if not event_id:
            return None

        event_name = raw.get("strEvent") or ""
        home_team = raw.get("strHomeTeam")
        away_team = raw.get("strAwayTeam")

        scheduled, event_tz = parse_thesportsdb_scheduled_at(raw)
        event_date = date or raw.get("dateEvent") or ""
        if scheduled:
            time_utc = scheduled.strftime("%H:%M")
        else:
            time_raw = raw.get("strTime") or ""
            time_utc = time_raw[:5] if len(time_raw) >= 5 else time_raw

        event = cls(
            event_id=event_id,
            event_name=event_name,
            league_name=raw.get("strLeague") or "",
            time_utc=time_utc,
            date=event_date,
            home_team=home_team,
            away_team=away_team,
            timezone=event_tz,
        )
        if scheduled:
            event._scheduled_at_cached = scheduled.replace(tzinfo=timezone.utc)
            event._scheduled_at_computed = True
        return event


class TheSportsDBCalendarScraper:
    """
    Scrapes TheSportsDB calendar pages to discover events without using the API.

    This service:
    1. Fetches calendar HTML pages for specific dates
    2. Parses event information including event IDs from links
    3. Caches results to avoid repeated requests
    4. Provides fuzzy matching for PPV channel names to events
    5. Persists cache to disk to survive restarts
    """

    def __init__(self, cache_ttl: int = CACHE_TTL_SECONDS, cache_dir: Optional[str] = None):
        """
        Initialize the calendar scraper.

        Args:
            cache_ttl: Cache time-to-live in seconds
            cache_dir: Directory for persistent cache file (default: data/)
        """
        self._cache: Dict[str, Tuple[List[CalendarEvent], float]] = {}
        self._cache_ttl = cache_ttl
        self._last_request_time = 0.0
        self._cache_hits = 0
        self._cache_misses = 0
        self._cache_disk_loads = 0

        # Set up persistent cache path
        if cache_dir is None:
            # Default to data/ directory relative to app root
            cache_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        self._cache_dir = cache_dir
        self._cache_file = os.path.join(cache_dir, PERSISTENT_CACHE_FILENAME)

        # Load persistent cache on startup
        self._load_persistent_cache()

        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (compatible; IPTV-Proxy/1.0; +https://github.com)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )

        self._authenticated_user: Optional[str] = None
        self._login_verified = False

    def _load_site_credentials(self) -> Tuple[Optional[str], Optional[str]]:
        """Load TheSportsDB website credentials from application settings."""
        try:
            from models import Settings

            username = (Settings.get("ppv_thesportsdb_site_username", "") or "").strip()
            password = Settings.get("ppv_thesportsdb_site_password", "") or ""
            if username and password:
                return username, password
        except Exception as e:
            logger.debug(f"Could not load TheSportsDB site credentials: {e}")
        return None, None

    def _get_auth_cache_suffix(self) -> str:
        """Separate cache entries for anonymous vs authenticated calendar fetches."""
        username, password = self._load_site_credentials()
        if username and password:
            return f":auth:{username}"
        return ":anon"

    def _ensure_site_login(self) -> None:
        """Authenticate the HTTP session when site credentials are configured."""
        username, password = self._load_site_credentials()
        if not username or not password:
            if self._authenticated_user is not None:
                self._session.cookies.clear()
            self._authenticated_user = None
            self._login_verified = False
            return

        if self._login_verified and self._authenticated_user == username:
            return

        self._session.cookies.clear()
        self._rate_limit()

        try:
            response = self._session.post(
                SITE_LOGIN_URL,
                data={
                    "username": username,
                    "password": password,
                    "rememberme": "Yes",
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
            response.raise_for_status()
        except Exception as e:
            logger.warning(f"TheSportsDB site login request failed for {username}: {e}")
            self._authenticated_user = None
            self._login_verified = False
            return

        if self._is_login_page_with_error(response.text):
            logger.warning(f"TheSportsDB site login failed for user {username}")
            self._authenticated_user = None
            self._login_verified = False
            return

        self._authenticated_user = username
        self._login_verified = True
        logger.info(f"TheSportsDB site login successful for {username}")

    @staticmethod
    def _is_login_page_with_error(html: str) -> bool:
        """Return True when the login form is shown with a validation error."""
        return "<h2>Login</h2>" in html and "has-error" in html

    def _rate_limit(self) -> None:
        """Enforce rate limiting between requests."""
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < REQUEST_DELAY_SECONDS:
            time.sleep(REQUEST_DELAY_SECONDS - elapsed)
        self._last_request_time = time.time()

    def _load_persistent_cache(self) -> None:
        """Load cache from disk if available."""
        if not os.path.exists(self._cache_file):
            logger.debug(f"No persistent cache file found at {self._cache_file}")
            return

        try:
            with open(self._cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            loaded_count = 0
            now = time.time()

            for cache_key, entry in data.items():
                if not cache_key.startswith(f"{CACHE_KEY_VERSION}:"):
                    continue
                timestamp = entry.get("timestamp", 0)
                events_data = entry.get("events", [])
                # Skip expired entries and poisoned empty caches (parser failures)
                if (now - timestamp) >= self._cache_ttl or not events_data:
                    continue
                events = [
                    CalendarEvent(
                        event_id=ev["event_id"],
                        event_name=ev["event_name"],
                        league_name=ev["league_name"],
                        time_utc=ev["time_utc"],
                        date=ev["date"],
                        home_team=ev.get("home_team"),
                        away_team=ev.get("away_team"),
                        event_url=ev.get("event_url"),
                        league_icon_url=ev.get("league_icon_url"),
                        country_flag_url=ev.get("country_flag_url"),
                    )
                    for ev in events_data
                ]
                self._cache[cache_key] = (events, timestamp)
                loaded_count += 1

            if loaded_count > 0:
                self._cache_disk_loads = loaded_count
                logger.info(
                    f"Loaded {loaded_count} date entries from persistent cache "
                    f"({sum(len(e) for e, _ in self._cache.values())} total events)"
                )
        except (json.JSONDecodeError, IOError, KeyError) as e:
            logger.warning(f"Failed to load persistent cache: {e}")

    def _save_persistent_cache(self) -> None:
        """Save current cache to disk."""
        try:
            # Ensure cache directory exists
            os.makedirs(self._cache_dir, exist_ok=True)

            # Convert cache to JSON-serializable format
            data = {}
            now = time.time()

            for cache_key, (events, timestamp) in self._cache.items():
                # Only save non-empty, non-expired entries (never persist parser-failure caches)
                if events and (now - timestamp) < self._cache_ttl:
                    data[cache_key] = {
                        "timestamp": timestamp,
                        "events": [ev.to_dict() for ev in events],
                    }

            with open(self._cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            total_events = 0
            for entry in data.values():
                events_list = entry.get("events", [])
                if isinstance(events_list, list):
                    total_events += len(events_list)
            logger.debug(f"Saved {len(data)} date entries to persistent cache " f"({total_events} total events)")
        except (IOError, TypeError) as e:
            logger.warning(f"Failed to save persistent cache: {e}")

    def _get_cache_key(self, date: str, sport: str = "") -> str:
        """Generate cache key for a date/sport combination."""
        return f"{CACHE_KEY_VERSION}:{date}:{sport}{self._get_auth_cache_suffix()}"

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached data is still valid."""
        if cache_key not in self._cache:
            return False
        events, timestamp = self._cache[cache_key]
        if not events:
            return False
        return (time.time() - timestamp) < self._cache_ttl

    def get_events_for_date(self, date: str, sport: str = "", force_refresh: bool = False) -> List[CalendarEvent]:
        """
        Get all events for a specific date from the calendar page.

        Args:
            date: Date in YYYY-MM-DD format
            sport: Optional sport filter (empty string for all sports)
            force_refresh: If True, bypass cache

        Returns:
            List of CalendarEvent objects for the date
        """
        cache_key = self._get_cache_key(date, sport)

        # Check cache first
        if not force_refresh and self._is_cache_valid(cache_key):
            events, _ = self._cache[cache_key]
            self._cache_hits += 1
            logger.debug(f"Cache hit for {cache_key}: {len(events)} events")
            return events

        # Fetch from web and supplement with API for major sports
        self._cache_misses += 1
        try:
            html_events = self._fetch_calendar_page(date, sport)
            api_events = self._fetch_api_events_for_date(date, sport)
            events = self._merge_calendar_events(html_events, api_events)
            if events:
                self._cache[cache_key] = (events, time.time())
                self._save_persistent_cache()
            else:
                self._cache.pop(cache_key, None)
                logger.warning(
                    f"No events from HTML or API for {date} (sport={sport or 'all'}) — " "not caching empty result"
                )
            logger.info(
                f"Fetched {len(events)} events for {date} (sport={sport or 'all'}, "
                f"html={len(html_events)}, api={len(api_events)})"
            )
            return events
        except Exception as e:
            logger.error(f"Failed to fetch calendar for {date}: {e}")
            # Return cached data if available, even if expired
            if cache_key in self._cache:
                events, _ = self._cache[cache_key]
                logger.warning(f"Using stale cache for {date} due to fetch error")
                return events
            return []

    def _before_calendar_fetch(self) -> None:
        """Rate-limit and authenticate before each calendar HTTP attempt."""
        self._rate_limit()
        self._ensure_site_login()

    def _fetch_calendar_page(self, date: str, sport: str = "") -> List[CalendarEvent]:
        """
        Fetch and parse a calendar page.

        Args:
            date: Date in YYYY-MM-DD format
            sport: Optional sport filter

        Returns:
            List of CalendarEvent objects
        """
        url = CALENDAR_URL_TEMPLATE.format(sport=sport, date=date)
        logger.debug(f"Fetching calendar: {url}")

        from services.thesportsdb_retry import fetch_url_with_retry, is_retryable_html_page

        response = fetch_url_with_retry(
            self._session,
            url,
            timeout=REQUEST_TIMEOUT,
            before_attempt=self._before_calendar_fetch,
            validate_response=lambda resp: is_retryable_html_page(resp.text),
        )

        return self._parse_calendar_html(response.text, date)

    def _fetch_api_events_for_date(self, date: str, sport: str = "") -> List[CalendarEvent]:
        """
        Fetch events from TheSportsDB API to supplement incomplete HTML calendar pages.

        The browse_calendar HTML page often omits major US sports (MLB, NFL, etc.)
        while eventsDay API returns them reliably.
        """
        if not self._is_date_in_api_supplement_window(date):
            return []

        from thesportsdb import events as tsdb_events

        from services.thesportsdb_retry import call_thesportsdb_api
        from services.thesportsdb_service import parse_thesportsdb_api_response

        sports_to_fetch: List[str]
        if sport:
            sports_to_fetch = [sport]
        else:
            sports_to_fetch = list(API_SUPPLEMENT_SPORTS)

        api_events: List[CalendarEvent] = []
        for sport_name in sports_to_fetch:
            try:
                result = call_thesportsdb_api(
                    tsdb_events.eventsDay,
                    date,
                    s=sport_name,
                    before_attempt=self._rate_limit,
                )
                payload = parse_thesportsdb_api_response(result)
                if payload is None:
                    logger.debug(
                        f"API eventsDay returned non-JSON for {date} sport={sport_name} "
                        f"after retries (type={type(result).__name__})"
                    )
                    continue

                events_list = payload.get("events") or []
                if not isinstance(events_list, list):
                    logger.debug(f"API eventsDay unexpected events payload for {date} sport={sport_name}")
                    continue

                for raw in events_list:
                    if not isinstance(raw, dict):
                        continue
                    event = self._api_event_to_calendar_event(raw, date)
                    if event:
                        api_events.append(event)
            except Exception as e:
                logger.warning(f"API eventsDay failed for {date} sport={sport_name}: {e}")

        return api_events

    def _is_date_in_api_supplement_window(self, date: str) -> bool:
        """Return False for dates too far from today to query via eventsDay."""
        try:
            target = datetime.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return False

        today = datetime.now(timezone.utc).date()
        delta = (target - today).days
        return -MAX_API_SUPPLEMENT_DAYS_BACK <= delta <= MAX_API_SUPPLEMENT_DAYS_AHEAD

    def _api_event_to_calendar_event(self, raw: Dict[str, Any], date: str) -> Optional[CalendarEvent]:
        """Convert a TheSportsDB API event dict to CalendarEvent."""
        return CalendarEvent.from_thesportsdb_api(raw, date=date)

    def _merge_calendar_events(
        self,
        html_events: List[CalendarEvent],
        api_events: List[CalendarEvent],
    ) -> List[CalendarEvent]:
        """Merge HTML and API events, deduplicating by event_id."""
        merged: Dict[str, CalendarEvent] = {event.event_id: event for event in html_events}
        for event in api_events:
            merged.setdefault(event.event_id, event)
        return list(merged.values())

    def _parse_calendar_html(self, html: str, date: str) -> List[CalendarEvent]:
        """
        Parse calendar HTML to extract events.

        The HTML structure has table rows in one of two layouts:

        Legacy (5+ columns):
        <tr>
            <td>00:00 UTC </td>
            <td width='20'> </td>
            <td><img src='league_icon'/> League Name</td>
            <td width='20'> </td>
            <td><img src='flag'/> <a href='/event/123456-event-slug'/>Event Name</a></td>
        </tr>

        Current (4 columns, since 2025/2026):
        <tr>
            <td>00:00</td>
            <td>Soccer</td>
            <td>FA Cup</td>
            <td><a href='/event/123456-event-slug'><span>Team A vs Team B</span></a></td>
        </tr>

        Args:
            html: Raw HTML content
            date: Date string for the events

        Returns:
            List of CalendarEvent objects
        """
        events = []
        soup = BeautifulSoup(html, "html.parser")

        # Find all table rows in the main content
        rows = soup.find_all("tr")

        for row in rows:
            try:
                event = self._parse_event_row(row, date)
                if event:
                    events.append(event)
            except Exception as e:
                logger.debug(f"Failed to parse row: {e}")
                continue

        return events

    def _parse_time_from_cell(self, time_text: str) -> Optional[str]:
        """Parse HH:MM from a calendar time cell (with or without UTC suffix)."""
        cleaned = re.sub(r"\s*UTC\s*", "", time_text.strip(), flags=re.IGNORECASE).strip()
        if not cleaned:
            return "00:00"
        if re.match(r"^\d{1,2}:\d{2}", cleaned):
            return cleaned
        return None

    def _extract_event_from_cells(
        self,
        league_cell,
        event_cell,
        time_utc: str,
        date: str,
    ) -> Optional[CalendarEvent]:
        """Build a CalendarEvent from league and event table cells."""
        league_img = league_cell.find("img")
        league_icon_url = league_img.get("src") if league_img else None
        league_name = league_cell.get_text(strip=True)

        flag_img = event_cell.find("img")
        country_flag_url = flag_img.get("src") if flag_img else None

        event_link = event_cell.find("a", href=re.compile(r"/event/\d+"))
        if not event_link:
            return None

        event_href = event_link.get("href", "")
        event_name = event_link.get_text(strip=True)
        if not event_name:
            event_name = event_cell.get_text(strip=True)

        event_id_match = re.search(r"/event/(\d+)", event_href)
        if not event_id_match:
            return None

        event_id = event_id_match.group(1)
        event_url = urljoin("https://www.thesportsdb.com", event_href)
        home_team, away_team = self._parse_teams_from_event_name(event_name)

        return CalendarEvent(
            event_id=event_id,
            event_name=event_name,
            league_name=league_name,
            time_utc=time_utc,
            date=date,
            home_team=home_team,
            away_team=away_team,
            event_url=event_url,
            league_icon_url=league_icon_url,
            country_flag_url=country_flag_url,
        )

    def _parse_event_row(self, row, date: str) -> Optional[CalendarEvent]:
        """
        Parse a single table row to extract event information.

        Supports legacy 5-column and current 4-column TheSportsDB layouts.

        Args:
            row: BeautifulSoup Tag for the <tr> element
            date: Date string for the event

        Returns:
            CalendarEvent or None if row doesn't contain a valid event
        """
        cells = row.find_all("td")
        if len(cells) < 4:
            return None

        # Legacy layout: time | spacer | league | spacer | event
        if len(cells) >= 5 and "UTC" in cells[0].get_text():
            time_utc = self._parse_time_from_cell(cells[0].get_text(strip=True))
            if not time_utc:
                return None
            return self._extract_event_from_cells(cells[2], cells[4], time_utc, date)

        # Current layout: time | sport | league | event
        time_utc = self._parse_time_from_cell(cells[0].get_text(strip=True))
        if not time_utc:
            return None

        event_cell = cells[3]
        if not event_cell.find("a", href=re.compile(r"/event/\d+")):
            return None

        return self._extract_event_from_cells(cells[2], event_cell, time_utc, date)

    def _parse_teams_from_event_name(self, event_name: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract team names from event name like "Team A vs Team B".

        Args:
            event_name: Event name string

        Returns:
            Tuple of (home_team, away_team) or (None, None) if not parseable
        """
        # Common separators: "vs", "vs.", "at", "@", "-"
        patterns = [
            r"(.+?)\s+vs\.?\s+(.+)",
            r"(.+?)\s+v\.?\s+(.+)",
            r"(.+?)\s+at\s+(.+)",
            r"(.+?)\s+@\s+(.+)",
            r"(.+?)\s+x\s+(.+)",
        ]

        for pattern in patterns:
            match = re.match(pattern, event_name, re.IGNORECASE)
            if match:
                return match.group(1).strip(), match.group(2).strip()

        return None, None

    def get_events_for_date_range(
        self, start_date: str, end_date: str, sport: str = ""
    ) -> Dict[str, List[CalendarEvent]]:
        """
        Get events for a range of dates.

        Args:
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            sport: Optional sport filter

        Returns:
            Dict mapping date strings to lists of events
        """
        results = {}

        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")

        current = start
        while current <= end:
            date_str = current.strftime("%Y-%m-%d")
            results[date_str] = self.get_events_for_date(date_str, sport)
            current += timedelta(days=1)

        return results

    def find_matching_events(
        self,
        date: str,
        competitors: Optional[Tuple[str, str]] = None,
        event_name_keywords: Optional[List[str]] = None,
        league_name: Optional[str] = None,
        time_utc: Optional[str] = None,
        time_tolerance_minutes: int = 120,
    ) -> List[Tuple[CalendarEvent, float]]:
        """
        Find events matching given criteria with confidence scores.

        Args:
            date: Date in YYYY-MM-DD format
            competitors: Tuple of (team1, team2) to match
            event_name_keywords: Keywords that should appear in event name
            league_name: League name to match
            time_utc: Expected time in HH:MM format
            time_tolerance_minutes: How many minutes difference to allow for time matching

        Returns:
            List of (CalendarEvent, confidence_score) tuples, sorted by confidence descending
        """
        events = self.get_events_for_date(date)
        matches = []

        for event in events:
            confidence = self._calculate_match_confidence(
                event,
                competitors=competitors,
                event_name_keywords=event_name_keywords,
                league_name=league_name,
                time_utc=time_utc,
                time_tolerance_minutes=time_tolerance_minutes,
            )

            if confidence > 0:
                matches.append((event, confidence))

        # Sort by confidence descending
        matches.sort(key=lambda x: x[1], reverse=True)
        return matches

    def _calculate_match_confidence(
        self,
        event: CalendarEvent,
        competitors: Optional[Tuple[str, str]] = None,
        event_name_keywords: Optional[List[str]] = None,
        league_name: Optional[str] = None,
        time_utc: Optional[str] = None,
        time_tolerance_minutes: int = 120,
    ) -> float:
        """
        Calculate confidence score for an event match.

        Scoring:
        - Competitor match (both teams): +0.6
        - Competitor match (one team): +0.3
        - Keyword match: +0.1 per keyword
        - League match: +0.1
        - Time match (within tolerance): +0.1
        - Exact time match: +0.1 bonus

        Returns:
            Confidence score between 0.0 and 1.0
        """
        score = 0.0
        event_name_lower = event.event_name.lower()

        # Competitor matching
        if competitors:
            comp1_lower = competitors[0].lower()
            comp2_lower = competitors[1].lower()

            comp1_match = self._fuzzy_team_match(comp1_lower, event)
            comp2_match = self._fuzzy_team_match(comp2_lower, event)

            if comp1_match and comp2_match:
                score += 0.6  # Both teams match
            elif comp1_match or comp2_match:
                score += 0.3  # One team matches

        # Keyword matching
        if event_name_keywords:
            for keyword in event_name_keywords:
                if keyword.lower() in event_name_lower:
                    score += 0.1

        # League matching
        if league_name and league_name.lower() in event.league_name.lower():
            score += 0.1

        # Time matching
        if time_utc:
            time_diff = self._time_difference_minutes(time_utc, event.time_utc)
            if time_diff is not None:
                if time_diff == 0:
                    score += 0.2  # Exact match
                elif time_diff <= time_tolerance_minutes:
                    score += 0.1  # Within tolerance

        return min(score, 1.0)

    def _fuzzy_team_match(self, team_name: str, event: CalendarEvent) -> bool:
        """
        Check if team name matches event teams using fuzzy matching.

        Args:
            team_name: Team name to search for (lowercase)
            event: CalendarEvent to check

        Returns:
            True if team name matches home or away team
        """
        team_name = team_name.lower().strip()

        # Check direct matches against parsed team names
        if event.home_team and team_name in event.home_team.lower():
            return True
        if event.away_team and team_name in event.away_team.lower():
            return True

        # Check against full event name
        if team_name in event.event_name.lower():
            return True

        # Try partial matching (e.g., "Arsenal" should match "Arsenal FC")
        team_words = team_name.split()
        event_name_lower = event.event_name.lower()

        # If all words in team name appear in event name, consider it a match
        if all(word in event_name_lower for word in team_words):
            return True

        return False

    def _time_difference_minutes(self, time1: str, time2: str) -> Optional[int]:
        """
        Calculate difference in minutes between two time strings.

        Args:
            time1: Time in HH:MM format
            time2: Time in HH:MM format

        Returns:
            Absolute difference in minutes, or None if parsing fails
        """
        try:
            # Parse time1
            parts1 = time1.strip().split(":")
            h1, m1 = int(parts1[0]), int(parts1[1]) if len(parts1) > 1 else 0

            # Parse time2
            parts2 = time2.strip().split(":")
            h2, m2 = int(parts2[0]), int(parts2[1]) if len(parts2) > 1 else 0

            minutes1 = h1 * 60 + m1
            minutes2 = h2 * 60 + m2

            return abs(minutes1 - minutes2)
        except (ValueError, IndexError):
            return None

    def clear_cache(self, include_persistent: bool = True) -> None:
        """
        Clear all cached calendar data.

        Args:
            include_persistent: If True, also delete the persistent cache file
        """
        self._cache.clear()
        if include_persistent and os.path.exists(self._cache_file):
            try:
                os.remove(self._cache_file)
                logger.info("Calendar cache cleared (including persistent cache)")
            except IOError as e:
                logger.warning(f"Failed to delete persistent cache: {e}")
        else:
            logger.info("Calendar cache cleared (memory only)")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = time.time()
        valid_entries = sum(1 for _, (_, ts) in self._cache.items() if (now - ts) < self._cache_ttl)
        total = len(self._cache)
        total_events = sum(len(events) for events, _ in self._cache.values())

        # Calculate hit rate from internal tracking
        total_requests = self._cache_hits + self._cache_misses
        hit_rate = (self._cache_hits / total_requests) if total_requests > 0 else 0.0

        # Check persistent cache file
        persistent_size = 0
        if os.path.exists(self._cache_file):
            persistent_size = os.path.getsize(self._cache_file)

        return {
            "size": valid_entries,
            "total_entries": total,
            "valid_entries": valid_entries,
            "total_events": total_events,
            "hit_rate": hit_rate,
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "disk_loads": self._cache_disk_loads,
            "cache_ttl_seconds": self._cache_ttl,
            "persistent_cache_file": self._cache_file,
            "persistent_cache_size_bytes": persistent_size,
        }


# Global singleton instance
_calendar_scraper: Optional[TheSportsDBCalendarScraper] = None


def reset_calendar_scraper() -> None:
    """Reset the global calendar scraper (e.g. after credential changes)."""
    global _calendar_scraper
    _calendar_scraper = None


def get_calendar_scraper() -> TheSportsDBCalendarScraper:
    """Get or create the global calendar scraper instance."""
    global _calendar_scraper
    if _calendar_scraper is None:
        _calendar_scraper = TheSportsDBCalendarScraper()
    return _calendar_scraper
