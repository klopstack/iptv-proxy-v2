# Reverse Event Matcher Decomposition & DRY Analysis

## Executive Summary

The current `ReverseEventMatcher` class (1148 lines) has significant opportunities for decomposition and DRY improvements. The class has multiple responsibilities that could be separated into focused, reusable components.

## Current Problems

### 1. Single Responsibility Violation
The `ReverseEventMatcher` class handles:
- Text normalization and word extraction
- Date extraction from channel names
- Event loading and storage
- Index building and management
- Multiple matching strategies
- Date filtering and confidence boosting
- Result aggregation and ranking

### 2. Code Duplication

**Pattern 1: Similar matching strategy structure**
All `_find_*_matches()` methods follow the same pattern:
```python
def _find_X_matches(self, normalized_channel: str, channel_words: Set[str]) -> List[EventMatch]:
    matches = []
    event_X_matches: Dict[str, Tuple[CalendarEvent, List[str], int]] = {}
    
    for normalized_X, events in self._X_index.items():
        # Check if X appears in channel
        if X in normalized_channel:
            for event in events:
                # Track matches
                event_id = event.event_id
                if event_id not in event_X_matches:
                    event_X_matches[event_id] = (event, [], 0)
                # Update count
                
    # Create EventMatch objects
    for event_id, (event, matched_terms, count) in event_X_matches.items():
        if count >= threshold:
            matches.append(EventMatch(...))
    
    return matches
```

**Pattern 2: Repeated normalization**
- `_normalize_text()` and `_normalize_team_name()` do almost the same thing
- Both strip punctuation, lowercase, and normalize whitespace
- Different only in how they're used (team names vs general text)

**Pattern 3: Index building repetition**
```python
# Repeated 4-5 times in _build_indexes()
if event.X:
    normalized = self._normalize_text(event.X)
    self._X_index[normalized].append(event)
    words = self._extract_significant_words(event.X)
    for word in words:
        self._word_index[word].append(event)
```

**Pattern 4: Date extraction has 3 similar code blocks**
Each date format (ISO, month-day-time, month-day-only) follows:
- Match pattern
- Extract components
- Try to build datetime
- Handle edge cases (year rollover, invalid dates)

## Proposed Decomposition

### Class Hierarchy

```
reverse_event_matcher/
├── __init__.py
├── text_processor.py       # TextProcessor class
├── date_extractor.py       # DateExtractor class
├── event_index.py          # EventIndex class
├── match_strategies.py     # Strategy classes
├── match_filter.py         # MatchFilter class
└── matcher.py              # Main ReverseEventMatcher class (now <200 lines)
```

### 1. TextProcessor Class

**Responsibility:** All text normalization and word extraction

```python
# services/reverse_event_matcher/text_processor.py

import re
from typing import Set

# Pre-compiled regex patterns (module-level)
_COMPILED_PATTERNS = {
    'start_timestamp': re.compile(r'start:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', re.IGNORECASE),
    'stop_timestamp': re.compile(r'stop:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', re.IGNORECASE),
    'multi_timezone': re.compile(
        r'\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+(?:uk|et|pt|ct|mt)'
        r'(?:\s*[/|]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+(?:uk|et|pt|ct|mt))+',
        re.IGNORECASE
    ),
    'timezone_abbr': re.compile(r'\b(?:uk|et|pt|ct|mt|utc|gmt|est|pst|cst|mst)\b', re.IGNORECASE),
    'iso_date': re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}'),
    'time_format': re.compile(r'\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:am|pm))?', re.IGNORECASE),
    'punctuation': re.compile(r'[^\w\s]'),
    'whitespace': re.compile(r'\s+'),
}

STOP_WORDS = {...}  # Move from main file
MIN_WORD_LENGTH = 4

class TextProcessor:
    """Handles text normalization and word extraction with caching."""
    
    def __init__(self):
        self._normalized_cache: Dict[str, str] = {}
        self._words_cache: Dict[str, Set[str]] = {}
    
    def normalize_text(self, text: str, cache_key: Optional[str] = None) -> str:
        """
        Normalize text for matching with optional caching.
        
        Args:
            text: Text to normalize
            cache_key: Optional key for caching (use for repeated operations)
        
        Returns:
            Normalized text
        """
        if cache_key and cache_key in self._normalized_cache:
            return self._normalized_cache[cache_key]
        
        if not text:
            return ""
        
        # Apply pre-compiled patterns efficiently
        result = text
        for pattern in (_COMPILED_PATTERNS['start_timestamp'],
                       _COMPILED_PATTERNS['stop_timestamp'],
                       _COMPILED_PATTERNS['multi_timezone'],
                       _COMPILED_PATTERNS['timezone_abbr'],
                       _COMPILED_PATTERNS['iso_date'],
                       _COMPILED_PATTERNS['time_format']):
            result = pattern.sub('', result)
        
        # Lowercase, remove punctuation, normalize whitespace
        result = result.lower()
        result = _COMPILED_PATTERNS['punctuation'].sub(' ', result)
        result = _COMPILED_PATTERNS['whitespace'].sub(' ', result).strip()
        
        if cache_key:
            self._normalized_cache[cache_key] = result
        
        return result
    
    def extract_significant_words(self, text: str, cache_key: Optional[str] = None) -> Set[str]:
        """
        Extract significant words from text with optional caching.
        
        Args:
            text: Text to extract words from
            cache_key: Optional key for caching
        
        Returns:
            Set of significant words
        """
        if cache_key and cache_key in self._words_cache:
            return self._words_cache[cache_key]
        
        normalized = self.normalize_text(text)
        words = normalized.split()
        
        significant = {
            w for w in words 
            if len(w) >= MIN_WORD_LENGTH and w not in STOP_WORDS
        }
        
        if cache_key:
            self._words_cache[cache_key] = significant
        
        return significant
    
    def clear_cache(self):
        """Clear normalization caches."""
        self._normalized_cache.clear()
        self._words_cache.clear()
```

### 2. DateExtractor Class

**Responsibility:** Extract dates from channel names

```python
# services/reverse_event_matcher/date_extractor.py

import re
from datetime import datetime, timezone
from typing import Optional

# Pre-compiled patterns (module-level)
ISO_DATE_PATTERN = re.compile(
    r"(?:start:|stop:)?(\d{4})[-/](\d{1,2})[-/](\d{1,2})(?:\s+(\d{1,2}):(\d{2}))?",
    re.IGNORECASE,
)
MONTH_DAY_PATTERN = re.compile(
    r"(?:mon|tue|wed|thu|fri|sat|sun)?\s*(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+(\d{1,2}):(\d{2})\s*(am|pm)?",
    re.IGNORECASE,
)
MONTH_DAY_ONLY_PATTERN = re.compile(
    r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)(?:uary|ruary|ch|il|e|y|ust|tember|ober|ember)?\s+(\d{1,2})(?:st|nd|rd|th)?",
    re.IGNORECASE,
)

MONTH_MAP = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

class DateExtractor:
    """Extracts dates from channel names using multiple format patterns."""
    
    def extract_date(self, channel_name: str) -> Optional[datetime]:
        """
        Extract a date/time from a channel name.
        
        Tries multiple formats in order of precision:
        1. ISO format: start:2025-12-14 03:55:00
        2. Month day time: Sat 03 Jan 23:50
        3. Month day only: Oct 18 or December 28
        
        Returns:
            datetime if found, None otherwise
        """
        if not channel_name:
            return None
        
        # Try each format, most specific first
        for extractor in (self._extract_iso_date, 
                         self._extract_month_day_time,
                         self._extract_month_day_only):
            date = extractor(channel_name)
            if date:
                return date
        
        return None
    
    def _extract_iso_date(self, text: str) -> Optional[datetime]:
        """Extract ISO format date: 2025-12-14 03:55:00"""
        match = ISO_DATE_PATTERN.search(text)
        if not match:
            return None
        
        year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
        hour = int(match.group(4)) if match.group(4) else 0
        minute = int(match.group(5)) if match.group(5) else 0
        
        try:
            return datetime(year, month, day, hour, minute)
        except ValueError:
            return None
    
    def _extract_month_day_time(self, text: str) -> Optional[datetime]:
        """Extract month day time format: Sat 03 Jan 23:50"""
        match = MONTH_DAY_PATTERN.search(text)
        if not match:
            return None
        
        day = int(match.group(1))
        month = MONTH_MAP.get(match.group(2).lower()[:3], 1)
        hour = int(match.group(3))
        minute = int(match.group(4))
        ampm = match.group(5)
        
        # Handle AM/PM
        if ampm and ampm.lower() == 'pm' and hour < 12:
            hour += 12
        elif ampm and ampm.lower() == 'am' and hour == 12:
            hour = 0
        
        # Determine year (smart rollover)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        year = now.year
        
        try:
            date = datetime(year, month, day, hour, minute)
            # If date is more than 330 days in the past, assume next year
            if (now - date).days > 330:
                date = datetime(year + 1, month, day, hour, minute)
            return date
        except ValueError:
            return None
    
    def _extract_month_day_only(self, text: str) -> Optional[datetime]:
        """Extract month day only: Oct 18, December 28"""
        match = MONTH_DAY_ONLY_PATTERN.search(text)
        if not match:
            return None
        
        month = MONTH_MAP.get(match.group(1).lower()[:3], 1)
        day = int(match.group(2))
        
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        year = now.year
        
        try:
            date = datetime(year, month, day, 0, 0)
            # Smart year rollover
            if (now - date).days > 330:
                date = datetime(year + 1, month, day, 0, 0)
            return date
        except ValueError:
            return None
```

### 3. EventIndex Class

**Responsibility:** Build and manage all search indexes

```python
# services/reverse_event_matcher/event_index.py

from collections import defaultdict
from typing import Dict, List, Set, Tuple

from services.thesportsdb_calendar_scraper import CalendarEvent
from .text_processor import TextProcessor

MIN_TEAM_NAME_LENGTH = 6

class EventIndex:
    """Manages search indexes for events."""
    
    def __init__(self, text_processor: TextProcessor):
        self.text_processor = text_processor
        
        # Search indexes
        self.team_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self.event_name_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self.league_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self.word_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self.last_name_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        self.first_name_index: Dict[str, List[CalendarEvent]] = defaultdict(list)
        
        # Lookup tables
        self.normalized_teams: Dict[str, str] = {}
        self.name_parts: Dict[str, Tuple[str, str]] = {}
        
        # Cache event words for performance
        self.event_words_cache: Dict[str, Set[str]] = {}
    
    def build_indexes(self, events: List[CalendarEvent]) -> None:
        """Build all search indexes from events."""
        self.clear()
        
        for event in events:
            # Cache event words once
            event_text = f"{event.event_name} {event.home_team or ''} {event.away_team or ''}"
            self.event_words_cache[event.event_id] = self.text_processor.extract_significant_words(event_text)
            
            # Index teams
            if event.home_team:
                self._index_team(event.home_team, event)
            if event.away_team:
                self._index_team(event.away_team, event)
            
            # Index event name
            if event.event_name:
                self._index_event_name(event.event_name, event)
            
            # Index league
            if event.league_name:
                self._index_league(event.league_name, event)
    
    def _index_team(self, team_name: str, event: CalendarEvent) -> None:
        """Index a single team name."""
        normalized = self.text_processor.normalize_text(team_name)
        self.team_index[normalized].append(event)
        self.normalized_teams[normalized] = team_name
        
        # Index name parts for individual sports
        self._index_name_parts(team_name, event)
    
    def _index_event_name(self, event_name: str, event: CalendarEvent) -> None:
        """Index an event name."""
        normalized = self.text_processor.normalize_text(event_name)
        self.event_name_index[normalized].append(event)
        
        # Also index significant words
        words = self.text_processor.extract_significant_words(event_name)
        for word in words:
            self.word_index[word].append(event)
    
    def _index_league(self, league_name: str, event: CalendarEvent) -> None:
        """Index a league name."""
        normalized = self.text_processor.normalize_text(league_name)
        self.league_index[normalized].append(event)
        
        # Also index significant words
        words = self.text_processor.extract_significant_words(league_name)
        for word in words:
            self.word_index[word].append(event)
    
    def _index_name_parts(self, full_name: str, event: CalendarEvent) -> None:
        """
        Index first and last name parts from a person's name.
        Helps match "SERRANO VS TELLEZ" to "Amanda Serrano vs Reina Tellez".
        """
        normalized = self.text_processor.normalize_text(full_name)
        parts = normalized.split()
        
        # Skip organization names
        team_suffixes = {
            "fc", "sc", "cf", "united", "city", "town", "athletic",
            "rovers", "wanderers", "county", "villa", "palace",
            "hotspur", "albion", "university", "state", "college",
        }
        if len(parts) > 3 or any(p in team_suffixes for p in parts):
            return
        
        # Single word: treat as last name
        if len(parts) == 1:
            last_name = parts[0]
            if len(last_name) >= 4:
                self.last_name_index[last_name].append(event)
                self.name_parts[normalized] = ("", last_name)
        
        # Two words: first and last name
        elif len(parts) == 2:
            first_name, last_name = parts[0], parts[1]
            if len(last_name) >= 4:
                self.last_name_index[last_name].append(event)
            if len(first_name) >= 4:
                self.first_name_index[first_name].append(event)
            self.name_parts[normalized] = (first_name, last_name)
        
        # Three words: first word is first name, last word is last name
        elif len(parts) == 3:
            first_name, last_name = parts[0], parts[-1]
            if len(last_name) >= 4:
                self.last_name_index[last_name].append(event)
            if len(first_name) >= 4:
                self.first_name_index[first_name].append(event)
            self.name_parts[normalized] = (first_name, last_name)
    
    def clear(self) -> None:
        """Clear all indexes."""
        self.team_index.clear()
        self.event_name_index.clear()
        self.league_index.clear()
        self.word_index.clear()
        self.last_name_index.clear()
        self.first_name_index.clear()
        self.normalized_teams.clear()
        self.name_parts.clear()
        self.event_words_cache.clear()
    
    def get_stats(self) -> Dict[str, int]:
        """Get statistics about index sizes."""
        return {
            "teams": len(self.team_index),
            "last_names": len(self.last_name_index),
            "event_names": len(self.event_name_index),
            "leagues": len(self.league_index),
            "words": len(self.word_index),
        }
```

### 4. Match Strategies (Abstract Base + Implementations)

**Responsibility:** Encapsulate each matching strategy

```python
# services/reverse_event_matcher/match_strategies.py

from abc import ABC, abstractmethod
from typing import List, Set

from services.thesportsdb_calendar_scraper import CalendarEvent
from .event_index import EventIndex
from .text_processor import TextProcessor

# Confidence thresholds
HIGH_CONFIDENCE = 0.8
MEDIUM_CONFIDENCE = 0.5
LOW_CONFIDENCE = 0.3
MIN_TEAM_NAME_LENGTH = 6

@dataclass
class EventMatch:
    """Represents a potential match between a channel and an event."""
    event: CalendarEvent
    confidence: float
    match_type: str
    matched_terms: List[str] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    channel_date: Optional[datetime] = None
    date_match_boost: float = 0.0

class MatchStrategy(ABC):
    """Abstract base class for matching strategies."""
    
    def __init__(self, index: EventIndex, text_processor: TextProcessor):
        self.index = index
        self.text_processor = text_processor
    
    @abstractmethod
    def find_matches(
        self, 
        normalized_channel: str, 
        channel_words: Set[str],
        seen_event_ids: Set[str]
    ) -> List[EventMatch]:
        """Find matches using this strategy."""
        pass

class TeamMatchStrategy(MatchStrategy):
    """Matches based on team names (highest confidence)."""
    
    def find_matches(
        self, 
        normalized_channel: str, 
        channel_words: Set[str],
        seen_event_ids: Set[str]
    ) -> List[EventMatch]:
        matches = []
        event_team_matches: Dict[str, Tuple[CalendarEvent, List[str], int]] = {}
        
        for normalized_team, events in self.index.team_index.items():
            if len(normalized_team) < MIN_TEAM_NAME_LENGTH:
                continue
            
            # Optimized: use string operations instead of regex
            team_parts = normalized_team.split()
            
            matched = False
            if len(team_parts) == 1:
                # Single word: O(1) set lookup
                matched = team_parts[0] in channel_words
            else:
                # Multi-word: O(n) substring search
                padded_channel = f" {normalized_channel} "
                padded_team = f" {normalized_team} "
                matched = padded_team in padded_channel
            
            if matched:
                for event in events:
                    event_id = event.event_id
                    if event_id not in event_team_matches:
                        event_team_matches[event_id] = (event, [], 0)
                    
                    _, matched_terms, count = event_team_matches[event_id]
                    original_name = self.index.normalized_teams.get(normalized_team, normalized_team)
                    if original_name not in matched_terms:
                        matched_terms.append(original_name)
                        event_team_matches[event_id] = (event, matched_terms, count + 1)
        
        # Create matches
        for event_id, (event, matched_terms, team_count) in event_team_matches.items():
            if team_count >= 2:
                confidence = HIGH_CONFIDENCE + 0.1
                match_type = "both_teams"
            elif team_count == 1:
                confidence = MEDIUM_CONFIDENCE + 0.1
                match_type = "one_team"
            else:
                continue
            
            matches.append(EventMatch(
                event=event,
                confidence=min(confidence, 1.0),
                match_type=match_type,
                matched_terms=matched_terms,
            ))
        
        return matches

class LastNameMatchStrategy(MatchStrategy):
    """Matches based on last names (for boxing, MMA, etc.)."""
    
    def find_matches(
        self, 
        normalized_channel: str, 
        channel_words: Set[str],
        seen_event_ids: Set[str]
    ) -> List[EventMatch]:
        matches = []
        event_name_matches: Dict[str, Tuple[CalendarEvent, List[str], int]] = {}
        
        for last_name, events in self.index.last_name_index.items():
            if len(last_name) < 4:
                continue
            
            # Check if last name appears in channel
            if last_name in channel_words or last_name in normalized_channel.split():
                for event in events:
                    event_id = event.event_id
                    if event_id not in event_name_matches:
                        event_name_matches[event_id] = (event, [], 0)
                    
                    _, matched_terms, count = event_name_matches[event_id]
                    if last_name not in matched_terms:
                        matched_terms.append(last_name)
                        event_name_matches[event_id] = (event, matched_terms, count + 1)
        
        # Create matches based on name count
        for event_id, (event, matched_terms, name_count) in event_name_matches.items():
            if name_count >= 2:
                confidence = HIGH_CONFIDENCE - 0.1
                match_type = "both_last_names"
            elif name_count == 1:
                confidence = MEDIUM_CONFIDENCE
                match_type = "one_last_name"
            else:
                continue
            
            matches.append(EventMatch(
                event=event,
                confidence=min(confidence, 1.0),
                match_type=match_type,
                matched_terms=matched_terms,
                details={"last_name_count": name_count},
            ))
        
        return matches

class EventNameMatchStrategy(MatchStrategy):
    """Matches based on event names (using token overlap, not fuzzy matching)."""
    
    def find_matches(
        self, 
        normalized_channel: str, 
        channel_words: Set[str],
        seen_event_ids: Set[str]
    ) -> List[EventMatch]:
        matches = []
        
        if len(normalized_channel) < 15:
            return matches
        
        for normalized_event_name, events in self.index.event_name_index.items():
            if len(normalized_event_name) < 15:
                continue
            
            # Strategy 1: Exact substring match (highest confidence)
            if normalized_event_name in normalized_channel:
                for event in events:
                    matches.append(EventMatch(
                        event=event,
                        confidence=HIGH_CONFIDENCE,
                        match_type="event_name_exact",
                        matched_terms=[event.event_name],
                        details={"match_type": "substring"},
                    ))
                continue
            
            # Strategy 2: Token-based matching (replaces fuzzy matching)
            event_words = self.text_processor.extract_significant_words(normalized_event_name)
            common_words = event_words & channel_words
            
            if len(common_words) >= 3:
                overlap_ratio = len(common_words) / len(event_words) if event_words else 0
                
                if overlap_ratio >= 0.6:  # 60% of event name words present
                    for event in events:
                        confidence = MEDIUM_CONFIDENCE + (overlap_ratio * 0.2)
                        matches.append(EventMatch(
                            event=event,
                            confidence=min(confidence, HIGH_CONFIDENCE - 0.1),
                            match_type="event_name_tokens",
                            matched_terms=[event.event_name],
                            details={
                                "word_overlap": overlap_ratio,
                                "common_words": len(common_words)
                            },
                        ))
        
        return matches

class LeagueMatchStrategy(MatchStrategy):
    """Matches based on league name + additional context."""
    
    def find_matches(
        self, 
        normalized_channel: str, 
        channel_words: Set[str],
        seen_event_ids: Set[str]
    ) -> List[EventMatch]:
        matches = []
        
        for normalized_league, events in self.index.league_index.items():
            if normalized_league not in normalized_channel:
                continue
            
            for event in events:
                # Use cached event words
                event_words = self.index.event_words_cache.get(event.event_id, set())
                common_words = channel_words & event_words
                
                # Require at least 2 common words
                if len(common_words) >= 2:
                    word_overlap = len(common_words) / max(len(channel_words), 1)
                    confidence = MEDIUM_CONFIDENCE + (word_overlap * 0.3)
                    
                    matches.append(EventMatch(
                        event=event,
                        confidence=min(confidence, HIGH_CONFIDENCE),
                        match_type="league",
                        matched_terms=[event.league_name] + list(common_words),
                        details={"word_overlap": word_overlap},
                    ))
        
        return matches

class WordMatchStrategy(MatchStrategy):
    """Fallback: matches based on significant word overlap."""
    
    def find_matches(
        self, 
        normalized_channel: str, 
        channel_words: Set[str],
        seen_event_ids: Set[str]
    ) -> List[EventMatch]:
        matches = []
        
        if len(channel_words) < 2:
            return matches
        
        event_word_counts: Dict[str, Tuple[CalendarEvent, Set[str]]] = {}
        
        for word in channel_words:
            if word in self.index.word_index:
                for event in self.index.word_index[word]:
                    if event.event_id in seen_event_ids:
                        continue
                    
                    if event.event_id not in event_word_counts:
                        event_word_counts[event.event_id] = (event, set())
                    
                    event_word_counts[event.event_id][1].add(word)
        
        # Require at least 3 significant words
        for event_id, (event, matched_words) in event_word_counts.items():
            if len(matched_words) >= 3:
                confidence = LOW_CONFIDENCE + (len(matched_words) * 0.08)
                matches.append(EventMatch(
                    event=event,
                    confidence=min(confidence, MEDIUM_CONFIDENCE - 0.1),
                    match_type="fuzzy",
                    matched_terms=list(matched_words),
                ))
        
        return matches
```

### 5. MatchFilter Class

**Responsibility:** Date filtering and confidence boosting

```python
# services/reverse_event_matcher/match_filter.py

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional, Tuple

from services.thesportsdb_calendar_scraper import CalendarEvent
from .match_strategies import EventMatch

class DateFilter(Enum):
    """Filter options for event dates when matching."""
    ALL = "all"
    UPCOMING_ONLY = "upcoming_only"
    RECENT_AND_UPCOMING = "recent_and_upcoming"
    CURRENT_WEEK = "current_week"

class MatchFilter:
    """Filters and boosts match confidence based on dates."""
    
    def apply_date_filters(
        self,
        match: EventMatch,
        channel_date: Optional[datetime],
        date_filter: DateFilter,
        now: Optional[datetime] = None,
    ) -> Optional[EventMatch]:
        """
        Apply date filtering and confidence boosting.
        
        Returns None if match should be filtered out, otherwise returns
        the match (possibly with confidence boost applied).
        """
        if now is None:
            now = datetime.now(timezone.utc)
        
        event_date = match.event.scheduled_at
        
        # Apply channel date matching first
        if channel_date is not None and event_date is not None:
            date_matches, date_boost = self._check_date_match(channel_date, event_date)
            if not date_matches:
                return None
            if date_boost > 0:
                match.date_match_boost = date_boost
                match.confidence = min(match.confidence + date_boost, 1.0)
                match.channel_date = channel_date
        
        # Apply date range filter
        if event_date is not None:
            if not self._passes_date_range_filter(event_date, date_filter, now):
                return None
        
        return match
    
    def _check_date_match(
        self, 
        channel_date: datetime, 
        event_date: datetime,
        tolerance_hours: int = 48
    ) -> Tuple[bool, float]:
        """
        Check if channel date matches event date.
        
        Returns:
            Tuple of (matches: bool, confidence_boost: float)
        """
        # Normalize timezones
        if channel_date.tzinfo is None:
            channel_date = channel_date.replace(tzinfo=timezone.utc)
        if event_date.tzinfo is None:
            event_date = event_date.replace(tzinfo=timezone.utc)
        
        diff_hours = abs((channel_date - event_date).total_seconds() / 3600)
        
        if diff_hours <= 6:
            return (True, 0.15)  # Very close match
        elif diff_hours <= tolerance_hours:
            return (True, 0.05)  # Within tolerance
        else:
            return (False, 0.0)  # Outside tolerance
    
    def _passes_date_range_filter(
        self, 
        event_date: datetime, 
        date_filter: DateFilter,
        now: datetime
    ) -> bool:
        """Check if event passes the date range filter."""
        # Normalize timezone
        event_date_utc = event_date
        if event_date.tzinfo is None:
            event_date_utc = event_date.replace(tzinfo=timezone.utc)
        
        if date_filter == DateFilter.ALL:
            return True
        elif date_filter == DateFilter.UPCOMING_ONLY:
            min_date = now - timedelta(hours=3)  # Allow in-progress events
            return event_date_utc >= min_date
        elif date_filter == DateFilter.RECENT_AND_UPCOMING:
            min_date = now - timedelta(days=7)
            return event_date_utc >= min_date
        elif date_filter == DateFilter.CURRENT_WEEK:
            min_date = now - timedelta(days=3)
            max_date = now + timedelta(days=7)
            return min_date <= event_date_utc <= max_date
        
        return True
```

### 6. Simplified Main Class

**Responsibility:** Orchestrate components and expose public API

```python
# services/reverse_event_matcher/matcher.py

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from services.thesportsdb_calendar_scraper import CalendarEvent, TheSportsDBCalendarScraper

from .date_extractor import DateExtractor
from .event_index import EventIndex
from .match_filter import DateFilter, MatchFilter
from .match_strategies import (
    EventMatch,
    EventNameMatchStrategy,
    LastNameMatchStrategy,
    LeagueMatchStrategy,
    TeamMatchStrategy,
    WordMatchStrategy,
)
from .text_processor import TextProcessor

logger = logging.getLogger(__name__)

class ReverseEventMatcher:
    """
    Matches PPV channel names to known sports events using reverse lookup.
    
    This is the main orchestrator that coordinates:
    - Text processing (normalization, word extraction)
    - Date extraction from channel names
    - Event indexing
    - Multiple matching strategies
    - Date filtering and confidence boosting
    """
    
    def __init__(self, calendar_scraper: Optional[TheSportsDBCalendarScraper] = None):
        """Initialize the reverse matcher with optional scraper."""
        self._scraper = calendar_scraper
        self._events: List[CalendarEvent] = []
        self._events_loaded = False
        self._load_date_range: Optional[Tuple[str, str]] = None
        
        # Initialize components
        self.text_processor = TextProcessor()
        self.date_extractor = DateExtractor()
        self.index = EventIndex(self.text_processor)
        self.match_filter = MatchFilter()
        
        # Initialize matching strategies
        self.strategies = [
            TeamMatchStrategy(self.index, self.text_processor),
            LastNameMatchStrategy(self.index, self.text_processor),
            EventNameMatchStrategy(self.index, self.text_processor),
            LeagueMatchStrategy(self.index, self.text_processor),
            WordMatchStrategy(self.index, self.text_processor),
        ]
    
    @property
    def scraper(self) -> TheSportsDBCalendarScraper:
        """Get or create the calendar scraper."""
        if self._scraper is None:
            from services.thesportsdb_calendar_scraper import get_calendar_scraper
            self._scraper = get_calendar_scraper()
        return self._scraper
    
    def load_events_for_date_range(
        self,
        start_date: Optional[datetime] = None,
        days_ahead: int = 14,
        days_back: int = 21,
        sports: Optional[List[str]] = None,
    ) -> int:
        """Load calendar events and build search indexes."""
        if start_date is None:
            start_date = datetime.now(timezone.utc)
        
        actual_start = start_date - timedelta(days=days_back)
        end_date = start_date + timedelta(days=days_ahead)
        
        start_str = actual_start.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")
        
        logger.info(
            f"Loading calendar events from {start_str} to {end_str} "
            f"({days_back} days back, {days_ahead} days ahead)"
        )
        
        # Clear existing data
        self._events = []
        self.text_processor.clear_cache()
        
        # Load events for each day
        current = actual_start
        sport_filter = sports[0] if sports and len(sports) == 1 else ""
        
        while current <= end_date:
            date_str = current.strftime("%Y-%m-%d")
            try:
                day_events = self.scraper.get_events_for_date(date_str, sport=sport_filter)
                self._events.extend(day_events)
            except Exception as e:
                logger.warning(f"Failed to load events for {date_str}: {e}")
            
            current += timedelta(days=1)
        
        # Build indexes
        self.index.build_indexes(self._events)
        
        self._events_loaded = True
        self._load_date_range = (start_str, end_str)
        
        stats = self.index.get_stats()
        logger.info(
            f"Loaded {len(self._events)} total events, "
            f"indexed {stats['teams']} teams, {stats['last_names']} last names, "
            f"{stats['event_names']} event names, {stats['leagues']} leagues, "
            f"{stats['words']} words"
        )
        
        return len(self._events)
    
    def find_matches(
        self,
        channel_name: str,
        max_results: int = 5,
        min_confidence: float = 0.3,
        date_filter: DateFilter = DateFilter.RECENT_AND_UPCOMING,
        use_channel_date: bool = True,
    ) -> List[EventMatch]:
        """
        Find events that match the given channel name.
        
        This is the main entry point for matching.
        """
        if not self._events_loaded:
            logger.warning("No events loaded. Call load_events_for_date_range() first.")
            return []
        
        if not channel_name or self._is_generic_channel(channel_name):
            return []
        
        # Pre-process channel name once (cached)
        cache_key = channel_name
        normalized_channel = self.text_processor.normalize_text(channel_name, cache_key)
        channel_words = self.text_processor.extract_significant_words(channel_name, cache_key)
        
        # Extract date if present
        channel_date = self.date_extractor.extract_date(channel_name) if use_channel_date else None
        
        # Run all matching strategies
        matches: List[EventMatch] = []
        seen_event_ids: Set[str] = set()
        now = datetime.now(timezone.utc)
        
        for strategy in self.strategies:
            strategy_matches = strategy.find_matches(normalized_channel, channel_words, seen_event_ids)
            
            # Apply date filtering to each match
            for match in strategy_matches:
                if match.event.event_id in seen_event_ids:
                    continue
                
                filtered_match = self.match_filter.apply_date_filters(
                    match, channel_date, date_filter, now
                )
                
                if filtered_match:
                    matches.append(filtered_match)
                    seen_event_ids.add(match.event.event_id)
            
            # Early termination: if we have enough high-confidence matches, stop
            if len(matches) >= max_results:
                high_conf_matches = [m for m in matches if m.confidence >= 0.8]
                if len(high_conf_matches) >= max_results:
                    break
        
        # Filter by minimum confidence and sort
        matches = [m for m in matches if m.confidence >= min_confidence]
        matches.sort(key=lambda m: m.confidence, reverse=True)
        
        return matches[:max_results]
    
    def _is_generic_channel(self, channel_name: str) -> bool:
        """Detect generic channels that have no event information."""
        name_lower = channel_name.lower().strip()
        
        if len(name_lower) < 5:
            return True
        
        # Network-only patterns
        network_patterns = [
            r'^\w{2,3}\s*[:|]\s*(?:nfl|nba|nhl|mlb|mls)\s+(?:network|tv|redzone)',
            r'^(?:nfl|nba|nhl|mlb|mls)\s+(?:network|tv|redzone)',
            r'^\w{2,3}\s*[:|]\s*(?:espn|fox|paramount)\+?\s*\d*\s*$',
        ]
        
        import re
        for pattern in network_patterns:
            if re.search(pattern, name_lower):
                return True
        
        if re.match(r'^:?(?:milb|mlb|nba|nhl|nfl|ncaaf|ncaab)\s+\d+\s*:?\s*$', name_lower):
            return True
        
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded events and indexes."""
        now = datetime.now(timezone.utc)
        past_events = sum(1 for e in self._events if e.scheduled_at and e.scheduled_at < now)
        future_events = len(self._events) - past_events
        
        return {
            "events_loaded": len(self._events),
            "past_events": past_events,
            "future_events": future_events,
            "date_range": self._load_date_range,
            **self.index.get_stats(),
        }
    
    # Convenience methods for backwards compatibility
    def get_all_teams(self) -> List[str]:
        """Get all indexed team names."""
        return [self.index.normalized_teams.get(k, k) for k in sorted(self.index.team_index.keys())]
    
    def get_all_leagues(self) -> List[str]:
        """Get all indexed league names."""
        return sorted(self.index.league_index.keys())
    
    def get_events_for_teams(self, team1: str, team2: Optional[str] = None) -> List[CalendarEvent]:
        """Get all events involving specific teams."""
        results = []
        norm_team1 = self.text_processor.normalize_text(team1)
        
        for event in self._events:
            norm_home = self.text_processor.normalize_text(event.home_team or "")
            norm_away = self.text_processor.normalize_text(event.away_team or "")
            
            if norm_team1 in (norm_home, norm_away):
                if team2 is None:
                    results.append(event)
                else:
                    norm_team2 = self.text_processor.normalize_text(team2)
                    if norm_team2 in (norm_home, norm_away):
                        results.append(event)
        
        return results

# Module-level singleton
_matcher_instance: Optional[ReverseEventMatcher] = None

def get_reverse_matcher() -> ReverseEventMatcher:
    """Get or create the global reverse matcher instance."""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = ReverseEventMatcher()
    return _matcher_instance
```

### 7. Package __init__.py

```python
# services/reverse_event_matcher/__init__.py

from .date_extractor import DateExtractor
from .event_index import EventIndex
from .match_filter import DateFilter, MatchFilter
from .match_strategies import (
    EventMatch,
    EventNameMatchStrategy,
    LastNameMatchStrategy,
    LeagueMatchStrategy,
    MatchStrategy,
    TeamMatchStrategy,
    WordMatchStrategy,
)
from .matcher import ReverseEventMatcher, get_reverse_matcher
from .text_processor import TextProcessor

__all__ = [
    # Main classes
    "ReverseEventMatcher",
    "get_reverse_matcher",
    # Components
    "TextProcessor",
    "DateExtractor",
    "EventIndex",
    "MatchFilter",
    # Strategies
    "MatchStrategy",
    "TeamMatchStrategy",
    "LastNameMatchStrategy",
    "EventNameMatchStrategy",
    "LeagueMatchStrategy",
    "WordMatchStrategy",
    # Data classes
    "EventMatch",
    "DateFilter",
]
```

## Benefits of This Decomposition

### 1. **Single Responsibility**
Each class has one clear purpose:
- `TextProcessor`: Text normalization
- `DateExtractor`: Date extraction
- `EventIndex`: Index management
- `MatchStrategy` classes: Specific matching logic
- `MatchFilter`: Date filtering
- `ReverseEventMatcher`: Orchestration

### 2. **DRY (Don't Repeat Yourself)**
- Text normalization centralized in `TextProcessor` with caching
- Index building pattern extracted to `EventIndex`
- Date extraction logic separated and reusable
- Matching pattern abstracted in `MatchStrategy` base class

### 3. **Testability**
Each component can be tested in isolation:
```python
def test_text_processor():
    processor = TextProcessor()
    assert processor.normalize_text("US: FOX 123") == "us fox 123"

def test_team_match_strategy():
    processor = TextProcessor()
    index = EventIndex(processor)
    index.build_indexes([sample_event])
    
    strategy = TeamMatchStrategy(index, processor)
    matches = strategy.find_matches("lakers vs celtics", {"lakers", "celtics"}, set())
    assert len(matches) == 1
```

### 4. **Extensibility**
- Add new matching strategies by subclassing `MatchStrategy`
- Swap out text processor or date extractor implementations
- Add new index types without modifying existing code

### 5. **Performance**
- Caching centralized in components that need it
- Pre-compiled regex patterns in module scope
- Event words cached during index building
- Text normalized once at entry point

### 6. **Maintainability**
- Each file is 100-250 lines (vs 1148 lines monolith)
- Clear interfaces between components
- Easy to locate and fix bugs
- Self-documenting structure

## Migration Strategy

1. **Phase 1:** Create new package structure alongside existing file
2. **Phase 2:** Implement and test each component individually
3. **Phase 3:** Implement main `ReverseEventMatcher` using new components
4. **Phase 4:** Update imports in dependent code
5. **Phase 5:** Remove old `reverse_event_matcher.py` file

## Testing Strategy

```python
# tests/test_reverse_event_matcher/
test_text_processor.py
test_date_extractor.py
test_event_index.py
test_match_strategies.py
test_match_filter.py
test_matcher_integration.py  # End-to-end tests
```

Each component test file validates:
- Correctness of core functionality
- Edge cases and error handling
- Performance characteristics
- Integration with dependencies

## Summary

This decomposition transforms a 1148-line monolithic class into:
- **6 focused classes** (~100-250 lines each)
- **Clear separation of concerns**
- **Extensive DRY improvements**
- **Better testability and maintainability**
- **Improved performance through caching and optimization**

The architecture follows SOLID principles and makes the codebase significantly easier to understand, test, and extend.
