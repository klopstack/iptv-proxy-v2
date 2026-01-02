# Sync Date Reference - Database Query

## Last Sync Query

```sql
SELECT key, value, updated_at 
FROM sync_metadata 
WHERE key = 'last_account_sync'
ORDER BY updated_at DESC
LIMIT 1;
```

## Result

| key | value | updated_at |
|-----|-------|------------|
| last_account_sync | 2025-12-28T00:04:36.346084+00:00 | 2025-12-28 00:04:36.347714 |

## Parsed Values

- **Timestamp (ISO):** `2025-12-28T00:04:36.346084+00:00`
- **Timestamp (UTC):** `2025-12-28 00:04:36.346084`
- **Date:** `2025-12-28`
- **Time:** `00:04:36`
- **Timezone:** `+00:00` (UTC)
- **Python datetime:** `datetime(2025, 12, 28, 0, 4, 36)`

## Reference Point for All Calculations

All future/past date calculations use **2025-12-28** as the reference date.

### Date Range Examples

Based on sync date of **2025-12-28**:

| Date | Days from Sync | Classification |
|------|----------------|-----------------|
| 2025-01-01 | -362 | Past event |
| 2025-06-01 | -211 | Past event |
| 2025-12-27 | -1 | Past event (yesterday from sync) |
| 2025-12-28 | 0 | Sync date |
| 2026-01-01 | +4 | Upcoming event |
| 2026-06-28 | +182 | Upcoming event (6 months) |
| 2026-12-27 | +364 | Upcoming event (within 1 year) |
| 2026-12-28 | +365 | Upcoming event (exactly 1 year) |
| 2026-12-29 | +366 | **FAR FUTURE** (>1 year) ❌ FILTERED |
| 2027-01-01 | +369 | **FAR FUTURE** ❌ FILTERED |

## Threshold Definition

Events are considered "far future" if:
```python
date > sync_date + timedelta(days=365)
# i.e., date > 2026-12-28
```

This ensures we only extract events:
- Within the past (historical events)
- Within the next year (current/upcoming events)
- Not beyond the next year (prevents placeholder/test data from far future)

## Code Usage

### Direct Query

```bash
sqlite3 data/iptv_proxy.db \
  "SELECT value FROM sync_metadata WHERE key='last_account_sync';"
# Returns: 2025-12-28T00:04:36.346084+00:00
```

### Python Service

```python
from services.sync_date_service import SyncDateService

sync_date = SyncDateService.get_reference_date("data/iptv_proxy.db")
# Returns: datetime(2025, 12, 28, 0, 4, 36, 346084)
```

### In Tests

```python
from datetime import datetime

SYNC_REFERENCE_DATE = datetime(2025, 12, 28, 0, 4, 36)

extractor = PPVEventExtractor(current_date=SYNC_REFERENCE_DATE)
```

## When to Update

Update **SYNC_REFERENCE_DATE** in `tests/test_ppv_event_extractor.py` when:

1. Database is re-synced (new `last_account_sync` value)
2. Query the database for new sync time
3. Update the constant to match new sync timestamp
4. Re-run tests and list regeneration

Example update:
```python
# Before
SYNC_REFERENCE_DATE = datetime(2025, 12, 28, 0, 4, 36)

# After next sync (e.g., 2026-01-15 12:30:45)
SYNC_REFERENCE_DATE = datetime(2026, 1, 15, 12, 30, 45)
```

## Verification Checklist

- [ ] Database sync_metadata table contains last_account_sync entry
- [ ] SYNC_REFERENCE_DATE constant matches database value
- [ ] Tests use SYNC_REFERENCE_DATE in setup_method
- [ ] regenerate_ppv_lists.py retrieves sync date from database
- [ ] All far-future filtering uses sync date as reference
- [ ] Extraction logic initializes PPVEventExtractor with sync date
