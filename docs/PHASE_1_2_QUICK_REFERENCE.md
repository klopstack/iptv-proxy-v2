# Phase 1 & 2: Quick Reference

## What Was Implemented

### Phase 1: Category-Specific Handling
Events in certain categories (boxing, wrestling, MMA, etc.) are now shown **even without explicit times**.

### Phase 2: 24-Hour Time Format Support  
Parse times in formats like "20:30" or "20.30" (European format) and use playlist sync date.

## Key Files

- **Implementation**: `services/ppv_filter_service.py`
- **Tests**: `tests/test_ppv_filter_service.py`
- **Documentation**: `PHASE_1_2_IMPLEMENTATION.md`

## New Filter Type

```python
rule = {
    "filter_type": "DATETIME_24HR",
    "allow_no_date": True,  # Phase 1: show without explicit time
    "provider_name": "Boxing"
}
```

## Supported Categories (Phase 1 & 2)

| Category | Description |
|----------|-------------|
| `UK\| BOXING PPV` | Boxing events (no date required) |
| `UK\| WRESTLING PPV` | Wrestling events (no date required) |
| `US\| WRESTLING PPV` | US Wrestling events (no date required) |
| `US\| MMA PPV` | MMA events (no date required) |
| `US\| UFC PPV` | UFC events (no date required) |
| `US\| WWE PPV` | WWE events (no date required) |
| `US\| AEW PPV` | AEW events (no date required) |
| `UK\| PPV EVENT` | Generic PPV events (no date required) |

## Time Format Support (Phase 2)

| Format | Example | Parsed As |
|--------|---------|-----------|
| HH:MM | "20:30" | 20:30:00 |
| HH:MM:SS | "20:30:45" | 20:30:45 |
| HH.MM | "20.30" | 20:30:00 |
| HH.MM.SS | "20.30.45" | 20:30:45 |
| ISO Date | "2025-01-15 20:30" | 2025-01-15 20:30:00 |

## Important: sync_date Parameter

When creating PPVFilterService, pass the **playlist sync date**:

```python
from datetime import datetime

# When syncing playlists from IPTV provider
sync_time = datetime.now()

service = PPVFilterService(
    sync_date=sync_time.date(),  # ← Use playlist sync date!
    current_time=sync_time
)
```

This ensures times without explicit dates use the correct reference date.

## Behavior Examples

### Example 1: Event with Time (Phase 2)
```
Channel: "Boxing Event - 20:30"
Category: "UK| BOXING PPV"
sync_date: 2025-01-15

Result: SHOWN at 2025-01-15 20:30:00
```

### Example 2: Event without Time (Phase 1)
```
Channel: "UFC 300: Jones vs Miocic"
Category: "US| UFC PPV"
sync_date: 2025-01-15
allow_no_date: true

Result: SHOWN at 2025-01-15 00:00:00 (midnight)
```

### Example 3: Past Event (Filtered Out)
```
Channel: "UFC 300: Jones vs Miocic - 20:30"
Category: "US| UFC PPV"
current_time: 2025-01-16 10:00:00
Event time: 2025-01-15 20:30:00

Result: HIDDEN (in the past)
```

## Code Examples

### Create Service
```python
from services.ppv_filter_service import PPVFilterService
from datetime import datetime, date

service = PPVFilterService(
    sync_date=date(2025, 1, 15),
    current_time=datetime(2025, 1, 15, 14, 0, 0)
)
```

### Parse Times
```python
# Parse 24-hour time
time_obj = service.parse_24hour_time("Event at 20:30")
# → time(20, 30, 0)

# Parse with sync_date
dt = service.parse_iso_datetime_with_24hr("Event at 20:30")
# → 2025-01-15 20:30:00
```

### Check Channel Visibility
```python
should_show, metadata = service.should_show_channel(
    "UFC 300 - 20:30",
    "US| UFC PPV"
)

if should_show:
    print(f"Show: {metadata['event_name']}")
    print(f"When: {metadata['start_datetime']}")
```

## Test Results

- **28 tests**: All passing ✅
- **Coverage**: 81% (exceeds 80% requirement)
- **Run**: `pytest tests/test_ppv_filter_service.py -v`

## Phase 3 (Not Implemented)

Future enhancement to query event times from API:
- Look up event by name
- Get accurate start times
- Respect API rate limits (30 calls/minute)
- Run in background to supplement parsed times

## Migration Notes

### If Using Default Rules Database

If loading filter rules from database instead of hardcoded defaults:

```python
# Current: Uses hardcoded DEFAULT_FILTER_RULES
service = PPVFilterService()

# Database lookup: Would need to add these rules to DB
rules = {
    "UK| BOXING PPV": {
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "Boxing",
    },
    # ... other rules ...
}
```

Add these rules to your database if not using hardcoded defaults.

### Backward Compatibility

✅ Fully backward compatible:
- Existing rules unchanged
- New filter type only for new categories
- sync_date parameter is optional
- Defaults to today if not provided

## Troubleshooting

### Events Not Showing
1. Check category matches exactly (case-sensitive)
2. Verify `sync_date` is correct
3. Check if event time is in the future
4. Confirm `allow_no_date=True` if no explicit time

### Times Parsing Incorrectly
1. Check for word boundary issues (e.g., "123-45" might match as time)
2. Ensure time is in valid range (00:00-23:59)
3. European format needs dots: "20.30" not "20,30"

### Event Shown as Past
1. Verify `current_time` is correct
2. Check if event is actually in the past
3. Confirm sync_date is used for events without dates

## Performance Notes

- `parse_24hour_time()`: O(1) regex operations
- `parse_iso_datetime_with_24hr()`: O(1) with short-circuit evaluation
- `_handle_datetime_24hr()`: O(1) filtering logic
- No database queries needed for Phase 1 & 2
