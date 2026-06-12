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

Uses the maintained fork from: https://github.com/benklop/sportsipy
(includes HTTP rate limiting, NCAAF URL fixes, and NBA player stat updates).
Install with: pip install git+https://github.com/benklop/sportsipy@ca69fc7

IMPORTANT: Sports Reference rate limits requests (30 pages/minute).
Team refresh uses sportsipy's built-in HTTP rate limiting (20 req/min, circuit breaker on blocks).
"""

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import IO, Any, Dict, List, Optional, Sequence, Tuple

from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)

try:
    import fcntl

    _HAS_FCNTL = True
except ImportError:
    _HAS_FCNTL = False

_REFRESH_LOCK_PATH = Path(os.getenv("SPORTSIPY_REFRESH_LOCK_PATH", "/app/data/sportsipy_refresh.lock"))
_DEFAULT_REFRESH_SPORTS = ["mlb", "nba", "ncaab", "ncaaf", "nfl", "nhl"]

# Track whether sportsipy is available
SPORTSIPY_AVAILABLE = False
SPORTSIPY_IMPORT_ERROR: Optional[str] = None
SPORTSIPY_GIT_REF = "git+https://github.com/benklop/sportsipy@ca69fc7"
SPORTSIPY_INSTALL_INSTRUCTIONS = f"pip install {SPORTSIPY_GIT_REF}"

SPORTSIPY_TEAM_CLASSES: Dict[str, Any] = {}
SPORTSIPY_SCHEDULE_CLASSES: Dict[str, Any] = {}
_import_errors: list[str] = []


def _import_sportsipy_attr(module: str, attr: str) -> Any:
    try:
        mod = __import__(module, fromlist=[attr])
        return getattr(mod, attr)
    except ImportError as exc:
        _import_errors.append(f"{module}.{attr}: {exc}")
        return None


for _sport, _module in [
    ("mlb", "sportsipy.mlb.teams"),
    ("nba", "sportsipy.nba.teams"),
    ("ncaab", "sportsipy.ncaab.teams"),
    ("ncaaf", "sportsipy.ncaaf.teams"),
    ("nfl", "sportsipy.nfl.teams"),
    ("nhl", "sportsipy.nhl.teams"),
]:
    _teams_cls = _import_sportsipy_attr(_module, "Teams")
    if _teams_cls is not None:
        SPORTSIPY_TEAM_CLASSES[_sport] = _teams_cls

_fb_teams = _import_sportsipy_attr("sportsipy.fb.teams", "Teams")
if _fb_teams is not None:
    SPORTSIPY_TEAM_CLASSES["fb"] = _fb_teams

for _sport, _module in [
    ("mlb", "sportsipy.mlb.schedule"),
    ("nba", "sportsipy.nba.schedule"),
    ("ncaab", "sportsipy.ncaab.schedule"),
    ("ncaaf", "sportsipy.ncaaf.schedule"),
    ("nfl", "sportsipy.nfl.schedule"),
    ("nhl", "sportsipy.nhl.schedule"),
]:
    _schedule_cls = _import_sportsipy_attr(_module, "Schedule")
    if _schedule_cls is not None:
        SPORTSIPY_SCHEDULE_CLASSES[_sport] = _schedule_cls

SPORTSIPY_AVAILABLE = bool(SPORTSIPY_TEAM_CLASSES)
if SPORTSIPY_AVAILABLE:
    logger.info(
        "sportsipy loaded for sports: %s",
        ", ".join(sorted(SPORTSIPY_TEAM_CLASSES)),
    )
else:
    SPORTSIPY_IMPORT_ERROR = "; ".join(_import_errors) if _import_errors else "no team modules imported"
    logger.warning(
        "sportsipy not available: %s. Install with: %s",
        SPORTSIPY_IMPORT_ERROR,
        SPORTSIPY_INSTALL_INSTRUCTIONS,
    )

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
            del self._cache[cache_key]

        try:
            schedule_class = SPORTSIPY_SCHEDULE_CLASSES.get(sport)

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

    def purge_expired(self) -> int:
        """Remove expired schedule cache entries; return the number removed."""
        now = datetime.now()
        expired_keys = [
            key
            for key, (cached_time, _) in self._cache.items()
            if (now - cached_time).total_seconds() >= self._cache_ttl
        ]
        for key in expired_keys:
            del self._cache[key]
        return len(expired_keys)

    def get_stats(self) -> Dict[str, Any]:
        """Get service statistics."""
        self._ensure_patterns_loaded()
        return {
            "available": SPORTSIPY_AVAILABLE,
            "cache_size": len(self._cache),
            "sports_loaded": list(self._team_mappings.keys()),
            "teams_per_sport": {sport: len(teams) for sport, teams in self._team_mappings.items()},
        }


def _try_acquire_refresh_lock() -> Optional[IO[str]]:
    if not _HAS_FCNTL:
        return None
    _REFRESH_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    handle = open(_REFRESH_LOCK_PATH, "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(os.getpid()))
    handle.flush()
    return handle


def _release_refresh_lock(handle: Optional[IO[str]]) -> None:
    if handle is None:
        return
    try:
        if _HAS_FCNTL:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def _sportsipy_http_stats() -> Dict[str, Any]:
    try:
        from sportsipy import http_client

        return http_client.get_stats()
    except Exception:
        return {}


def refresh_teams_from_sportsipy(
    sports: Optional[List[str]] = None,
    delay_seconds: float = 0.0,
) -> Dict[str, Any]:
    """
    Refresh team data from sportsipy and store in database.

    Uses sportsipy's shared HTTP rate limiter (default 20 req/min, 3s spacing).
    Full team stats pages are fetched for accurate names, abbreviations, and cities.

    Args:
        sports: List of sports to refresh (default: mlb, nba, ncaab, ncaaf, nfl, nhl)
        delay_seconds: Optional pause between sports after each commit (http_client
            handles per-request spacing)

    Returns: Dict with refresh statistics
    """
    if not SPORTSIPY_AVAILABLE:
        return {
            "success": False,
            "error": f"sportsipy not available. {SPORTSIPY_INSTALL_INSTRUCTIONS}",
            "import_error": SPORTSIPY_IMPORT_ERROR,
        }

    lock_handle = _try_acquire_refresh_lock()
    if _HAS_FCNTL and lock_handle is None:
        return {
            "success": False,
            "error": "Another sportsipy refresh is already in progress",
            "http_stats": _sportsipy_http_stats(),
        }

    from models import SportsTeam, db
    from services.team_location_registry import apply_location_to_sports_team, lookup

    if sports is None:
        sports = list(_DEFAULT_REFRESH_SPORTS)

    stats: Dict[str, Any] = {
        "success": True,
        "sports_processed": [],
        "teams_added": 0,
        "teams_updated": 0,
        "location_misses": [],
        "errors": [],
    }

    sport_classes = SPORTSIPY_TEAM_CLASSES

    try:
        for sport in sports:
            if sport not in sport_classes:
                stats["errors"].append(f"Unknown sport: {sport}")
                continue

            try:
                logger.info("Refreshing %s teams from sportsipy...", sport.upper())

                teams_class = sport_classes[sport]
                teams = teams_class()

                for team in teams:
                    try:
                        existing = SportsTeam.query.filter_by(
                            sport=sport,
                            abbreviation=team.abbreviation,
                        ).first()

                        location = lookup(sport, team.abbreviation)
                        source = "sportsipy"

                        if existing:
                            existing.name = team.name
                            if location:
                                apply_location_to_sports_team(existing, location)
                                source = "sportsipy+location_registry"
                                existing.source = source
                            else:
                                stats["location_misses"].append(
                                    {"sport": sport, "abbreviation": team.abbreviation, "name": team.name}
                                )
                            existing.last_updated_at = datetime.now()
                            stats["teams_updated"] += 1
                        else:
                            new_team = SportsTeam(
                                sport=sport,
                                abbreviation=team.abbreviation,
                                name=team.name,
                                source=source,
                            )
                            if location:
                                apply_location_to_sports_team(new_team, location)
                                new_team.source = "sportsipy+location_registry"
                            else:
                                stats["location_misses"].append(
                                    {"sport": sport, "abbreviation": team.abbreviation, "name": team.name}
                                )
                            aliases = _generate_team_aliases(team.name, team.abbreviation)
                            new_team.set_aliases(aliases)
                            db.session.add(new_team)
                            stats["teams_added"] += 1

                    except Exception as e:
                        logger.warning("Error processing team %s: %s", team.name, e)
                        continue

                db.session.commit()
                stats["sports_processed"].append(sport)
                logger.info("Completed %s team refresh", sport.upper())

                if delay_seconds > 0:
                    time.sleep(delay_seconds)

            except Exception as e:
                error_msg = f"Error refreshing {sport}: {e}"
                logger.error(error_msg)
                stats["errors"].append(error_msg)
                db.session.rollback()

    finally:
        stats["http_stats"] = _sportsipy_http_stats()
        _release_refresh_lock(lock_handle)

    if stats["errors"] and not stats["sports_processed"]:
        stats["success"] = False

    return stats


LEGACY_FB_SEED_ABBREVS = frozenset({"MUN", "LIV", "MCI", "ARS", "CHE", "TOT"})


def refresh_tsdb_registry_teams(sports: Sequence[str] = ("fb", "wnba")) -> Dict[str, Any]:
    """
    Upsert teams from bundled location registry for TheSportsDB-backed sports.

    Uses TheSportsDB idTeam as SportsTeam.abbreviation — separate from sportsipy refresh.
    """
    from models import SportsTeam, db
    from services.team_location_registry import apply_location_to_sports_team, entries_for_sport

    stats: Dict[str, Any] = {
        "success": True,
        "teams_added": 0,
        "teams_updated": 0,
        "teams_removed": 0,
        "location_misses": [],
        "errors": [],
        "sports_processed": [],
    }

    try:
        for sport in sports:
            sport_l = sport.lower()
            entries = entries_for_sport(sport_l)
            if not entries:
                stats["errors"].append(f"No {sport_l} entries in location registry")
                continue

            if sport_l == "fb":
                removed = SportsTeam.query.filter(
                    SportsTeam.sport == "fb",
                    SportsTeam.abbreviation.in_(LEGACY_FB_SEED_ABBREVS),
                ).delete(synchronize_session=False)
                stats["teams_removed"] += removed

            for location in entries:
                if not location.iana_timezone and not location.city:
                    stats["location_misses"].append(
                        {"sport": sport_l, "abbreviation": location.key, "name": location.name}
                    )

                existing = SportsTeam.query.filter_by(sport=sport_l, abbreviation=location.key).first()
                if existing:
                    existing.name = location.name
                    apply_location_to_sports_team(existing, location)
                    existing.source = "thesportsdb+location_registry"
                    if location.aliases:
                        existing.set_aliases(list(location.aliases))
                    existing.last_updated_at = datetime.now()
                    stats["teams_updated"] += 1
                else:
                    team = SportsTeam(
                        sport=sport_l,
                        abbreviation=location.key,
                        name=location.name,
                        source="thesportsdb+location_registry",
                    )
                    apply_location_to_sports_team(team, location)
                    if location.aliases:
                        team.set_aliases(list(location.aliases))
                    db.session.add(team)
                    stats["teams_added"] += 1

            stats["sports_processed"].append(sport_l)

        if not stats["sports_processed"]:
            stats["success"] = False
        else:
            db.session.commit()
    except Exception as exc:
        db.session.rollback()
        stats["success"] = False
        stats["errors"].append(str(exc))
        logger.error("TheSportsDB registry refresh failed: %s", exc)

    return stats


def refresh_fb_teams_from_registry() -> Dict[str, Any]:
    """Upsert FB (soccer) teams from bundled location registry."""
    return refresh_tsdb_registry_teams(sports=("fb",))


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
