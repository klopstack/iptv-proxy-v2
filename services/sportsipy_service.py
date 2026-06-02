"""
Sportsipy Integration Service

Provides integration with the sportsipy library for matching PPV channels
to sports events. Sportsipy scrapes Sports Reference websites and provides
data for:
- FB (Football/Soccer)
- MLB (Baseball)
- NBA (Basketball)
- NCAAB (College Basketball)
- NCAAF (College Football)
- NFL (American Football)
- NHL (Ice Hockey)

Team data is stored in the database (SportsTeam model) and can be refreshed
from sportsipy on a schedule. This avoids hardcoding team lists and allows
for automatic updates.

Uses the maintained fork from: https://github.com/davidjkrause/sportsipy
Install with: pip install git+https://github.com/davidjkrause/sportsipy@master

IMPORTANT: Sports Reference rate limits requests (30 pages/minute).
Team data refresh should be done sparingly with delays between requests.
"""

import logging
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)

# Track whether sportsipy is available
SPORTSIPY_AVAILABLE = False
SPORTSIPY_IMPORT_ERROR: Optional[str] = None
SPORTSIPY_INSTALL_INSTRUCTIONS = "pip install git+https://github.com/davidjkrause/sportsipy@master"

try:
    from sportsipy.fb.teams import Teams as FBTeams
    from sportsipy.mlb.schedule import Schedule as MLBSchedule
    from sportsipy.mlb.teams import Teams as MLBTeams
    from sportsipy.nba.schedule import Schedule as NBASchedule
    from sportsipy.nba.teams import Teams as NBATeams
    from sportsipy.ncaab.teams import Teams as NCAABTeams
    from sportsipy.ncaaf.teams import Teams as NCAAFTeams
    from sportsipy.nfl.schedule import Schedule as NFLSchedule
    from sportsipy.nfl.teams import Teams as NFLTeams
    from sportsipy.nhl.schedule import Schedule as NHLSchedule
    from sportsipy.nhl.teams import Teams as NHLTeams

    SPORTSIPY_AVAILABLE = True
    logger.info("sportsipy library loaded successfully (davidjkrause fork)")
except ImportError as e:
    SPORTSIPY_IMPORT_ERROR = str(e)
    logger.warning(f"sportsipy not available: {e}. Install with: {SPORTSIPY_INSTALL_INSTRUCTIONS}")

# Sport detection patterns - built dynamically from database
# These are fallback patterns when no team data is in DB
FALLBACK_SPORT_PATTERNS = {
    "nfl": [r"\b(NFL|American Football)\b"],
    "nba": [r"\b(NBA|Basketball)\b"],
    "nhl": [r"\b(NHL|Hockey)\b"],
    "mlb": [r"\b(MLB|Baseball)\b"],
    "ncaaf": [r"\b(NCAA Football|College Football|CFB)\b"],
    "ncaab": [r"\b(NCAA Basketball|College Basketball|March Madness|Final Four)\b"],
    "mls": [r"\b(MLS|Major League Soccer|Soccer)\b"],
}


class SportsipyEvent:
    """Represents an event from sportsipy data."""

    def __init__(
        self,
        event_id: str,
        home_team: str,
        away_team: str,
        date: datetime,
        sport: str,
        league: str,
        location: Optional[str] = None,
        result: Optional[str] = None,
    ):
        self.event_id = event_id
        self.home_team = home_team
        self.away_team = away_team
        self.date = date
        self.sport = sport
        self.league = league
        self.location = location
        self.result = result

    @property
    def event_name(self) -> str:
        return f"{self.away_team} @ {self.home_team}"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "home_team": self.home_team,
            "away_team": self.away_team,
            "event_name": self.event_name,
            "date": serialize_utc_iso(self.date),
            "sport": self.sport,
            "league": self.league,
            "location": self.location,
            "result": self.result,
        }

    def __repr__(self):
        return f"<SportsipyEvent {self.event_name} @ {self.date}>"


class SportsipyService:
    """
    Service for matching PPV channels using sportsipy library.

    This service:
    1. Loads team data from database (SportsTeam model)
    2. Detects sport type from channel name
    3. Extracts team names from channel name
    4. Looks up team schedule using sportsipy
    5. Finds matching games by date

    Team data can be refreshed from sportsipy via refresh_teams_from_sportsipy().
    """

    def __init__(self):
        self._cache: Dict[str, Any] = {}
        self._cache_ttl = 3600  # 1 hour
        self._team_mappings: Dict[str, Dict[str, str]] = {}
        self._sport_patterns: Dict[str, List[str]] = {}
        self._patterns_loaded = False

    def is_available(self) -> bool:
        """Check if sportsipy is available."""
        return SPORTSIPY_AVAILABLE

    def _ensure_patterns_loaded(self):
        """Load team data from database if not already loaded."""
        if self._patterns_loaded:
            return

        try:
            from models import SportsTeam

            # Load team mappings and build patterns for each sport
            for sport in SportsTeam.SPORTS:
                self._team_mappings[sport] = SportsTeam.get_team_mapping(sport)

                # Build regex pattern from team names
                team_names = SportsTeam.get_all_team_names(sport)
                if team_names:
                    # Escape special regex chars and join with |
                    escaped_names = [re.escape(name) for name in team_names if name]
                    if escaped_names:
                        pattern = r"\b(" + "|".join(escaped_names) + r")\b"
                        self._sport_patterns[sport] = [pattern]

            # Add fallback patterns for sports with no team data
            for sport, patterns in FALLBACK_SPORT_PATTERNS.items():
                if sport not in self._sport_patterns:
                    self._sport_patterns[sport] = patterns
                else:
                    # Prepend sport-specific keywords to team patterns
                    self._sport_patterns[sport] = patterns + self._sport_patterns[sport]

            self._patterns_loaded = True
            logger.debug(f"Loaded team patterns for {len(self._team_mappings)} sports")

        except Exception as e:
            logger.warning(f"Failed to load team data from database: {e}")
            # Use fallback patterns
            self._sport_patterns = FALLBACK_SPORT_PATTERNS.copy()
            self._patterns_loaded = True

    def reload_team_data(self):
        """Force reload of team data from database."""
        self._patterns_loaded = False
        self._team_mappings.clear()
        self._sport_patterns.clear()
        self._ensure_patterns_loaded()

    def detect_sport(self, channel_name: str) -> Optional[str]:
        """
        Detect the sport type from channel name.

        Returns: 'nfl', 'nba', 'nhl', 'mlb', 'ncaaf', 'ncaab', or None

        Checks college sports patterns first since they contain more specific
        identifiers like "NCAA" that should take precedence over generic
        terms like "Football" or "Basketball" in pro sports patterns.
        """
        self._ensure_patterns_loaded()
        name_lower = channel_name.lower()

        # Check college sports first (more specific patterns)
        for sport in ["ncaaf", "ncaab"]:
            if sport in self._sport_patterns:
                for pattern in self._sport_patterns[sport]:
                    if re.search(pattern, name_lower, re.IGNORECASE):
                        return sport

        # Then check pro sports
        for sport in ["nfl", "nba", "nhl", "mlb"]:
            if sport in self._sport_patterns:
                for pattern in self._sport_patterns[sport]:
                    if re.search(pattern, name_lower, re.IGNORECASE):
                        return sport

        return None

    def extract_teams(self, channel_name: str, sport: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract team names from channel name.

        Returns: (home_team_abbrev, away_team_abbrev) or (None, None)
        """
        self._ensure_patterns_loaded()

        if not sport:
            sport = self.detect_sport(channel_name)

        if not sport:
            return None, None

        team_map = self._team_mappings.get(sport, {})
        if not team_map:
            return None, None

        name_lower = channel_name.lower()
        found_teams = []

        # Find all matching teams
        for team_name, abbrev in team_map.items():
            if team_name in name_lower:
                found_teams.append((team_name, abbrev))

        # Sort by length (longer matches are more specific)
        found_teams.sort(key=lambda x: len(x[0]), reverse=True)

        # Get unique abbreviations (dedupe)
        seen_abbrevs = set()
        unique_teams = []
        for name, abbrev in found_teams:
            if abbrev not in seen_abbrevs:
                seen_abbrevs.add(abbrev)
                unique_teams.append(abbrev)

        if len(unique_teams) >= 2:
            return unique_teams[0], unique_teams[1]
        elif len(unique_teams) == 1:
            return unique_teams[0], None

        return None, None

    def get_team_schedule(self, team_abbrev: str, sport: str, year: Optional[int] = None) -> List[SportsipyEvent]:
        """
        Get schedule for a team.

        Args:
            team_abbrev: Team abbreviation
            sport: Sport type (nfl, nba, etc.)
            year: Season year (defaults to current)

        Returns: List of SportsipyEvent
        """
        if not SPORTSIPY_AVAILABLE:
            logger.warning("sportsipy not available")
            return []

        cache_key = f"{sport}_{team_abbrev}_{year}"
        if cache_key in self._cache:
            cached_time, cached_data = self._cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self._cache_ttl:
                return cached_data

        try:
            schedule_class = {
                "nfl": NFLSchedule,
                "nba": NBASchedule,
                "nhl": NHLSchedule,
                "mlb": MLBSchedule,
            }.get(sport)

            if not schedule_class:
                logger.warning(f"No schedule class for sport: {sport}")
                return []

            if year:
                schedule = schedule_class(team_abbrev, year=year)
            else:
                schedule = schedule_class(team_abbrev)

            events = []
            for game in schedule:
                try:
                    event = SportsipyEvent(
                        event_id=f"{sport}_{team_abbrev}_{game.boxscore_index}",
                        home_team=team_abbrev if game.location == "Home" else game.opponent_abbr,
                        away_team=game.opponent_abbr if game.location == "Home" else team_abbrev,
                        date=game.datetime if hasattr(game, "datetime") else None,
                        sport=sport,
                        league=sport.upper(),
                        location=game.location,
                        result=game.result if hasattr(game, "result") else None,
                    )
                    events.append(event)
                except Exception as e:
                    logger.debug(f"Error parsing game: {e}")
                    continue

            self._cache[cache_key] = (datetime.now(), events)
            return events

        except Exception as e:
            logger.error(f"Error getting schedule for {team_abbrev}: {e}")
            return []

    def find_matching_event(
        self,
        channel_name: str,
        target_date: Optional[datetime] = None,
    ) -> Optional[SportsipyEvent]:
        """
        Find a matching event for a channel name.

        Args:
            channel_name: PPV channel name
            target_date: Optional date to match (defaults to today)

        Returns: SportsipyEvent or None
        """
        if not SPORTSIPY_AVAILABLE:
            return None

        sport = self.detect_sport(channel_name)
        if not sport:
            return None

        team1, team2 = self.extract_teams(channel_name, sport)
        if not team1:
            return None

        if target_date is None:
            target_date = datetime.now()

        # Get schedule for the first team
        events = self.get_team_schedule(team1, sport)

        # Find event matching the date and opponent
        for event in events:
            if event.date and event.date.date() == target_date.date():
                # If we have both teams, verify the opponent matches
                if team2:
                    if event.home_team == team2 or event.away_team == team2:
                        return event
                else:
                    return event

        return None

    def clear_cache(self):
        """Clear the schedule cache."""
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        self._ensure_patterns_loaded()
        return {
            "available": SPORTSIPY_AVAILABLE,
            "cache_size": len(self._cache),
            "sports_loaded": list(self._team_mappings.keys()),
            "teams_per_sport": {sport: len(teams) for sport, teams in self._team_mappings.items()},
        }


def refresh_teams_from_sportsipy(
    sports: Optional[List[str]] = None,
    delay_seconds: float = 3.0,
) -> Dict[str, Any]:
    """
    Refresh team data from sportsipy and store in database.

    IMPORTANT: Sports Reference rate limits to 30 requests/minute.
    This function adds delays between requests to avoid rate limiting.

    Args:
        sports: List of sports to refresh (default: all supported sports)
        delay_seconds: Delay between API calls (default: 3.0 seconds)

    Returns: Dict with refresh statistics
    """
    if not SPORTSIPY_AVAILABLE:
        return {
            "success": False,
            "error": f"sportsipy not available. {SPORTSIPY_INSTALL_INSTRUCTIONS}",
            "import_error": SPORTSIPY_IMPORT_ERROR,
        }

    from models import SportsTeam, db

    if sports is None:
        # Default to all available sports from sportsipy
        sports = ["fb", "mlb", "nba", "ncaab", "ncaaf", "nfl", "nhl"]

    stats: Dict[str, Any] = {
        "success": True,
        "sports_processed": [],
        "teams_added": 0,
        "teams_updated": 0,
        "errors": [],
    }

    sport_classes = {
        "fb": FBTeams,
        "mlb": MLBTeams,
        "nba": NBATeams,
        "ncaab": NCAABTeams,
        "ncaaf": NCAAFTeams,
        "nfl": NFLTeams,
        "nhl": NHLTeams,
    }

    for sport in sports:
        if sport not in sport_classes:
            stats["errors"].append(f"Unknown sport: {sport}")
            continue

        try:
            logger.info(f"Refreshing {sport.upper()} teams from sportsipy...")

            # Fetch teams from sportsipy
            teams_class = sport_classes[sport]
            teams = teams_class()

            for team in teams:
                try:
                    # Check if team exists
                    existing = SportsTeam.query.filter_by(
                        sport=sport,
                        abbreviation=team.abbreviation,
                    ).first()

                    if existing:
                        # Update existing team
                        existing.name = team.name
                        city = getattr(team, "city", None) or getattr(team, "location", None)
                        if city:
                            existing.city = str(city)
                            from services.ppv.city_timezone_map import iana_for_city

                            tz = iana_for_city(str(city))
                            if tz:
                                existing.iana_timezone = tz
                        existing.last_updated_at = datetime.now()
                        stats["teams_updated"] += 1
                    else:
                        # Create new team
                        city = getattr(team, "city", None) or getattr(team, "location", None)
                        city_str = str(city) if city else None
                        iana_tz = None
                        if city_str:
                            from services.ppv.city_timezone_map import iana_for_city

                            iana_tz = iana_for_city(city_str)
                        new_team = SportsTeam(
                            sport=sport,
                            abbreviation=team.abbreviation,
                            name=team.name,
                            city=city_str,
                            iana_timezone=iana_tz,
                            source="sportsipy",
                        )
                        # Generate default aliases
                        aliases = _generate_team_aliases(team.name, team.abbreviation)
                        new_team.set_aliases(aliases)
                        db.session.add(new_team)
                        stats["teams_added"] += 1

                except Exception as e:
                    logger.warning(f"Error processing team {team.name}: {e}")
                    continue

            db.session.commit()
            stats["sports_processed"].append(sport)
            logger.info(f"Completed {sport.upper()} team refresh")

            # Rate limit delay
            if delay_seconds > 0:
                logger.debug(f"Waiting {delay_seconds}s before next sport...")
                time.sleep(delay_seconds)

        except Exception as e:
            error_msg = f"Error refreshing {sport}: {e}"
            logger.error(error_msg)
            stats["errors"].append(error_msg)
            db.session.rollback()

    return stats


def _generate_team_aliases(name: str, abbreviation: str) -> List[str]:
    """Generate common aliases for a team name."""
    aliases = []

    # Lowercase full name
    aliases.append(name.lower())

    # Abbreviation (lowercase)
    aliases.append(abbreviation.lower())

    # Extract city and team name parts
    # e.g., "New England Patriots" -> ["new england", "patriots"]
    parts = name.lower().split()
    if len(parts) >= 2:
        # Last word is usually the team name
        team_name = parts[-1]
        aliases.append(team_name)

        # City/region is everything before
        city = " ".join(parts[:-1])
        if city:
            aliases.append(city)

    # Handle special cases
    name_lower = name.lower()
    if "76ers" in name_lower:
        aliases.append("sixers")
    if "trail blazers" in name_lower:
        aliases.append("blazers")
    if "red sox" in name_lower:
        aliases.append("sox")
    if "white sox" in name_lower:
        aliases.append("sox")

    # Remove duplicates while preserving order
    seen = set()
    unique_aliases = []
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            unique_aliases.append(alias)

    return unique_aliases


def seed_initial_team_data() -> Dict[str, Any]:
    """
    Seed initial team data into the database.

    This can be called during app initialization to ensure
    basic team data exists even if sportsipy refresh hasn't run.

    Returns: Dict with seeding statistics
    """
    from models import SportsTeam, db

    # Check if we already have data
    existing_count = SportsTeam.query.count()
    if existing_count > 0:
        return {
            "success": True,
            "message": f"Database already has {existing_count} teams",
            "teams_added": 0,
        }

    logger.info("Seeding initial team data...")

    # Minimal seed data - just enough for basic matching
    # Full data should come from sportsipy refresh
    seed_teams = [
        # NFL - Major teams
        ("nfl", "NWE", "New England Patriots", ["patriots", "pats", "new england"]),
        ("nfl", "DAL", "Dallas Cowboys", ["cowboys", "dallas"]),
        ("nfl", "KAN", "Kansas City Chiefs", ["chiefs", "kansas city", "kc"]),
        ("nfl", "BUF", "Buffalo Bills", ["bills", "buffalo"]),
        ("nfl", "PHI", "Philadelphia Eagles", ["eagles", "philly"]),
        ("nfl", "SFO", "San Francisco 49ers", ["49ers", "niners", "san francisco"]),
        ("nfl", "GNB", "Green Bay Packers", ["packers", "green bay"]),
        ("nfl", "PIT", "Pittsburgh Steelers", ["steelers", "pittsburgh"]),
        # NBA - Major teams
        ("nba", "LAL", "Los Angeles Lakers", ["lakers", "la lakers"]),
        ("nba", "BOS", "Boston Celtics", ["celtics", "boston"]),
        ("nba", "GSW", "Golden State Warriors", ["warriors", "golden state"]),
        ("nba", "MIA", "Miami Heat", ["heat", "miami"]),
        ("nba", "CHI", "Chicago Bulls", ["bulls", "chicago"]),
        ("nba", "NYK", "New York Knicks", ["knicks", "new york"]),
        # NHL - Major teams
        ("nhl", "TOR", "Toronto Maple Leafs", ["maple leafs", "leafs", "toronto"]),
        ("nhl", "MTL", "Montreal Canadiens", ["canadiens", "habs", "montreal"]),
        ("nhl", "BOS", "Boston Bruins", ["bruins", "boston"]),
        ("nhl", "NYR", "New York Rangers", ["rangers", "new york"]),
        ("nhl", "CHI", "Chicago Blackhawks", ["blackhawks", "hawks", "chicago"]),
        ("nhl", "DET", "Detroit Red Wings", ["red wings", "wings", "detroit"]),
        # MLB - Major teams
        ("mlb", "NYY", "New York Yankees", ["yankees", "new york", "bronx bombers"]),
        ("mlb", "BOS", "Boston Red Sox", ["red sox", "sox", "boston"]),
        ("mlb", "LAD", "Los Angeles Dodgers", ["dodgers", "la dodgers"]),
        ("mlb", "CHC", "Chicago Cubs", ["cubs", "chicago"]),
        ("mlb", "STL", "St. Louis Cardinals", ["cardinals", "cards", "st louis"]),
        ("mlb", "SFG", "San Francisco Giants", ["giants", "san francisco"]),
        # FB (Football/Soccer) - Major teams
        ("fb", "MUN", "Manchester United", ["manchester united", "man united", "united"]),
        ("fb", "LIV", "Liverpool", ["liverpool", "reds"]),
        ("fb", "MCI", "Manchester City", ["manchester city", "man city", "city"]),
        ("fb", "ARS", "Arsenal", ["arsenal", "gunners"]),
        ("fb", "CHE", "Chelsea", ["chelsea", "blues"]),
        ("fb", "TOT", "Tottenham", ["tottenham", "spurs"]),
    ]

    teams_added = 0
    for sport, abbrev, name, aliases in seed_teams:
        try:
            team = SportsTeam(
                sport=sport,
                abbreviation=abbrev,
                name=name,
                source="seed",
            )
            team.set_aliases(aliases)
            db.session.add(team)
            teams_added += 1
        except Exception as e:
            logger.warning(f"Error seeding team {name}: {e}")

    try:
        db.session.commit()
        logger.info(f"Seeded {teams_added} initial teams")
        return {
            "success": True,
            "message": f"Seeded {teams_added} teams",
            "teams_added": teams_added,
        }
    except Exception as e:
        db.session.rollback()
        logger.error(f"Error committing seed data: {e}")
        return {
            "success": False,
            "error": str(e),
            "teams_added": 0,
        }


# Global instance
_sportsipy_service: Optional[SportsipyService] = None


def get_sportsipy_service() -> SportsipyService:
    """Get or create the global sportsipy service instance."""
    global _sportsipy_service
    if _sportsipy_service is None:
        _sportsipy_service = SportsipyService()
    return _sportsipy_service
