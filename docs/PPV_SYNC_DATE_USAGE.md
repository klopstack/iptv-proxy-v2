# PPV Extraction - Sync Date Reference

## Overview

All PPV event extraction, filtering, and testing now uses the **database sync date** as the reference point for date calculations. This ensures consistency between:

- Database state at the time of sync
- Test assertions about past/future dates  
- List regeneration (extractable vs no-data categorization)

## Sync Reference Date

**Last Account Sync:** `2025-12-28 00:04:36 UTC`

This timestamp is retrieved from the `sync_metadata` table in the database:

```sql
SELECT value FROM sync_metadata 
WHERE key = 'last_account_sync'
LIMIT 1;
```

Result: `2025-12-28T00:04:36.346084+00:00`

## How It Works

### 1. Service: SyncDateService

**Location:** `services/sync_date_service.py`

The `SyncDateService` class provides two methods:

```python
# Get raw sync timestamp
sync_time = SyncDateService.get_last_sync_time(db_path)
# Returns: datetime(2025, 12, 28, 0, 4, 36, 346084, tzinfo=timezone.utc)

# Get reference date (timezone-naive)
ref_date = SyncDateService.get_reference_date(db_path)
# Returns: datetime(2025, 12, 28, 0, 4, 36)
```

### 2. PPVEventExtractor Initialization

The extractor now uses the sync date:

```python
from datetime import datetime, UTC
from services.ppv_event_extractor import PPVEventExtractor
from services.sync_date_service import SyncDateService

# Get sync date from database
sync_date = SyncDateService.get_reference_date("data/iptv_proxy.db")

# Create extractor with sync date as reference
extractor = PPVEventExtractor(current_date=sync_date)

# Now all date calculations are relative to sync date
# Example: is_date_far_future() checks if date > sync_date + 365 days
```

### 3. Test Suite Integration

All tests in `tests/test_ppv_event_extractor.py` use the sync date:

```python
from datetime import datetime, UTC
from services.ppv_event_extractor import PPVEventExtractor

# Hardcoded sync reference (matches database value)
SYNC_REFERENCE_DATE = datetime(2025, 12, 28, 0, 4, 36)

class TestPPVEventExtractor:
    def setup_method(self):
        self.extractor = PPVEventExtractor(current_date=SYNC_REFERENCE_DATE)
```

**Why hardcoded?** 
- Tests should be reproducible with same results regardless of when they run
- Using a hardcoded date ensures consistency
- Can be updated when sync is performed again

### 4. List Regeneration

The `regenerate_ppv_lists.py` script uses the sync date:

```bash
python regenerate_ppv_lists.py
```

This:
1. Queries database for sync date
2. Creates PPVEventExtractor with sync date
3. Processes all channels in PPV.list
4. Categorizes as EXTRACTABLE or NO_DATA based on:
   - Competitor extraction success
   - Date extraction success
   - Far-future filtering (using sync date as reference)

## Date Calculations

With reference date **2025-12-28**:

| Date | Relative | Classification |
|------|----------|-----------------|
| 2025-06-01 | ~6 months ago | Past ✓ |
| 2025-12-27 | 1 day ago | Past ✓ |
| 2025-12-28 | Today (sync) | Present ✓ |
| 2026-06-01 | ~5 months future | Valid ✓ |
| 2026-12-28 | Exactly 1 year out | Valid ✓ |
| 2026-12-29 | >365 days out | Far future ✗ (filtered) |
| 2027-02-01 | ~1 month past 1-year | Far future ✗ (filtered) |

## Usage Examples

### Example 1: Check if Date is Far Future

```python
from datetime import datetime, UTC
from services.ppv_event_extractor import PPVEventExtractor
from services.sync_date_service import SyncDateService

sync_date = SyncDateService.get_reference_date("data/iptv_proxy.db")
extractor = PPVEventExtractor(current_date=sync_date)

# This date is >1 year from sync date (2025-12-28)
test_date = datetime(2026, 12, 29)
if extractor.is_date_far_future(test_date):
    print("Date is too far in the future")  # Will print this
```

### Example 2: Extract Event with Confidence

```python
channel_name = "US (ESPN+ 005) | Cleary vs. Duquesne Dec 27 2:00PM ET (2025-12-27 14:00:00)"

sync_date = SyncDateService.get_reference_date("data/iptv_proxy.db")
extractor = PPVEventExtractor(current_date=sync_date)

event = extractor.extract_all(channel_name)
# Extracts competitors: ("Cleary", "Duquesne")
# Extracts date: 2025-12-27 14:00:00 (past, but valid)
# Not filtered because it's within 1 year of sync
```

### Example 3: Regenerate Lists

```bash
# Automatically uses database sync date
python regenerate_ppv_lists.py

# Output:
# Using sync reference date: 2025-12-28 00:04:36
# ✅ EXTRACTABLE.list: 986 channels
# ❌ NO_DATA.list: 10,951 channels
# 📊 Total: 11,937 channels
# 📅 Reference date used: 2025-12-28 00:04:36
```

## Test Coverage

All 56 tests in `tests/test_ppv_event_extractor.py` use the sync date:

**Far-Future Tests (Updated):**
- `test_is_date_far_future_past_date`: Date from 6 months before sync → ✓ Not far future
- `test_is_date_far_future_current_year`: Date 5 months after sync → ✓ Not far future  
- `test_is_date_far_future_beyond_threshold`: Date >365 days after sync → ✓ Is far future

**Other Tests:** All 53 remaining tests also use sync date for consistent date inference

## When to Update

Update `SYNC_REFERENCE_DATE` in `tests/test_ppv_event_extractor.py` when:

1. Database is re-synced with new data
2. Query new sync time: `SELECT value FROM sync_metadata WHERE key = 'last_account_sync' LIMIT 1;`
3. Extract the datetime value
4. Update the constant:
   ```python
   # Old
   SYNC_REFERENCE_DATE = datetime(2025, 12, 28, 0, 4, 36)
   
   # New (after future sync)
   SYNC_REFERENCE_DATE = datetime(2026, 1, 15, 12, 30, 45)
   ```

## Benefits

✅ **Reproducibility:** Tests pass consistently regardless of current date  
✅ **Accuracy:** Date calculations match actual database state  
✅ **Clarity:** Hard to miss - sync date is clearly visible  
✅ **Traceability:** Can see exactly when sync was done  
✅ **Consistency:** All extraction uses same reference point  

## Files Modified

1. **services/sync_date_service.py** (NEW)
   - Retrieves sync timestamp from database
   - Provides `get_reference_date()` helper

2. **tests/test_ppv_event_extractor.py** (UPDATED)
   - Added `SYNC_REFERENCE_DATE` constant  
   - Updated `setup_method()` to use sync date
   - Updated far-future tests with sync date context

3. **regenerate_ppv_lists.py** (NEW)
   - Uses sync date for list regeneration
   - Ensures consistency in extractable/no-data categorization

## Verification

To verify sync date usage:

```bash
# 1. Check database sync time
sqlite3 data/iptv_proxy.db "SELECT value FROM sync_metadata WHERE key='last_account_sync';"
# Output: 2025-12-28T00:04:36.346084+00:00

# 2. Check test constant
grep "SYNC_REFERENCE_DATE" tests/test_ppv_event_extractor.py
# Output: SYNC_REFERENCE_DATE = datetime(2025, 12, 28, 0, 4, 36)

# 3. Run tests with sync date
python -m pytest tests/test_ppv_event_extractor.py -v

# 4. Regenerate lists with sync date
python regenerate_ppv_lists.py
```

All commands should be consistent and report the same date.
