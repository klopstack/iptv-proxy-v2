# Last Name Matching & Persistent Caching - Quick Start

## What's New?

Two major improvements to PPV event matching:

1. **Last Name Matching** - Matches abbreviated channel names like "SERRANO VS TELLEZ" to calendar events like "Amanda Serrano vs Reina Tellez"
2. **Persistent Caching** - Calendar data is saved to disk and reused, reducing load times from 38s to 0.23s

## Quick Demo

```bash
# Run the demo script
python test_last_name_matching_demo.py
```

This will:
- Load calendar data (uses cache if available)
- Show cache statistics and performance
- Demonstrate last name matching with example channels

## How It Works

### Persistent Cache
```python
from services.thesportsdb_calendar_scraper import TheSportsDBCalendarScraper

# Create scraper with persistent cache (saves to data/calendar_cache.json)
scraper = TheSportsDBCalendarScraper(cache_dir="data")

# First call fetches from web and saves to cache
events = scraper.get_events_for_date(date(2024, 1, 15))

# Subsequent calls load from cache (12-hour TTL)
events = scraper.get_events_for_date(date(2024, 1, 15))  # Instant!
```

### Last Name Matching
```python
from services.reverse_event_matcher import ReverseEventMatcher

matcher = ReverseEventMatcher(scraper)
matcher.load_events_for_date_range(start_date, end_date)

# Automatically tries multiple strategies:
# 1. Full team names
# 2. Partial team names
# 3. Last names (NEW!)
# 4. Keywords

matches = matcher.find_matches("SERRANO VS TELLEZ")
# → Matches "Amanda Serrano vs Reina Tellez" with conf: 0.95
```

## Match Types

| Channel Format | Calendar Format | Match Type | Confidence |
|---------------|-----------------|------------|------------|
| SERRANO VS TELLEZ | Amanda Serrano vs Reina Tellez | both_last_names | 0.95 |
| AMANDA SERRANO | Amanda Serrano vs Reina Tellez | one_last_name | 0.60 |
| SERRANO | Amanda Serrano vs Reina Tellez | one_last_name | 0.60 |

## Configuration

### Cache TTL (Time-To-Live)
Default: 12 hours. Edit `thesportsdb_calendar_scraper.py`:
```python
CACHE_TTL = 43200  # 12 hours in seconds
```

### Cache Location
Default: `data/calendar_cache.json`. Change with:
```python
scraper = TheSportsDBCalendarScraper(cache_dir="/custom/path")
```

### Disable Persistent Cache
```python
scraper = TheSportsDBCalendarScraper(cache_dir=None)
```

## Cache Management

### Clear Cache
```python
# Clear memory only
scraper.clear_cache(include_persistent=False)

# Clear everything (memory + disk file)
scraper.clear_cache(include_persistent=True)
```

### Cache Statistics
```python
stats = scraper.get_cache_stats()
print(f"Entries: {stats['total_entries']}")
print(f"Hit rate: {stats['hit_rate']:.1%}")
print(f"Disk loads: {stats['disk_loads']}")
print(f"File size: {stats['persistent_cache_size_bytes']:,} bytes")
```

## Testing

```bash
# Run tests
pytest tests/test_thesportsdb_calendar_scraper.py tests/test_reverse_event_matcher.py -v

# Should see:
# - 74 tests passing
# - TestPersistentCache: 6 tests
# - TestLastNameMatching: 7 tests
```

## Performance Impact

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| First run | 38s | 38s | - |
| Second run | 38s | 0.23s | **165x faster** |
| Cache hit rate | 0% | 100% | **Perfect** |
| Server requests | Always | Once per 12h | **Minimal load** |

## Example Matches

These channels now work with last name matching:

```
"SERRANO VS TELLEZ" → "Amanda Serrano vs Reina Tellez" (0.95)
"PAUL VS JOSHUA" → "Jake Paul vs Anthony Joshua" (0.95)
"serrano vs. tellez" → "Amanda Serrano vs Reina Tellez" (0.95)
"AMANDA SERRANO" → "Amanda Serrano vs Reina Tellez" (0.60)
```

## Files Changed

- `services/thesportsdb_calendar_scraper.py` - Added persistent cache
- `services/reverse_event_matcher.py` - Added last name matching
- `tests/test_thesportsdb_calendar_scraper.py` - Added 6 cache tests
- `tests/test_reverse_event_matcher.py` - Added 7 name matching tests

## Troubleshooting

### Cache not loading?
Check file exists: `ls -lh data/calendar_cache.json`

### Cache expired?
Default TTL is 12 hours. Delete file to force refresh: `rm data/calendar_cache.json`

### Tests failing?
Ensure test isolation with `tmp_path` fixtures (already implemented).

## Next Steps

See [LAST_NAME_MATCHING_IMPLEMENTATION.md](LAST_NAME_MATCHING_IMPLEMENTATION.md) for:
- Detailed implementation notes
- Algorithm descriptions
- Future enhancement ideas
- Performance characteristics
