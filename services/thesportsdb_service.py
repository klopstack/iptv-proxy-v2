"""
TheSportsDB Integration Service

Provides integration with TheSportsDB API for sports event data retrieval,
supporting event lookup, league information, and event matching for PPV channels.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from thesportsdb import events, leagues, teams

logger = logging.getLogger(__name__)

# Common league IDs mapping (can be expanded)
LEAGUE_ID_MAP = {
    # Premier League (various leagues)
    "English Premier League": "133602",
    "English League 1": "4396",
    "English League 2": "4397",
    "Championship": "4399",
    # La Liga
    "Spanish La Liga": "775",
    "Spanish Segunda División": "776",
    # Serie A
    "Italian Serie A": "783",
    # Bundesliga
    "German Bundesliga": "780",
    "German 2. Bundesliga": "781",
    # Ligue 1
    "French Ligue 1": "772",
    # US Sports
    "NFL": "133602",  # Placeholder - use team-based lookups
    "NBA": "133602",  # Placeholder
    "MLB": "133602",  # Placeholder
    "NHL": "133602",  # Placeholder
}


class TheSportsDBService:
    """Service for interacting with TheSportsDB API"""

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 3600  # 1 hour

    def get_next_league_events(self, league_id: str, max_events: int = 50) -> List[Dict[str, Any]]:
        """
        Get upcoming events for a league.

        Args:
            league_id: TheSportsDB league ID (string)
            max_events: Maximum number of events to return

        Returns:
            List of event dicts with keys:
            - idEvent: Unique event ID
            - strEvent: Event name (e.g., "Team A vs Team B")
            - dateEvent: Date in YYYY-MM-DD format
            - strTime: Time in HH:MM:SS format
            - strTimestamp: ISO 8601 timestamp
            - strHomeTeam: Home team name
            - strAwayTeam: Away team name
            - strLeague: League name
            - strSport: Sport type (e.g., "Soccer")
            - strStatus: Event status ("Not Started", "In Progress", etc.)
            - strPostponed: "yes" or "no"
        """
        try:
            result = events.nextLeagueEvents(league_id)

            if not result or not isinstance(result, dict):
                logger.warning(f"Invalid response from nextLeagueEvents: {type(result)}")
                return []

            events_list = result.get("events", [])
            if not events_list:
                logger.debug(f"No events found for league {league_id}")
                return []

            # Filter out postponed events and return limited results
            active_events = [e for e in events_list if e.get("strPostponed") != "yes"][:max_events]

            logger.debug(f"Retrieved {len(active_events)} active events for league {league_id}")
            return active_events

        except Exception as e:
            logger.error(f"Error fetching league events for {league_id}: {e}")
            return []

    def get_league_season_events(self, league_id: str, season: str, max_events: int = 100) -> List[Dict[str, Any]]:
        """
        Get all events for a specific league season.

        Args:
            league_id: TheSportsDB league ID (string)
            season: Season string (e.g., "2025-2026")
            max_events: Maximum number of events to return

        Returns:
            List of event dicts (see get_next_league_events for format)
        """
        try:
            result = events.leagueSeasonEvents(league_id, season)

            if not result or not isinstance(result, dict):
                logger.warning(f"Invalid response from leagueSeasonEvents: {type(result)}")
                return []

            events_list = result.get("results", [])
            if not events_list:
                logger.debug(f"No events found for league {league_id} season {season}")
                return []

            # Return limited results
            return events_list[:max_events]

        except Exception as e:
            logger.error(f"Error fetching season events for {league_id} {season}: {e}")
            return []

    def get_league_info(self, league_id: str) -> Optional[Dict[str, Any]]:
        """
        Get league information.

        Args:
            league_id: TheSportsDB league ID (string)

        Returns:
            Dict with keys:
            - strLeague: League name
            - strCountry: Country
            - strSport: Sport type
            - intFormedYear: Year founded
            - strLeagueAlternate: Alternative league name
            Or None if not found
        """
        try:
            result = leagues.leagueInfo(league_id)

            # API returns None for invalid league IDs
            if result is None:
                logger.debug(f"League {league_id} not found (API returned None)")
                return None

            if not isinstance(result, dict):
                logger.warning(f"Invalid response type from leagueInfo: {type(result)}")
                return None

            # Try different response formats
            # Format 1: results array (expected)
            results = result.get("results", [])
            if results and isinstance(results, list) and len(results) > 0:
                return results[0]

            # Format 2: direct league object
            if result.get("strLeague"):
                return result

            logger.debug(f"League {league_id} not found in response")
            return None

        except Exception as e:
            logger.error(f"Error fetching league info for {league_id}: {e}")
            return None

    def get_league_teams(self, league_id: str, max_teams: int = 50) -> List[Dict[str, Any]]:
        """
        Get all teams in a league.

        Args:
            league_id: TheSportsDB league ID (string)
            max_teams: Maximum number of teams to return

        Returns:
            List of team dicts with keys:
            - idTeam: Unique team ID
            - strTeam: Team name
            - strCountry: Country
            - strLeague: League name
            - strSport: Sport type
        """
        try:
            result = teams.leagueTeams(league_id)

            if not result or not isinstance(result, dict):
                logger.warning(f"Invalid response from leagueTeams: {type(result)}")
                return []

            # API uses 'teams' key for this endpoint
            teams_list = result.get("teams", [])

            # Fallback to 'results' for backward compatibility
            if not teams_list:
                teams_list = result.get("results", [])

            if not teams_list:
                logger.debug(f"No teams found for league {league_id}")
                return []

            return teams_list[:max_teams]

        except Exception as e:
            logger.error(f"Error fetching teams for league {league_id}: {e}")
            return []

    def match_channel_to_event(self, channel_name: str, league_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Attempt to match a channel name to a sports event.

        Looks for upcoming events that match the channel name pattern.
        Supports patterns like:
        - "Team A vs Team B"
        - "Team A - Team B"
        - Just team names

        Args:
            channel_name: PPV channel name to match
            league_id: Optional league ID to search within

        Returns:
            Matched event dict or None if no match found
        """
        if not channel_name:
            return None

        channel_lower = channel_name.lower().strip()

        # If no league specified, try English Premier League as default
        if not league_id:
            league_id = "133602"

        events_list = self.get_next_league_events(league_id)

        for event in events_list:
            event_name = event.get("strEvent", "").lower()

            # Check various matching patterns
            home_team = event.get("strHomeTeam", "").lower()
            away_team = event.get("strAwayTeam", "").lower()

            if home_team in channel_lower and away_team in channel_lower:
                logger.info(f"Matched channel '{channel_name}' to event {event.get('strEvent')}")
                return event

            if event_name in channel_lower:
                logger.info(f"Matched channel '{channel_name}' to event {event.get('strEvent')}")
                return event

        logger.debug(f"No event match found for channel '{channel_name}'")
        return None

    def find_events_for_date(self, date_str: str, league_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find events scheduled for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format
            league_id: Optional league ID to search within

        Returns:
            List of events scheduled for that date
        """
        if not league_id:
            league_id = "133602"

        events_list = self.get_next_league_events(league_id, max_events=100)

        matching_events = [e for e in events_list if e.get("dateEvent") == date_str]

        return matching_events

    def get_event_by_id(self, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific event.

        Args:
            event_id: TheSportsDB event ID

        Returns:
            Event dict with full details or None if not found
        """
        try:
            result = events.eventInfo(event_id)

            if not result or not isinstance(result, dict):
                logger.warning(f"Invalid response from eventInfo: {type(result)}")
                return None

            results = result.get("results", [])
            if not results:
                logger.debug(f"Event {event_id} not found")
                return None

            return results[0]

        except Exception as e:
            logger.error(f"Error fetching event info for {event_id}: {e}")
            return None

    def is_event_live(self, event: Dict[str, Any]) -> bool:
        """
        Check if an event is currently live based on timestamp.

        Args:
            event: Event dict with strTimestamp and strStatus

        Returns:
            True if event is currently being played
        """
        status = event.get("strStatus", "").lower()
        if "live" in status or "in progress" in status:
            return True

        # Check timestamp if status not reliable
        try:
            timestamp_str = event.get("strTimestamp")
            if timestamp_str:
                event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                # Consider event live if within 3.5 hours of start time
                # (average sports event duration + buffer)
                return now >= event_time and now <= event_time + timedelta(hours=3.5)
        except Exception as e:
            logger.debug(f"Error parsing event timestamp: {e}")

        return False

    def is_event_upcoming(self, event: Dict[str, Any], hours_ahead: int = 24) -> bool:
        """
        Check if an event is upcoming within specified hours.

        Args:
            event: Event dict with strTimestamp
            hours_ahead: How many hours ahead to consider "upcoming"

        Returns:
            True if event is scheduled within hours_ahead
        """
        try:
            timestamp_str = event.get("strTimestamp")
            if timestamp_str:
                event_time = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc).replace(tzinfo=None)
                return now <= event_time <= now + timedelta(hours=hours_ahead)
        except Exception as e:
            logger.debug(f"Error parsing event timestamp: {e}")

        return False

    def clear_cache(self):
        """Clear the service cache."""
        self._cache.clear()
        logger.debug("TheSportsDB service cache cleared")


# Global instance
_thesportsdb_service: Optional[TheSportsDBService] = None


def get_thesportsdb_service() -> TheSportsDBService:
    """Get or create the global TheSportsDB service instance."""
    global _thesportsdb_service
    if _thesportsdb_service is None:
        _thesportsdb_service = TheSportsDBService()
    return _thesportsdb_service
