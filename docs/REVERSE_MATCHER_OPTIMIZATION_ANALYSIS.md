# Reverse Event Matcher Optimization Analysis

## Executive Summary

Analysis of `services/reverse_event_matcher.py` reveals several optimization opportunities. The primary bottleneck is fuzzy matching (SequenceMatcher), which is only used in one location but applied to many event names. Additional optimizations can reduce unnecessary work across all matching strategies.

## Current Performance Characteristics

**Strengths:**
- Trustworthy, consistent calendar data format
- Multiple matching strategies with confidence scoring
- Effective use of indexes for fast lookups

**Bottlenecks:**
1. Fuzzy matching with `SequenceMatcher` (line 990)
2. Multiple regex operations in `_normalize_text()` (7+ regex calls per invocation)
3. Redundant text normalization (same channel normalized multiple times)
4. Expensive word extraction for league matching
5. Regex compilation on every team name match (line 921)

## High-Impact Optimizations

### 1. **Eliminate Most Fuzzy Matching** ⭐ HIGHEST IMPACT

**Current Issue:**
- Line 990: `SequenceMatcher` is called for every event name ≥25 chars
- This is O(n*m) complexity where n=event_name_length, m=channel_length
- Runs even when exact substring matching already failed

**Solution:**
Since calendar data is trustworthy and consistent, we can use **token-based matching** instead:

```python
def _find_event_name_matches(self, normalized_channel: str, channel_words: Set[str]) -> List[EventMatch]:
    """Find matches based on event names."""
    matches: List[EventMatch] = []
    
    # Skip if channel is too short (likely placeholder)
    if len(normalized_channel) < 15:
        return matches
    
    for normalized_event_name, events in self._event_name_index.items():
        # Only check event names of reasonable length
        if len(normalized_event_name) < 15:
            continue
        
        # First check: Does event name appear as substring in channel?
        if normalized_event_name in normalized_channel:
            for event in events:
                matches.append(
                    EventMatch(
                        event=event,
                        confidence=HIGH_CONFIDENCE,
                        match_type="event_name_exact",
                        matched_terms=[event.event_name],
                        details={"match_type": "substring"},
                    )
                )
            continue
        
        # Second check: Token-based matching (replaces fuzzy matching)
        # Extract significant words from event name
        event_words = self._extract_significant_words(normalized_event_name)
        
        # Calculate word overlap
        common_words = event_words & channel_words
        if len(common_words) >= 3:  # Require at least 3 common words
            overlap_ratio = len(common_words) / len(event_words) if event_words else 0
            
            if overlap_ratio >= 0.6:  # 60% of event name words present
                for event in events:
                    confidence = MEDIUM_CONFIDENCE + (overlap_ratio * 0.2)
                    matches.append(
                        EventMatch(
                            event=event,
                            confidence=min(confidence, HIGH_CONFIDENCE - 0.1),
                            match_type="event_name_tokens",
                            matched_terms=[event.event_name],
                            details={"word_overlap": overlap_ratio, "common_words": len(common_words)},
                        )
                    )
    
    return matches
```

**Impact:** Eliminates O(n*m) fuzzy matching, replaces with O(n) set intersection
**Expected Speedup:** 10-50x for event name matching phase

### 2. **Cache Normalized Text and Words** ⭐ HIGH IMPACT

**Current Issue:**
- `_normalize_text()` called multiple times on same channel name
- `_extract_significant_words()` called multiple times
- Each call performs 7+ regex operations

**Solution:**
Add caching at the `find_matches()` entry point:

```python
def find_matches(
    self,
    channel_name: str,
    max_results: int = 5,
    min_confidence: float = LOW_CONFIDENCE,
    date_filter: DateFilter = DateFilter.RECENT_AND_UPCOMING,
    use_channel_date: bool = True,
) -> List[EventMatch]:
    """Find events that match the given channel name."""
    if not self._events_loaded:
        logger.warning("No events loaded. Call load_events_for_date_range() first.")
        return []
    
    if not channel_name:
        return []
    
    # Skip generic channels that have no event information
    if self._is_generic_channel(channel_name):
        logger.debug(f"Skipping generic channel: {channel_name[:50]}")
        return []
    
    # OPTIMIZATION: Normalize once and reuse
    normalized_channel = self._normalize_text(channel_name)
    channel_words = self._extract_significant_words(channel_name)  # Uses cached normalization internally
    
    matches: List[EventMatch] = []
    seen_event_ids: Set[str] = set()
    
    # Extract date from channel name if present
    channel_date = self.extract_date_from_channel(channel_name) if use_channel_date else None
    
    # ... rest of method uses normalized_channel and channel_words
```

**Impact:** Reduces 7+ regex operations × 4-5 strategy calls down to single execution
**Expected Speedup:** 3-5x overall

### 3. **Optimize Regex Operations in _normalize_text()** ⭐ MEDIUM IMPACT

**Current Issue:**
- 7+ separate `re.sub()` calls on every normalization
- Regex patterns compiled on every call

**Solution:**
Pre-compile regex patterns and combine where possible:

```python
# At module level (after imports)
_COMPILED_PATTERNS = {
    'start_timestamp': re.compile(r'start:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', re.IGNORECASE),
    'stop_timestamp': re.compile(r'stop:\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}', re.IGNORECASE),
    'multi_timezone': re.compile(
        r'\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+(?:uk|et|pt|ct|mt)(?:\s*[/|]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm)\s+(?:uk|et|pt|ct|mt))+',
        re.IGNORECASE
    ),
    'timezone_abbr': re.compile(r'\b(?:uk|et|pt|ct|mt|utc|gmt|est|pst|cst|mst)\b', re.IGNORECASE),
    'iso_date': re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}'),
    'time_format': re.compile(r'\d{1,2}:\d{2}(?::\d{2})?(?:\s*(?:am|pm))?', re.IGNORECASE),
    'punctuation': re.compile(r'[^\w\s]'),
}

def _normalize_text(self, text: str) -> str:
    """Normalize text for matching (optimized version)."""
    if not text:
        return ""
    
    # Apply pre-compiled patterns
    for pattern in (_COMPILED_PATTERNS['start_timestamp'],
                    _COMPILED_PATTERNS['stop_timestamp'],
                    _COMPILED_PATTERNS['multi_timezone'],
                    _COMPILED_PATTERNS['timezone_abbr'],
                    _COMPILED_PATTERNS['iso_date'],
                    _COMPILED_PATTERNS['time_format']):
        text = pattern.sub('', text)
    
    # Lowercase, remove punctuation, normalize whitespace
    text = text.lower()
    text = _COMPILED_PATTERNS['punctuation'].sub(' ', text)
    text = ' '.join(text.split())
    
    return text
```

**Impact:** Eliminates regex compilation overhead
**Expected Speedup:** 2-3x for _normalize_text()

### 4. **Optimize Team Name Matching** ⭐ MEDIUM IMPACT

**Current Issue:**
- Line 921: Creates regex pattern with `re.escape()` and `re.search()` for every team
- Pattern compilation happens on every call

**Solution:**
Pre-compile patterns or use string operations:

```python
def _find_team_matches(self, normalized_channel: str, channel_words: Set[str]) -> List[EventMatch]:
    """Find matches based on team names (optimized)."""
    matches = []
    event_team_matches: Dict[str, Tuple[CalendarEvent, List[str], int]] = {}
    
    for normalized_team, events in self._team_index.items():
        # Skip short team names to avoid false positives
        if len(normalized_team) < MIN_TEAM_NAME_LENGTH:
            continue
        
        # OPTIMIZATION: Use string operations instead of regex when possible
        # Check if team appears as isolated word(s)
        # Split normalized_team and check if all parts appear in channel_words
        team_parts = normalized_team.split()
        
        if len(team_parts) == 1:
            # Single word team - check in word set (O(1))
            if team_parts[0] not in channel_words:
                continue
        else:
            # Multi-word team - check if phrase appears in channel
            # Add spaces around channel to ensure word boundaries
            padded_channel = f" {normalized_channel} "
            padded_team = f" {normalized_team} "
            if padded_team not in padded_channel:
                continue
        
        # Team matched - record it
        for event in events:
            event_id = event.event_id
            if event_id not in event_team_matches:
                event_team_matches[event_id] = (event, [], 0)
            
            _, matched_terms, count = event_team_matches[event_id]
            original_name = self._normalized_teams.get(normalized_team, normalized_team)
            if original_name not in matched_terms:
                matched_terms.append(original_name)
                event_team_matches[event_id] = (event, matched_terms, count + 1)
    
    # ... rest remains the same
```

**Impact:** Replaces regex with O(1) set lookup or O(n) substring search
**Expected Speedup:** 2-4x for team matching phase

### 5. **Early Termination on High-Confidence Matches** ⭐ LOW IMPACT

**Current Issue:**
- All matching strategies run even if early strategies find high-confidence matches
- Wastes time on additional searches that won't improve results

**Solution:**
Add early termination logic:

```python
def find_matches(
    self,
    channel_name: str,
    max_results: int = 5,
    min_confidence: float = LOW_CONFIDENCE,
    date_filter: DateFilter = DateFilter.RECENT_AND_UPCOMING,
    use_channel_date: bool = True,
) -> List[EventMatch]:
    # ... setup code ...
    
    # Strategy 1: Look for both team names (highest confidence)
    team_matches = self._find_team_matches(normalized_channel, channel_words)
    for candidate in team_matches:
        if candidate.event.event_id not in seen_event_ids:
            # Apply date filters...
            if filtered_match:
                matches.append(filtered_match)
                seen_event_ids.add(candidate.event.event_id)
    
    # OPTIMIZATION: Early exit if we have high-confidence matches
    if len(matches) >= max_results and all(m.confidence >= HIGH_CONFIDENCE for m in matches):
        matches.sort(key=lambda m: m.confidence, reverse=True)
        return matches[:max_results]
    
    # Strategy 1.5: Look for last names only...
    # (continue with remaining strategies)
```

**Impact:** Avoids unnecessary work when results are already good
**Expected Speedup:** 1.5-2x in cases with strong early matches

### 6. **Optimize League Matching** ⭐ LOW IMPACT

**Current Issue:**
- Line 1017: Calls `_extract_significant_words()` for every event in matching league
- Extracts words from same event data multiple times if event appears in multiple searches

**Solution:**
Cache event words during index building:

```python
def __init__(self, calendar_scraper: Optional[TheSportsDBCalendarScraper] = None):
    # ... existing init code ...
    
    # Add event words cache
    self._event_words_cache: Dict[str, Set[str]] = {}

def _build_indexes(self) -> None:
    """Build search indexes from loaded events."""
    for event in self._events:
        # Build event words cache once
        event_text = f"{event.event_name} {event.home_team or ''} {event.away_team or ''}"
        self._event_words_cache[event.event_id] = self._extract_significant_words(event_text)
        
        # ... rest of indexing ...

def _find_league_matches(self, normalized_channel: str, channel_words: Set[str]) -> List[EventMatch]:
    """Find matches based on league names (optimized)."""
    matches = []
    
    for normalized_league, events in self._league_index.items():
        if normalized_league in normalized_channel:
            for event in events:
                # Use cached event words
                event_words = self._event_words_cache.get(event.event_id, set())
                common_words = channel_words & event_words
                word_overlap = len(common_words) / max(len(channel_words), 1)
                
                # Require at least 2 common words for league matches
                if len(common_words) >= 2:
                    confidence = MEDIUM_CONFIDENCE + (word_overlap * 0.3)
                    matches.append(
                        EventMatch(
                            event=event,
                            confidence=min(confidence, HIGH_CONFIDENCE),
                            match_type="league",
                            matched_terms=[event.league_name] + list(common_words),
                            details={"word_overlap": word_overlap},
                        )
                    )
    
    return matches
```

**Impact:** Eliminates redundant word extraction
**Expected Speedup:** 2-3x for league matching phase

## Summary of Expected Performance Gains

| Optimization | Phase | Expected Speedup | Implementation Effort |
|-------------|-------|------------------|---------------------|
| Token-based matching (replace fuzzy) | Event name matching | 10-50x | Medium |
| Cache normalized text/words | Overall | 3-5x | Low |
| Pre-compile regex patterns | Text normalization | 2-3x | Low |
| Optimize team matching | Team matching | 2-4x | Low |
| Early termination | Overall (when applicable) | 1.5-2x | Low |
| Cache event words | League matching | 2-3x | Low |

**Combined Expected Improvement:** 20-100x overall speedup depending on channel name characteristics

## Implementation Priority

1. **Phase 1 (Quick Wins):**
   - Cache normalized text and words at entry point
   - Pre-compile regex patterns
   - Optimize team name matching (replace regex with string ops)

2. **Phase 2 (High Impact):**
   - Replace fuzzy matching with token-based matching
   - Add early termination logic

3. **Phase 3 (Refinement):**
   - Cache event words during indexing
   - Further optimize league matching

## Testing Recommendations

1. Create benchmark with representative channel names (100-1000 samples)
2. Measure before/after performance for each optimization
3. Verify match quality remains consistent (especially after replacing fuzzy matching)
4. Test edge cases: very long channel names, many events, etc.

## Code Quality Notes

The current implementation is well-structured with:
- Clear separation of concerns
- Good use of indexes
- Comprehensive matching strategies
- Detailed confidence scoring

These optimizations maintain that structure while eliminating computational bottlenecks.
