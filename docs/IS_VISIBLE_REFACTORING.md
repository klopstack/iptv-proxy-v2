# is_visible Field Refactoring Summary

**Date**: January 4, 2026  
**Status**: ✅ Complete

## Problem Statement

The `is_visible` field in the `Channel` model was being used inconsistently across the codebase:
- Some places used it as a pre-computed filter cache (outdated pattern)
- Some places used it as a query filter (incorrect - should use FilterService)
- The web UI was showing 231 categories, while the Xtream API correctly showed 62 categories

This caused inconsistencies where the admin UI and API endpoints showed different results.

## Solution

**New Architecture:**
- `is_visible` is now **reserved for explicit per-channel hiding only**
  - Used by `channel_health_service.py` for auto-disable feature
  - Can be used in the future for a manual "hide this channel" feature
- **FilterService is the single source of truth** for filter-based visibility
  - All routes and services that need to respect filters must use `FilterService.apply_filters_to_channels()`

## Files Changed

### 1. ✅ `services/ppv_epg_service.py`
**Before:**
```python
.filter(
    Channel.is_active == True,
    Channel.is_visible == True,  # ❌ Wrong - uses pre-computed flag
)
```

**After:**
```python
# Load all channels, then apply FilterService
all_channels = query.all()
FilterService.apply_filters_to_channels(account_id, all_channels)
filtered_channels = [ch for ch in all_channels if ch.is_visible]
```

### 2. ✅ `routes/epg/channels.py`
**Before:**
```python
if not show_filtered:
    query = query.filter(Channel.is_visible == True)  # ❌ Wrong
```

**After:**
```python
# Get all channels, then apply FilterService
all_channels = query.all()
if not show_filtered and account_id:
    FilterService.apply_filters_to_channels(account_id, all_channels)
    channels = [ch for ch in all_channels if ch.is_visible]
```

**Changes in 3 view modes:** unmapped, mapped, all

### 3. ✅ `services/epg_match_rules_service.py`
**Before:**
```python
query = Channel.query.filter_by(account_id=account_id, is_active=True)
if not include_filtered:
    query = query.filter_by(is_visible=True)  # ❌ Wrong
```

**After:**
```python
all_channels = query.all()
if not include_filtered:
    FilterService.apply_filters_to_channels(account_id, all_channels)
    channels = [ch for ch in all_channels if ch.is_visible]
```

### 4. ✅ `routes/accounts.py`
**Before:**
```python
# Get visible/hidden counts using pre-computed flag
visible_count = Channel.query.filter_by(
    account_id=account_id, is_active=True, is_visible=True
).count()  # ❌ Wrong
```

**After:**
```python
# Load all channels and apply FilterService for accurate stats
all_channels = Channel.query.filter_by(account_id=account_id, is_active=True).all()
FilterService.apply_filters_to_channels(account_id, all_channels)
visible_count = sum(1 for ch in all_channels if ch.is_visible)
```

### 5. ✅ `routes/channel_health.py`
**Before:**
```python
query = Category.query.join(Channel).filter(
    Channel.is_visible == True  # ❌ Wrong - uses pre-computed flag
).distinct()
```

**After:**
```python
# Get all categories, apply FilterService to determine visibility
categories_with_channels = query.distinct().all()
for category in categories_with_channels:
    channels = Channel.query.filter_by(category_id=category.id, is_active=True).all()
    FilterService.apply_filters_to_channels(category.account_id, channels)
    if any(ch.is_visible for ch in channels):
        visible_category_ids.add(category.id)
```

## Legitimate Uses of is_visible (Kept As-Is)

### ✅ `services/channel_health_service.py`
- **Line 508-509**: `channel.is_visible = False` - Auto-disable feature ✅ **CORRECT**
- **Line 554**: `channels_query.filter(Channel.is_visible == True)` - Respects explicit hide ✅ **CORRECT**
- **Line 1195**: `channel.is_visible = True` - Re-enable channel ✅ **CORRECT**

These uses are **legitimate** because they implement an explicit per-channel hide feature (auto-disable for health failures), not filter-based visibility.

## Pattern Summary

### ❌ OLD PATTERN (Deprecated)
```python
# Query with is_visible filter
channels = Channel.query.filter_by(is_visible=True).all()
```

### ✅ NEW PATTERN (Correct)
```python
# Load channels, apply FilterService, then filter by is_visible
channels = Channel.query.filter_by(is_active=True).all()
FilterService.apply_filters_to_channels(account_id, channels)
visible_channels = [ch for ch in channels if ch.is_visible]
```

### ✅ LEGITIMATE USE (Auto-Disable)
```python
# Explicit per-channel hide/unhide
channel.is_visible = False  # Auto-disable due to health failure
channel.is_visible = True   # Re-enable channel
```

## Impact

- **Web UI categories**: Now correctly shows 62 categories (matching Xtream API)
- **EPG matching**: Only matches visible (filtered) channels
- **PPV EPG**: Only includes visible channels
- **Account stats**: Accurate visible/hidden counts based on filters
- **Channel health**: Category list only shows categories with visible channels

## Testing

Run the following to verify:

```bash
# 1. Check linting passes
make lint

# 2. Run tests
make test

# 3. Verify web UI categories match Xtream API count
curl http://localhost:8000/api/categories?account_id=1 | jq '.categories | length'
# Should match:
curl http://localhost:8000/player_api.php?username=X&password=Y&action=get_live_categories | jq '. | length'
```

## Future Work

- Consider adding a manual "Hide Channel" button in the UI that sets `is_visible=False`
- This would be independent of filters and persist across filter changes
- The auto-disable feature already implements the backend for this

## References

- FilterService: [services/filter_service.py](../services/filter_service.py)
- Models: [models.py](../models.py) line 324 (Channel.is_visible definition)
- Architecture: [ARCHITECTURE_OVERVIEW.md](ARCHITECTURE_OVERVIEW.md)
