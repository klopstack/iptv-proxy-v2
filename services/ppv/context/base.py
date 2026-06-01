"""
Base types for the PPV context data provider plugin system.

Every provider must subclass ContextDataProvider and declare:
- name: unique identifier string
- supported_sports: set of sport name strings (e.g. {"NFL", "NBA"})
- supported_leagues: set of league name strings; empty set means all leagues for supported sports
- provided_data_types: set of DataType values this provider can return
- priority: lower number = higher priority (used by registry when multiple providers cover the same sport/data type)

Providers implement the four data-type methods.  A method should return None
(not raise) when data is unavailable so the assembler can fall through to the
next provider.

Provider settings
-----------------
Each provider can declare UI-visible settings fields by overriding
``settings_fields()``.  Settings are stored in the ``provider_settings``
database table and accessed via ``get_setting()`` / ``set_setting()``.

Example ``settings_fields()`` implementation::

    def settings_fields(self):
        return [
            {
                "key": "api_key",
                "label": "API Key",
                "type": "password",
                "description": "Your API key from example.com.",
                "required": True,
            },
        ]
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class DataType(str, Enum):
    """Types of contextual data a provider can supply."""

    STANDINGS = "standings"
    HEAD_TO_HEAD = "head_to_head"
    TEAM_FORM = "team_form"
    EVENT_NOTES = "event_notes"
    FIGHTER_RECORD = "fighter_record"


@dataclass
class TeamContext:
    """Contextual facts about one team in a matchup."""

    name: str
    record: Optional[str] = None  # e.g. "11-3" or "68 pts, 3rd place"
    standing: Optional[str] = None  # e.g. "1st in AFC West, #2 seed"
    recent_form: List[str] = field(default_factory=list)  # e.g. ["W 24-17", "L 10-14"]
    extra: Optional[str] = None  # sport-specific extras (fighter record, world ranking, etc.)


@dataclass
class EventContext:
    """
    All contextual facts assembled for an event.

    This is the sole input to the LLM prompt builder — the LLM must not be
    asked to supply any additional facts beyond what appears here.
    """

    sport: str
    league: str
    home_team: TeamContext
    away_team: TeamContext
    head_to_head: List[str] = field(default_factory=list)  # e.g. ["2024-01-28: Ravens 17, Chiefs 10"]
    event_notes: Optional[str] = None  # source-provided preview or stakes note
    data_sources: List[str] = field(default_factory=list)  # which providers contributed
    missing_data: List[str] = field(default_factory=list)  # data types with no provider coverage


class ContextDataProvider(ABC):
    """
    Abstract base class for context data providers.

    Subclasses must set the class-level attributes and implement the four
    data-retrieval methods.  All methods should return None when data is
    unavailable rather than raising an exception.
    """

    #: Unique lowercase identifier, e.g. "espn", "football_data"
    name: str = ""

    #: Sport names this provider covers (case-insensitive matching is handled
    #: by the registry).  Use the same strings that appear in Event.sport.
    supported_sports: Set[str] = set()

    #: League names this provider covers.  Empty set means "all leagues for
    #: the supported sports".
    supported_leagues: Set[str] = set()

    #: Data types this provider can supply.
    provided_data_types: Set[DataType] = set()

    #: Lower number = higher priority when multiple providers cover the same
    #: sport/data-type combination.
    priority: int = 50

    # ------------------------------------------------------------------
    # Data retrieval methods
    # ------------------------------------------------------------------

    def get_standings(self, sport: str, league: str, season: Optional[str] = None) -> Optional[dict]:
        """
        Return current standings for the given league.

        Expected return shape (all values optional):
        {
            "home": {"record": "11-3", "standing": "1st in AFC West, #2 seed"},
            "away": {"record": "10-4", "standing": "1st in AFC North, #3 seed"},
        }

        The caller passes home_team_name / away_team_name separately; the provider
        can choose any key structure as long as assembler.py maps it.
        """
        return None  # pragma: no cover

    def get_head_to_head(
        self,
        home_team: str,
        away_team: str,
        sport: str,
        home_team_id: Optional[str] = None,
        away_team_id: Optional[str] = None,
        limit: int = 5,
    ) -> Optional[List[str]]:
        """
        Return last *limit* head-to-head results as human-readable strings.

        Example: ["2024-01-28: Ravens 17, Chiefs 10", "2023-09-05: Chiefs 20, Ravens 17 (OT)"]
        """
        return None  # pragma: no cover

    def get_team_form(
        self,
        team_name: str,
        sport: str,
        team_id: Optional[str] = None,
        last_n: int = 5,
    ) -> Optional[List[str]]:
        """
        Return the last *last_n* results for a single team.

        Example: ["W 3-1 vs Arsenal", "L 0-2 vs Man City", "W 2-0 vs Brighton"]
        """
        return None  # pragma: no cover

    def get_event_notes(
        self,
        home_team: str,
        away_team: str,
        sport: str,
        event_date: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Return a short source-provided preview note or None.

        Example: "Clinching scenario: Chiefs can secure #1 seed with a win."
        """
        return None  # pragma: no cover

    # ------------------------------------------------------------------
    # Plugin settings API
    # ------------------------------------------------------------------

    def settings_fields(self) -> List[Dict]:
        """
        Return a list of setting field definitions for this provider.

        Each entry is a dict with the following keys:

        ``key`` (str)
            Setting identifier, used with :meth:`get_setting` / :meth:`set_setting`.
        ``label`` (str)
            Human-readable label shown in the UI.
        ``type`` (str)
            Field type: ``"text"``, ``"password"``, ``"select"``, or ``"toggle"``.
        ``description`` (str, optional)
            Explanatory text shown below the field.
        ``required`` (bool, optional)
            Whether the field must be set for the provider to function.
        ``options`` (list of ``{"value": ..., "label": ...}``, optional)
            Choices for ``"select"`` fields.
        ``default`` (str, optional)
            Default value shown in the UI when nothing is stored.

        Override this method in subclasses to expose provider-specific
        configuration (API keys, credentials, etc.).
        """
        return []

    def get_setting(self, key: str, default: str = "") -> str:
        """Read a provider setting from the database.

        Falls back to *default* when the setting has not been stored yet.
        """
        try:
            from models.provider_settings import ProviderSettings

            return ProviderSettings.get(self.name, key, default=default)
        except Exception:
            return default

    def set_setting(self, key: str, value: str) -> None:
        """Persist a provider setting to the database."""
        from models.provider_settings import ProviderSettings

        ProviderSettings.set(self.name, key, value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def covers_sport(self, sport: str) -> bool:
        """Return True if this provider covers the given sport (case-insensitive).

        An empty ``supported_sports`` set means the provider covers all sports.
        """
        if not self.supported_sports:
            return True  # empty set = all sports
        sport_lower = sport.lower()
        return any(s.lower() == sport_lower for s in self.supported_sports)

    def covers_league(self, league: str) -> bool:
        """Return True if this provider covers the given league, or covers all leagues."""
        if not self.supported_leagues:
            return True  # empty set = all leagues
        league_lower = league.lower()
        return any(lg.lower() == league_lower for lg in self.supported_leagues)

    def covers(self, sport: str, league: str, data_type: DataType) -> bool:
        """Return True if this provider covers the sport/league/data-type combination."""
        return self.covers_sport(sport) and self.covers_league(league) and data_type in self.provided_data_types

    def __repr__(self) -> str:
        return f"<ContextDataProvider name={self.name!r} priority={self.priority}>"
