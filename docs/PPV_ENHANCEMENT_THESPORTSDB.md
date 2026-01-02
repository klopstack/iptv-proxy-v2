# PPV Enhancement: TheSportsDB Integration

## Overview

Currently, the PPV filter relies solely on parsing channel names for event timing information. This approach has limitations:

1. **Missing Events**: Events without explicit times in the channel name are hidden (conservative default)
2. **Unreliable Data**: Channel names may have typos, abbreviations, or non-standard formats
3. **No Metadata**: Icons, thumbnails, accurate titles, and full event details are unavailable
4. **Category-Specific Logic Missing**: Some categories (boxing, wrestling) should show events without explicit times

**Solution**: Integrate TheSportsDB API to provide authoritative event data as a fallback/enhancement.

## TheSportsDB API Overview

**Documentation**: https://www.thesportsdb.com/documentation

### Key Endpoints

1. **Event Search** - Look up events by teams/league
   ```
   https://www.thesportsdb.com/api/v1/json/3/eventslast.php?id={team_id}
   https://www.thesportsdb.com/api/v1/json/3/eventslast.php?id={league_id}
   https://www.thesportsdb.com/api/v1/json/3/eventsnext.php?id={league_id}
   ```

2. **Team Search** - Find team IDs by name
   ```
   https://www.thesportsdb.com/api/v1/json/3/searchteams.php?t={team_name}
   ```

3. **Event Details** - Get full event information
   ```
   https://www.thesportsdb.com/api/v1/json/3/lookupevent.php?id={event_id}
   ```

### Available Data Points

```json
{
  "idEvent": "event_id",
  "strEvent": "Team A vs Team B",
  "strEventAlternate": "Alternative Name",
  "dateEvent": "2025-01-20",
  "strTime": "20:00:00",
  "strSport": "Soccer",
  "strLeague": "Premier League",
  "intHomeScore": 2,
  "intAwayScore": 1,
  "strThumb": "thumbnail_url",
  "strBanner": "banner_url",
  "strDescription": "Event description"
}
```

## Implementation Strategy

### Phase 1: Category-Specific Handling (Quick Win)
**Objective**: Allow boxing/wrestling without explicit times

```python
# In DEFAULT_FILTER_RULES
CATEGORY_SHOW_WITHOUT_TIME = {
    "boxing": True,
    "wrestling": True,
    "mma": True,
    "wwe": True,
    "aew": True,
}
```

**Change**: Don't hide "Jake Paul vs Anthony Joshua" entries if category is boxing

### Phase 2: 24-Hour Time Support (High-Impact)
**Objective**: Parse 3,116 entries with HH:MM format
**Effort**: Low (regex addition)
**Impact**: +26% coverage

### Phase 3: TheSportsDB Lookup Service (Major Enhancement)
**Objective**: Create fallback event lookup service

#### New Service: `services/sports_db_service.py`

```python
class TheSportsDBService:
    """
    Lookup event information from TheSportsDB API.
    
    Used as fallback for PPV events with missing or ambiguous datetime.
    """
    
    def __init__(self, cache_ttl: int = 3600):
        self.api_key = "3"  # Free tier
        self.base_url = "https://www.thesportsdb.com/api/v1/json"
        self.cache = {}
        self.cache_ttl = cache_ttl
    
    def search_team(self, team_name: str) -> Optional[Dict[str, Any]]:
        """Find team by name, return ID and details."""
        # /searchteams.php?t={team_name}
        pass
    
    def search_event(self, team_id: str, limit: int = 10) -> List[Dict]:
        """Get recent/upcoming events for a team."""
        # /eventslast.php?id={team_id} or /eventsnext.php?id={team_id}
        pass
    
    def get_event_details(self, event_id: str) -> Optional[Dict[str, Any]]:
        """Get full details for specific event."""
        # /lookupevent.php?id={event_id}
        pass
    
    def match_event(self, channel_name: str, category: str) -> Optional[Dict[str, Any]]:
        """
        Attempt to find matching event in TheSportsDB.
        
        Extracts team names from channel_name, searches API, returns best match.
        """
        # 1. Extract team names from "Team A vs Team B"
        # 2. Search for teams in TheSportsDB
        # 3. Get recent/upcoming events
        # 4. Match against channel_name
        # 5. Return best match with datetime
        pass
```

#### Update: `services/ppv_filter_service.py`

```python
def should_show_channel(
    self, channel_name: str, category: str, 
    filter_rule: Optional[Dict[str, Any]] = None
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """
    Enhanced filtering with TheSportsDB fallback.
    
    1. Check for non-event markers (NO EVENT, OFFLINE, etc)
    2. Parse channel name for datetime
    3. If no datetime AND category allows it:
       - Try TheSportsDB lookup
       - Return event if found and date is reasonable
    4. Conservative default: HIDE if uncertain
    """
    
    # ... existing checks ...
    
    # NEW: TheSportsDB fallback for boxing/wrestling
    if not datetime_result and category_allows_no_time:
        sports_db_event = self.sports_db.match_event(channel_name, category)
        if sports_db_event:
            return True, {
                'event_name': sports_db_event['strEvent'],
                'start_datetime': datetime.fromisoformat(
                    f"{sports_db_event['dateEvent']}T{sports_db_event['strTime']}"
                ),
                'source': 'thesportsdb',
                'thumbnail': sports_db_event.get('strThumb'),
                'banner': sports_db_event.get('strBanner'),
            }
    
    return False, None  # Conservative default
```

### Phase 4: PPV EPG Generation (Long-term)
**Objective**: Build EPG XML from PPV events with TheSportsDB data

```python
class PPVEPGGenerator:
    """
    Generate XMLTV EPG for PPV events using:
    1. Channel name parsing
    2. TheSportsDB event lookup
    3. Schedule inference (day slots, typical broadcast times)
    """
    
    def generate_epg(self, ppv_channels: List[Channel]) -> str:
        """Generate XMLTV format EPG."""
        pass
    
    def get_program_details(
        self, event_name: str, category: str
    ) -> Dict[str, Any]:
        """Get title, description, icon from TheSportsDB."""
        pass
```

## Benefits

### Immediate (Phase 1-2)
- ✅ Better handling of boxing/wrestling PPV
- ✅ +26% coverage with 24-hour times
- ✅ Total coverage: ~75-80%

### Medium-term (Phase 3)
- ✅ Authoritative event times from external source
- ✅ Reduced false negatives (events hidden due to ambiguous times)
- ✅ Event metadata (icons, descriptions)
- ✅ Better accuracy than text parsing alone
- ✅ Total coverage: ~95%+

### Long-term (Phase 4)
- ✅ Professional-grade PPV EPG data
- ✅ Channel icons and thumbnails
- ✅ Accurate event titles and descriptions
- ✅ Better UX for clients (Plex, Kodi, etc.)

## Implementation Roadmap

```
Week 1: Phase 1 + Phase 2
  • Category-specific rules (boxing/wrestling)
  • 24-hour time format support
  • Testing with current data

Week 2-3: Phase 3
  • Create TheSportsDBService
  • Integrate into PPVFilterService
  • Add caching layer
  • Test with real API

Week 4: Phase 4
  • EPG generation
  • Icon/thumbnail handling
  • Quality assurance

Expected Coverage Timeline:
  • Current: 62.6%
  • After Phase 1-2: ~75-80%
  • After Phase 3: ~95%+
  • After Phase 4: Production-ready EPG
```

## Considerations

### Caching Strategy
- TheSportsDB API calls should be cached (TTL: 24 hours)
- Cache key: `{sport}:{team1}:{team2}:{date}`
- Fallback to cached data if API unavailable

### Rate Limiting
- TheSportsDB free tier: 10 requests/second
- Implement request queue/throttle
- Batch lookups during off-peak times

### Data Quality
- Not all events have complete data in TheSportsDB
- Fallback to conservative hiding if API lookup fails
- Validate datetime against "current time" (no events >2 years old)

### Error Handling
- Network errors → log and continue with text-based parsing
- API timeout → use cached data if available
- Malformed response → skip lookup, use parsing

## API Key Management

TheSportsDB uses free tier (key: "3") with these limits:
- 10 requests/second
- No authentication required
- Consider requesting paid tier for production

## Testing Strategy

```python
# Unit tests for TheSportsDBService
def test_search_team():
    """Test team lookup."""
    
def test_get_event():
    """Test event retrieval."""
    
def test_match_event():
    """Test event matching against channel names."""
    
def test_cache_behavior():
    """Test caching and TTL."""

# Integration tests
def test_ppv_filter_with_sports_db():
    """Test full filter flow with API fallback."""
    
def test_boxing_without_time():
    """Test category-specific behavior."""
```

## Example Use Cases

### Before Enhancement
```python
# Channel: "Jake Paul vs Anthony Joshua"
# Category: Boxing
# Result: ❌ HIDDEN (no explicit time, conservative default)
```

### After Phase 1
```python
# Channel: "Jake Paul vs Anthony Joshua"  
# Category: Boxing
# Result: ✅ SHOW (boxing category allows events without explicit time)
```

### After Phase 3
```python
# Channel: "Jake Paul vs Anthony Joshua"
# Category: Boxing
# TheSportsDB lookup: Found event on 2024-12-19 20:00 UTC
# Result: ✅ SHOW with proper datetime and metadata
```

## References

- TheSportsDB API: https://www.thesportsdb.com/documentation
- XMLTV Format: http://xmltv.org/wiki/
- EPG Standards: https://en.wikipedia.org/wiki/Electronic_program_guide
