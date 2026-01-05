# Calendar Cache Cleanup - Event 2391465 Issue Resolution

## Problem Summary

Repeated warnings were being logged for event 2391465 ("Laces BC vs Vinyl BC") during calendar enrichment processing:

```
WARNING Empty time or date for event 2391465: date='2026-01-05', time=' UTC'
```

## Root Cause Analysis

The issue had **two layers**:

### Layer 1: Property Caching (Initially Fixed)
The `scheduled_at` property in `CalendarEvent` was being accessed multiple times during processing (e.g., during `to_dict()` for cache serialization), and each access logged a warning. This was fixed by adding property caching in [thesportsdb_calendar_scraper.py](../services/thesportsdb_calendar_scraper.py#L47-L125).

### Layer 2: Invalid Cached Data (Root Cause)
The real issue was that **old code** (prior to commit 919b3a9) didn't filter out events with empty `time_utc` fields during HTML parsing. These events were:

1. **Parsed and cached** with empty `time_utc` values (literally `" UTC"` - just whitespace)
2. **Persisted to disk** in `data/calendar_cache.json`
3. **Loaded on every scraper initialization** and reused
4. Every time `scheduled_at` was accessed, it failed to parse and logged a warning

The current code (as of this fix) **does** filter out empty times at parse time ([thesportsdb_calendar_scraper.py#L406-L412](../services/thesportsdb_calendar_scraper.py#L406-L412)), but the old cached data remained.

## Events Affected

20 events total with empty `time_utc` fields were found in the cache:

- **Event 2391465**: Laces BC vs Vinyl BC (2026-01-05)
- **Figure Skating Events**: Grand Prix finals, Grand Prix de France (multiple dates)
- **Baseball Events**: Northwest League games (Eugene Emeralds, Tri-City Dust Devils, etc.)

All were legitimate events from TheSportsDB that have **dates but no specific times** in the source data.

## Solution Implemented

Created [clean_calendar_cache.py](../clean_calendar_cache.py) script that:

1. **Scans** `data/calendar_cache.json` for events with empty `time_utc` values
2. **Removes** those events from the cache
3. **Preserves** date entries that still have valid events
4. **Removes** date entries that no longer have any events after cleaning

### Results
- **Before**: 39 date entries, 19,595 events (20 with empty times)
- **After**: 37 date entries, 19,575 events (0 with empty times)

## Current Behavior

With both fixes in place:

1. **New data**: Events with empty times are filtered out during HTML parsing and never cached
2. **Cached data**: Clean - no invalid events remain
3. **Property access**: Cached at first access, no repeated warnings
4. **Logging**: Each issue logged once per event, not repeatedly

## Prevention

The current code at [thesportsdb_calendar_scraper.py#L406-L412](../services/thesportsdb_calendar_scraper.py#L406-L412) prevents this from recurring:

```python
# If time is empty after cleaning, log a warning with more context
if not time_utc:
    logger.debug(
        f"Empty time after parsing for row. Raw time_text: '{time_text}', "
        f"Cell HTML: {time_cell}"
    )
    # Skip this event if we can't determine the time
    return None
```

Events without valid times are simply not added to results, preventing them from being cached.

## Usage

To clean the cache if this issue reoccurs:

```bash
# Preview what would be removed
python clean_calendar_cache.py

# Apply the cleanup
python clean_calendar_cache.py --apply
```

The script is safe to run multiple times - it's idempotent and won't harm valid cached data.

## Related Changes

- **Property caching**: [thesportsdb_calendar_scraper.py#L47-L125](../services/thesportsdb_calendar_scraper.py#L47-L125)
- **Empty time filtering**: [thesportsdb_calendar_scraper.py#L406-L412](../services/thesportsdb_calendar_scraper.py#L406-L412)
- **Cache cleanup script**: [clean_calendar_cache.py](../clean_calendar_cache.py)

## Testing

Verified with:
```bash
pytest tests/test_thesportsdb_calendar_scraper.py -v
```

All 18 calendar scraper tests pass, confirming proper handling of:
- Events with valid times
- Events with empty times (filtered out)
- Property caching behavior
- Cache serialization without repeated warnings
