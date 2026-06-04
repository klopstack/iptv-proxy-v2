"""
Event Index Component

Manages all search indexes for calendar events. Provides efficient lookup
of events by team names, event names, leagues, words, and name parts.

This component centralizes index management that was previously scattered
throughout the ReverseEventMatcher class.
"""

from collections import defaultdict
from typing import Any, Dict, List

from services.reverse_event_matcher.text_processor import TextProcessor
from services.thesportsdb_calendar_scraper import CalendarEvent


class EventIndex:
    """
    Centralized search index for calendar events.

    Builds and manages multiple indexes for efficient event lookup:
    - team_index: Events by normalized team name
    - event_name_index: Events by normalized event name
    - league_index: Events by normalized league name
    - word_index: Events by significant words
    - last_name_index: Events by last names (for individual sports)
    - first_name_index: Events by first names (for individual sports)
    """

    # Minimum word length for indexing
    MIN_WORD_LENGTH = 4

    # Team suffixes that indicate organizations (not person names)
    TEAM_SUFFIXES = {
        "fc",
        "sc",
        "cf",
        "united",
        "city",
        "town",
        "athletic",
        "rovers",
        "wanderers",
        "county",
        "villa",
        "palace",
        "hotspur",
        "albion",
        "university",
        "state",
        "college",
    }

    def __init__(self, text_processor: TextProcessor):
        """
        Initialize with a TextProcessor for text normalization.

        Args:
            text_processor: TextProcessor instance for normalizing text
        """
        self.text_processor = text_processor

        # Main indexes
        self._team_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self._event_name_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self._league_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self._word_index: Dict[str, List[CalendarEvent]] = defaultdict(list)

        # Name part indexes for individual sports
        self._last_name_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self._first_name_index: Dict[str, List[CalendarEvent]] = defaultdict(list)

        # Lookup maps
        self._normalized_teams: Dict[str, str] = {}  # normalized -> original
        self._name_parts: Dict[str, tuple[str, str]] = {}  # normalized -> (first, last)

    def build_indexes(self, events: List[CalendarEvent]) -> None:
        """
        Build all search indexes from a list of events.

        Args:
            events: List of CalendarEvent objects to index
        """
        # Clear existing indexes
        self.clear()

        # Build indexes
        for event in events:
            self._index_event(event)

    def clear(self) -> None:
        """Clear all indexes."""
        self._team_index.clear()
        self._event_name_index.clear()
        self._league_index.clear()
        self._word_index.clear()
        self._last_name_index.clear()
        self._first_name_index.clear()
        self._normalized_teams.clear()
        self._name_parts.clear()

    def _index_event(self, event: CalendarEvent) -> None:
        """
        Index a single event across all indexes.

        Args:
            event: CalendarEvent to index
        """
        # Index team names
        if event.home_team:
            self._index_team(event.home_team, event)

        if event.away_team:
            self._index_team(event.away_team, event)

        # Index event name
        if event.event_name:
            normalized = self.text_processor.normalize_text(event.event_name)
            self._event_name_index[normalized].append(event)

            # Index significant words from event name
            words = self.text_processor.extract_significant_words(event.event_name)
            for word in words:
                self._word_index[word].append(event)

        # Index league name
        if event.league_name:
            normalized = self.text_processor.normalize_text(event.league_name)
            self._league_index[normalized].append(event)

            # Index significant words from league name
            words = self.text_processor.extract_significant_words(event.league_name)
            for word in words:
                self._word_index[word].append(event)

    def _index_team(self, team_name: str, event: CalendarEvent) -> None:
        """
        Index a team name and its parts.

        Args:
            team_name: Team name to index
            event: CalendarEvent associated with this team
        """
        if " / " in team_name:
            for partner in team_name.split(" / "):
                partner = partner.strip()
                if partner:
                    self._index_team(partner, event)
            normalized = self.text_processor.normalize_text(team_name)
            self._team_index[normalized].append(event)
            self._normalized_teams[normalized] = team_name
            return

        normalized = self.text_processor.normalize_text(team_name)
        self._team_index[normalized].append(event)
        self._normalized_teams[normalized] = team_name

        # Also index name parts for individual sports
        self._index_name_parts(team_name, event)

    def _index_name_parts(self, full_name: str, event: CalendarEvent) -> None:
        """
        Index first and last name parts from a person's name.

        This helps match "SERRANO VS TELLEZ" to "Amanda Serrano vs Reina Tellez".

        Current approach: Simple split (first word = first name, last word = last name).
        TODO: Consider using 'nameparser' library for better handling of suffixes
        (Jr, Sr, III) and titles, though we'd still need custom separator handling
        for "vs", "@", etc. Current approach works well for our use case.

        Args:
            full_name: Full name like "Amanda Serrano"
            event: CalendarEvent to associate with these name parts
        """
        if not full_name:
            return

        if " / " in full_name:
            for partner in full_name.split(" / "):
                partner = partner.strip()
                if partner:
                    self._index_name_parts(partner, event)
            return

        # Normalize the name
        normalized = self.text_processor.normalize_text(full_name)
        parts = normalized.split()

        # Skip team names that look like organizations
        if len(parts) > 3 or any(p in self.TEAM_SUFFIXES for p in parts):
            return

        # For single-word names, treat as last name
        if len(parts) == 1:
            last_name = parts[0]
            if len(last_name) >= self.MIN_WORD_LENGTH:
                self._last_name_index[last_name].append(event)
                self._name_parts[normalized] = ("", last_name)
            return

        # For two-part names like "Amanda Serrano"
        if len(parts) == 2:
            first_name, last_name = parts[0], parts[1]
            if len(last_name) >= self.MIN_WORD_LENGTH:
                self._last_name_index[last_name].append(event)
            if len(first_name) >= self.MIN_WORD_LENGTH:
                self._first_name_index[first_name].append(event)
            self._name_parts[normalized] = (first_name, last_name)
            return

        # For three-part names like "Jake Paul Jr" or "Reina Tellez Garcia"
        # Assume last word is last name, first word is first name
        if len(parts) == 3:
            first_name = parts[0]
            last_name = parts[-1]
            if len(last_name) >= self.MIN_WORD_LENGTH:
                self._last_name_index[last_name].append(event)
            if len(first_name) >= self.MIN_WORD_LENGTH:
                self._first_name_index[first_name].append(event)
            self._name_parts[normalized] = (first_name, last_name)

    # Property accessors for indexes (read-only)

    @property
    def team_index(self) -> Dict[str, List[CalendarEvent]]:
        """Get the team index (read-only)."""
        return self._team_index

    @property
    def event_name_index(self) -> Dict[str, List[CalendarEvent]]:
        """Get the event name index (read-only)."""
        return self._event_name_index

    @property
    def league_index(self) -> Dict[str, List[CalendarEvent]]:
        """Get the league index (read-only)."""
        return self._league_index

    @property
    def word_index(self) -> Dict[str, List[CalendarEvent]]:
        """Get the word index (read-only)."""
        return self._word_index

    @property
    def last_name_index(self) -> Dict[str, List[CalendarEvent]]:
        """Get the last name index (read-only)."""
        return self._last_name_index

    @property
    def first_name_index(self) -> Dict[str, List[CalendarEvent]]:
        """Get the first name index (read-only)."""
        return self._first_name_index

    @property
    def normalized_teams(self) -> Dict[str, str]:
        """Get the normalized teams map (read-only)."""
        return self._normalized_teams

    @property
    def name_parts(self) -> Dict[str, tuple[str, str]]:
        """Get the name parts map (read-only)."""
        return self._name_parts

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the indexes.

        Returns:
            Dict with counts for each index type
        """
        return {
            "teams": len(self._team_index),
            "event_names": len(self._event_name_index),
            "leagues": len(self._league_index),
            "words": len(self._word_index),
            "last_names": len(self._last_name_index),
            "first_names": len(self._first_name_index),
        }
