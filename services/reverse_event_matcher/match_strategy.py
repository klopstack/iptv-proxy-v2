"""
Match Strategy Components

Defines different matching strategies for finding calendar events based on
channel names. Each strategy uses the EventIndex to find candidates and
calculates confidence scores.

This replaces the monolithic matching logic with composable strategies,
making it easier to tune and test different matching approaches.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Set, Tuple

from services.thesportsdb_calendar_scraper import CalendarEvent

if TYPE_CHECKING:
    from .event_index import EventIndex

# Confidence thresholds (aligned with original implementation)
HIGH_CONFIDENCE = 0.85
MEDIUM_CONFIDENCE = 0.65
LOW_CONFIDENCE = 0.45

# Minimum team name length to avoid false positives
MIN_TEAM_NAME_LENGTH = 5


@dataclass
class MatchResult:
    """
    Result from a matching strategy.

    Attributes:
        event: The matched calendar event
        confidence: Match confidence score (0.0-1.0)
        match_type: Type of match (e.g., "both_teams", "last_name")
        matched_terms: List of terms that matched (for debugging/display)
        details: Additional match metadata
    """

    event: CalendarEvent
    confidence: float
    match_type: str
    matched_terms: List[str]
    details: dict


class BaseMatchStrategy(ABC):
    """
    Base class for event matching strategies.

    Each strategy knows how to:
    1. Find candidate events from the EventIndex
    2. Calculate confidence scores for matches
    3. Return MatchResult objects
    """

    @abstractmethod
    def find_matches(
        self,
        normalized_channel: str,
        channel_words: Set[str],
        event_index: EventIndex,
    ) -> List[MatchResult]:
        """
        Find matching events using this strategy.

        Args:
            normalized_channel: Normalized channel name text
            channel_words: Set of significant words from channel
            event_index: EventIndex to search

        Returns:
            List of MatchResult objects
        """
        pass


class TeamMatchStrategy(BaseMatchStrategy):
    """
    Matches based on team names (both teams or single team).

    Examples:
    - "Lakers vs Celtics" → finds events with both teams (HIGH_CONFIDENCE)
    - "Lakers Game" → finds events with Lakers (MEDIUM_CONFIDENCE)
    """

    def find_matches(
        self,
        normalized_channel: str,
        channel_words: Set[str],
        event_index: EventIndex,
    ) -> List[MatchResult]:
        """Find matches based on team names."""
        matches = []

        # Build a map of events to their team match count
        event_team_matches: dict[str, Tuple[CalendarEvent, List[str], int]] = {}

        for normalized_team, events in event_index.team_index.items():
            # Skip short team names to avoid false positives (e.g., "Bra", "Cal")
            if len(normalized_team) < MIN_TEAM_NAME_LENGTH:
                continue

            # Check if team name appears in channel as a whole word/phrase
            # Use word boundary matching to avoid partial matches
            pattern = r"\b" + re.escape(normalized_team) + r"\b"
            if re.search(pattern, normalized_channel):
                for event in events:
                    event_id = event.event_id
                    if event_id not in event_team_matches:
                        event_team_matches[event_id] = (event, [], 0)

                    _, matched_terms, count = event_team_matches[event_id]
                    original_name = event_index.normalized_teams.get(normalized_team, normalized_team)
                    if original_name not in matched_terms:
                        matched_terms.append(original_name)
                        event_team_matches[event_id] = (event, matched_terms, count + 1)

        # Create matches based on how many teams were found
        for event_id, (event, matched_terms, team_count) in event_team_matches.items():
            if team_count >= 2:
                # Both teams found - high confidence
                confidence = min(HIGH_CONFIDENCE + 0.1, 1.0)
                match_type = "both_teams"
            elif team_count == 1:
                # One team found - medium confidence
                confidence = MEDIUM_CONFIDENCE + 0.1
                match_type = "one_team"
            else:
                continue

            matches.append(
                MatchResult(
                    event=event,
                    confidence=confidence,
                    match_type=match_type,
                    matched_terms=matched_terms,
                    details={"team_count": team_count},
                )
            )

        return matches


class LastNameMatchStrategy(BaseMatchStrategy):
    """
    Matches based on last names (for individual sports like boxing, MMA).

    Examples:
    - "SERRANO VS TELLEZ" → matches "Amanda Serrano vs Reina Tellez"
    - "Paul Fury Boxing" → matches "Jake Paul vs Tommy Fury"
    """

    def find_matches(
        self,
        normalized_channel: str,
        channel_words: Set[str],
        event_index: EventIndex,
    ) -> List[MatchResult]:
        """Find matches based on last names."""
        matches = []

        # Build a map of events to their last name match count
        event_name_matches: dict[str, Tuple[CalendarEvent, List[str], int]] = {}

        for last_name, events in event_index.last_name_index.items():
            # Last names must be at least 4 chars
            if len(last_name) < 4:
                continue

            # Check if last name appears in channel as a whole word
            if last_name in channel_words or last_name in normalized_channel.split():
                for event in events:
                    event_id = event.event_id
                    if event_id not in event_name_matches:
                        event_name_matches[event_id] = (event, [], 0)

                    _, matched_terms, count = event_name_matches[event_id]
                    if last_name not in matched_terms:
                        matched_terms.append(last_name)
                        event_name_matches[event_id] = (event, matched_terms, count + 1)

        # Create matches based on how many last names were found
        for event_id, (event, matched_terms, name_count) in event_name_matches.items():
            if name_count >= 2:
                # Both last names found - high confidence for individual sports
                confidence = HIGH_CONFIDENCE
                match_type = "both_last_names"
            elif name_count == 1:
                # One last name found - lower confidence (could be coincidence)
                confidence = LOW_CONFIDENCE + 0.1
                match_type = "one_last_name"
            else:
                continue

            matches.append(
                MatchResult(
                    event=event,
                    confidence=confidence,
                    match_type=match_type,
                    matched_terms=matched_terms,
                    details={"last_name_count": name_count},
                )
            )

        return matches


class EventNameMatchStrategy(BaseMatchStrategy):
    """
    Matches based on event names using token-based similarity.

    Replaces expensive SequenceMatcher with token overlap calculation.

    Examples:
    - "UFC 300 Main Card" → matches event "UFC 300"
    - "Premier League Final" → matches event "Premier League Championship Final"
    """

    def find_matches(
        self,
        normalized_channel: str,
        channel_words: Set[str],
        event_index: EventIndex,
    ) -> List[MatchResult]:
        """Find matches based on event names using token similarity."""
        matches: List[MatchResult] = []

        # Skip if channel is too short (likely placeholder)
        if len(normalized_channel) < 15:
            return matches

        channel_tokens = set(normalized_channel.split())

        for normalized_event_name, events in event_index.event_name_index.items():
            # Only check event names of reasonable length
            if len(normalized_event_name) < 15:
                continue

            # First check: Does event name appear as substring in channel?
            if normalized_event_name in normalized_channel:
                for event in events:
                    matches.append(
                        MatchResult(
                            event=event,
                            confidence=HIGH_CONFIDENCE,
                            match_type="event_name_exact",
                            matched_terms=[event.event_name],
                            details={"match_type": "substring"},
                        )
                    )
                continue

            # Second check: Token-based similarity (replaces SequenceMatcher)
            # Only for longer event names (to avoid random matches)
            if len(normalized_event_name) >= 25:
                event_tokens = set(normalized_event_name.split())

                # Calculate Jaccard similarity (intersection / union)
                if event_tokens and channel_tokens:
                    intersection = len(event_tokens & channel_tokens)
                    union = len(event_tokens | channel_tokens)
                    similarity = intersection / union if union > 0 else 0.0

                    # Require reasonable overlap
                    if similarity > 0.4:  # Token similarity threshold
                        for event in events:
                            confidence = min(similarity * 1.5, MEDIUM_CONFIDENCE + 0.1)
                            matches.append(
                                MatchResult(
                                    event=event,
                                    confidence=confidence,
                                    match_type="event_name_tokens",
                                    matched_terms=[event.event_name],
                                    details={
                                        "token_similarity": similarity,
                                        "matched_tokens": list(event_tokens & channel_tokens),
                                    },
                                )
                            )

        return matches


class LeagueMatchStrategy(BaseMatchStrategy):
    """
    Matches based on league name plus significant words.

    Examples:
    - "NBA Finals Lakers" → matches NBA events with "Lakers" or "Finals"
    - "UFC 300" → matches UFC events
    """

    def find_matches(
        self,
        normalized_channel: str,
        channel_words: Set[str],
        event_index: EventIndex,
    ) -> List[MatchResult]:
        """Find matches based on league name plus significant words."""
        matches: List[MatchResult] = []

        # Find leagues mentioned in channel
        matched_leagues: List[Tuple[str, List[CalendarEvent]]] = []

        for league_name, events in event_index.league_index.items():
            # Check if league appears in channel
            pattern = r"\b" + re.escape(league_name) + r"\b"
            if re.search(pattern, normalized_channel):
                matched_leagues.append((league_name, events))

        # If no league matches, return empty
        if not matched_leagues:
            return matches

        # For each league, find events with overlapping significant words
        for league_name, events in matched_leagues:
            for event in events:
                # Get significant words from this event
                event_words = event_index.word_index
                event_significant_words = set()

                # Find which words in word_index contain this event
                for word, word_events in event_words.items():
                    if event in word_events:
                        event_significant_words.add(word)

                # Calculate word overlap
                word_overlap = channel_words & event_significant_words
                overlap_count = len(word_overlap)

                if overlap_count >= 2:
                    # League + 2+ words - medium confidence
                    confidence = MEDIUM_CONFIDENCE
                    match_type = "league_plus_words"
                elif overlap_count == 1:
                    # League + 1 word - low confidence
                    confidence = LOW_CONFIDENCE + 0.1
                    match_type = "league_plus_word"
                else:
                    # Just league - very low confidence (too generic)
                    confidence = LOW_CONFIDENCE
                    match_type = "league_only"

                matched_terms = [league_name] + list(word_overlap)

                matches.append(
                    MatchResult(
                        event=event,
                        confidence=confidence,
                        match_type=match_type,
                        matched_terms=matched_terms,
                        details={"word_overlap_count": overlap_count},
                    )
                )

        return matches


class WordMatchStrategy(BaseMatchStrategy):
    """
    Fallback strategy: matches based on significant word overlap.

    Used when other strategies don't find strong matches.
    Lower confidence than team/name-based strategies.

    Examples:
    - "Final Championship Game" → matches events with these words
    """

    def find_matches(
        self,
        normalized_channel: str,
        channel_words: Set[str],
        event_index: EventIndex,
    ) -> List[MatchResult]:
        """Find matches based on significant word overlap."""
        matches: List[MatchResult] = []

        # Build event word match counts
        event_word_matches: dict[str, Tuple[CalendarEvent, Set[str], int]] = {}

        for word in channel_words:
            if word in event_index.word_index:
                for event in event_index.word_index[word]:
                    event_id = event.event_id
                    if event_id not in event_word_matches:
                        event_word_matches[event_id] = (event, set(), 0)

                    _, matched_words, count = event_word_matches[event_id]
                    matched_words.add(word)
                    event_word_matches[event_id] = (event, matched_words, count + 1)

        # Create matches for events with sufficient word overlap
        for event_id, (event, matched_words, word_count) in event_word_matches.items():
            # Require at least 2 matching words for this low-specificity strategy
            if word_count >= 2:
                # Calculate confidence based on overlap ratio
                total_words = len(channel_words)
                overlap_ratio = word_count / total_words if total_words > 0 else 0.0

                # Scale confidence: 2+ words = LOW_CONFIDENCE, more words = higher
                confidence = min(LOW_CONFIDENCE + (overlap_ratio * 0.2), MEDIUM_CONFIDENCE)

                matches.append(
                    MatchResult(
                        event=event,
                        confidence=confidence,
                        match_type="word_overlap",
                        matched_terms=list(matched_words),
                        details={"word_count": word_count, "overlap_ratio": overlap_ratio},
                    )
                )

        return matches
