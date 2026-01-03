# Integration Guide: Phase 1 & 2 PPV Filter Service

## Quick Start for Integrating Phase 1 & 2

### 1. Use the New Filter Type in Code

```python
from services.ppv_filter_service import PPVFilterService
from datetime import datetime, UTC, date

# Create service with sync date (when playlist was fetched from IPTV)
sync_time = datetime.now()  # or actual sync time from your system
service = PPVFilterService(
    sync_date=sync_time.date(),
    current_time=sync_time
)

# Check if a PPV channel should be shown
channel_name = "UFC 300: Jones vs Miocic - 20:30"
category = "US| UFC PPV"

should_show, metadata = service.should_show_channel(channel_name, category)

if should_show:
    print(f"Show this channel: {metadata['event_name']}")
    print(f"Event time: {metadata['start_datetime']}")
```

### 2. Where to Pass sync_date

The sync_date should come from when you last fetched channels from the IPTV API:

```python
# In your playlist sync routine
from datetime import datetime, UTC

class PlaylistManager:
    def sync_channels(self):
        sync_start = datetime.now()
        
        # Fetch channels from IPTV provider
        channels = self.iptv_service.get_live_streams()
        
        # Create filter service with this sync time
        ppv_service = PPVFilterService(
            sync_date=sync_start.date(),
            current_time=sync_start
        )
        
        # Filter channels
        filtered = []
        for ch in channels:
            should_show, meta = ppv_service.should_show_channel(
                ch['name'],
                ch['category']
            )
            if should_show:
                filtered.append(ch)
        
        return filtered
```

### 3. If Using Database Rules (Optional)

If loading rules from database instead of hardcoded defaults:

```python
# Add these rules to your database
new_rules = [
    {
        "category": "UK| BOXING PPV",
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "Boxing"
    },
    {
        "category": "US| UFC PPV",
        "filter_type": "DATETIME_24HR",
        "allow_no_date": True,
        "provider_name": "UFC"
    },
    # ... more categories
]

# Then load them when creating service
db_rules = db.query(PPVEventFilter).all()
service = PPVFilterService(default_rules=db_rules)
```

## Time Format Support

### Supported Formats (Phase 2)

| Format | Example | Parsed As |
|--------|---------|-----------|
| ISO Date + Time | `2025-01-15 20:30` | 2025-01-15 20:30:00 |
| 24-hour (colon) | `20:30` | {sync_date} 20:30:00 |
| 24-hour + seconds | `20:30:45` | {sync_date} 20:30:45 |
| European (dots) | `20.30` | {sync_date} 20:30:00 |
| European + seconds | `20.30.45` | {sync_date} 20:30:45 |

### Category-Specific Behavior (Phase 1)

These categories show events **even without a time**:

```python
categories = [
    "UK| BOXING PPV",
    "UK| WRESTLING PPV",
    "US| WRESTLING PPV",
    "US| MMA PPV",
    "US| UFC PPV",
    "US| WWE PPV",
    "US| AEW PPV",
    "UK| PPV EVENT"
]

# For these categories:
# - Channel without time: SHOWN (midnight on sync_date)
# - Channel with time: SHOWN (time on sync_date)
# - Channel past event: HIDDEN (in the past)
```

## Testing Your Integration

### 1. Unit Test Example

```python
def test_ppv_integration():
    from datetime import datetime, UTC, date
    from services.ppv_filter_service import PPVFilterService
    
    # Setup
    sync_date = date(2025, 1, 15)
    current = datetime(2025, 1, 15, 14, 0, 0)
    service = PPVFilterService(sync_date=sync_date, current_time=current)
    
    # Test UFC event without explicit time
    should_show, meta = service.should_show_channel(
        "UFC 300: Jones vs Miocic",
        "US| UFC PPV"
    )
    
    assert should_show is True
    assert meta['start_datetime'].date() == sync_date
    assert meta['start_datetime'].hour == 0  # midnight (no time specified)

def test_boxing_with_time():
    sync_date = date(2025, 1, 15)
    current = datetime(2025, 1, 15, 10, 0, 0)
    service = PPVFilterService(sync_date=sync_date, current_time=current)
    
    # Boxing with European time format
    should_show, meta = service.should_show_channel(
        "Fury vs Usyk - 20.30 CET",
        "UK| BOXING PPV"
    )
    
    assert should_show is True
    assert meta['start_datetime'].hour == 20
    assert meta['start_datetime'].minute == 30
    assert meta['start_datetime'].date() == sync_date
```

### 2. Integration Test in Your System

```python
def test_playlist_filtering():
    """Test filtering PPV channels in playlist generation"""
    from services.ppv_filter_service import PPVFilterService
    from datetime import datetime, UTC
    
    # Simulate playlist from IPTV provider
    channels = [
        {
            'name': 'UFC 300: Jones vs Miocic',
            'category': 'US| UFC PPV',
            'stream_id': '12345'
        },
        {
            'name': 'Boxing Event - 20:30',
            'category': 'UK| BOXING PPV',
            'stream_id': '12346'
        },
        {
            'name': 'PPV 1 - No Event',  # Will be filtered
            'category': 'US| GENERIC PPV',
            'stream_id': '12347'
        }
    ]
    
    # Filter using Phase 1 & 2
    sync_time = datetime.now()
    service = PPVFilterService(
        sync_date=sync_time.date(),
        current_time=sync_time
    )
    
    filtered = []
    for ch in channels:
        should_show, _ = service.should_show_channel(
            ch['name'], ch['category']
        )
        if should_show:
            filtered.append(ch)
    
    # Should have 2 channels (UFC and Boxing)
    # PPV 1 would be hidden if it doesn't have explicit time
    assert len(filtered) >= 2
```

## Debugging

### Check If Time is Being Parsed

```python
service = PPVFilterService()

# Parse time directly
time_obj = service.parse_24hour_time("Event - 20:30")
print(f"Parsed time: {time_obj}")  # time(20, 30, 0)

# Parse with date
dt = service.parse_iso_datetime_with_24hr("Event - 20:30")
print(f"Parsed datetime: {dt}")  # 2025-01-15 20:30:00
```

### Check Category Rules

```python
service = PPVFilterService()

# See what rule is used for a category
rule = service._default_rules.get("UK| BOXING PPV")
print(f"Rule: {rule}")
# {
#     'filter_type': 'DATETIME_24HR',
#     'allow_no_date': True,
#     'provider_name': 'Boxing'
# }
```

### Enable Logging

```python
import logging

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('services.ppv_filter_service')
logger.setLevel(logging.DEBUG)

# Now you'll see why channels are being hidden/shown
service = PPVFilterService()
should_show, meta = service.should_show_channel(channel_name, category)
# Check logs for debug messages
```

## Common Issues & Solutions

### Issue: Event not showing even though it should

**Check these**:
1. Category spelling (case-sensitive): `"UK| BOXING PPV"` NOT `"uk| boxing ppv"`
2. sync_date is set correctly and is today or recent
3. Time is in the future (if specified)
4. No past event filtering (event time < current_time)

### Issue: Time not being parsed

**Check these**:
1. Time format is correct: `"20:30"` or `"20.30"` only
2. Time is in valid range: 00:00-23:59
3. No other numbers nearby that might interfere
4. Log output to see what was actually parsed

### Issue: Using wrong time (current date instead of sync date)

**Solution**: Always pass sync_date to constructor:
```python
# WRONG - uses today
service = PPVFilterService(current_time=datetime.now())

# CORRECT - uses sync date
sync_time = datetime.now()
service = PPVFilterService(
    sync_date=sync_time.date(),  # ← Required!
    current_time=sync_time
)
```

## API Compatibility

### New Methods (Public)

```python
def parse_24hour_time(text: str) -> Optional[time]:
    """Parse 24-hour time from text"""
    
def parse_iso_datetime_with_24hr(
    text: str,
    sync_date_override: Optional[date] = None
) -> Optional[datetime]:
    """Parse ISO or 24-hour time with sync_date fallback"""
```

Both are safe to call directly if you need time parsing independently.

### Constructor Change

```python
def __init__(
    self,
    db=None,
    current_time: Optional[datetime] = None,
    sync_date: Optional[date] = None,  # NEW - optional, defaults to today
    default_rules: Optional[Dict] = None,
):
```

The new `sync_date` parameter is optional and backward compatible.

## Performance Notes

- **No database queries** for Phase 1 & 2
- **Regex operations** are cached in `pattern_cache`
- **Time complexity**: O(1) for all new operations
- **Memory**: Minimal (no buffering of large lists)

Safe to use in high-throughput scenarios (100+ channels/second).

## Next Steps (Phase 3)

When implementing Phase 3 (API integration):

1. Create event lookup service (query by event name)
2. Implement background enrichment process
3. Add rate limiting (30 calls/minute)
4. Cache API results to avoid redundant lookups
5. Add timezone conversion support
6. Update metadata with API-sourced times

The Phase 1 & 2 implementation provides a solid foundation for Phase 3.

## Reporting Issues

If you encounter problems:

1. Check the test suite: `tests/test_ppv_filter_service.py`
2. Enable debug logging to see decisions
3. Test time parsing directly: `service.parse_24hour_time(text)`
4. Verify sync_date is being used
5. Check that category exactly matches a supported one

All test cases are available as reference implementations.
