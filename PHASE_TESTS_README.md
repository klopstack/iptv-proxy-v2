# Phase Optimization Tests

Targeted test suites validating Phases 1-4 optimizations to ensure performance improvements work correctly.

## Overview

These test files complement the existing test suite ([test_app.py](tests/test_app.py), [test_tag_service.py](tests/test_tag_service.py), [test_rulesets_api.py](tests/test_rulesets_api.py)) by focusing specifically on the database optimizations implemented in Phases 1-4.

## Test Files

### [tests/test_phase1_cleaned_names.py](tests/test_phase1_cleaned_names.py)
**Purpose:** Validate cleaned name storage optimization (Phase 1)

**What it tests:**
- Sync service computes cleaned names during channel synchronization
- Cleaned names are properly stored in `cleaned_name` column
- Preview endpoint uses pre-computed cleaned names
- Playlist generation uses pre-computed cleaned names
- Tag processing updates cleaned names when tags are applied
- Fallback to original name when cleaned_name is NULL

**Key Assertions:**
- Database column contains cleaned names (tags removed)
- API responses use cleaned names, not computed on-the-fly
- Performance: No real-time tag extraction during reads

**Tests:** 6

### [tests/test_phase2_filter_visibility.py](tests/test_phase2_filter_visibility.py)
**Purpose:** Validate pre-computed filter visibility (Phase 2)

**What it tests:**
- `FilterService.compute_visibility_for_account()` correctly applies filters
- Category whitelist/blacklist filters
- Channel name substring filters
- Regex pattern filters
- Tag-based filters
- Multiple filters with AND logic (all must pass)
- Disabled filters are ignored
- No filters = all channels visible
- Filter create/update/delete triggers recomputation
- Preview endpoint uses `is_visible` column
- Playlist generation uses `is_visible` column

**Key Assertions:**
- Database column `is_visible` reflects filter results
- Filters are applied at write-time (sync, filter CRUD)
- Reads query `is_visible=True` instead of computing filters
- Performance: No real-time filter evaluation during reads

**Tests:** 13

### [tests/test_phase4_database_first.py](tests/test_phase4_database_first.py)
**Purpose:** Validate database-first enforcement (Phase 4)

**What it tests:**
- Tag processing returns 503 when account not synced
- Tag processing works normally when synced
- Preview returns 503 when account not synced
- Preview works normally when synced
- Preview pagination with synced channels
- Playlist generation returns 503 when not synced
- Playlist generation works when synced
- No API fallback in tag processing (removed)
- No API fallback in preview (removed)
- Complete database-first workflow enforcement
- Error messages are clear and actionable
- Only active channels count for sync status

**Key Assertions:**
- All operations require synced channels (database rows)
- 503 Service Unavailable returned when not synced
- No attempt to fall back to live API calls
- Error messages guide users to sync first

**Tests:** 12

## Running the Tests

### Run all phase tests:
```bash
pytest tests/test_phase1_cleaned_names.py tests/test_phase2_filter_visibility.py tests/test_phase4_database_first.py -v
```

### Run specific phase tests:
```bash
# Phase 1 only
pytest tests/test_phase1_cleaned_names.py -v

# Phase 2 only
pytest tests/test_phase2_filter_visibility.py -v

# Phase 4 only
pytest tests/test_phase4_database_first.py -v
```

### Run without coverage (faster, clearer output):
```bash
pytest tests/test_phase4_database_first.py -v --no-cov
```

### Run a single test:
```bash
pytest tests/test_phase4_database_first.py::test_tag_processing_returns_503_when_not_synced -v
```

## Test Configuration

### Fixtures ([tests/conftest.py](tests/conftest.py))

- **`app`**: Flask application with in-memory SQLite database
  - Fresh database for each test (function scope)
  - Tables created/dropped automatically
  
- **`client`**: Flask test client for HTTP requests
  - Use `client.get()`, `client.post()`, etc.
  
- **`db`**: Direct database access within app context
  - For manual data manipulation

### Environment Setup

Tests automatically use in-memory SQLite (`sqlite:///:memory:`) configured in conftest.py. No manual database setup required.

## Coverage Impact

These tests increase coverage for:
- `services/sync_service.py` - cleaned name computation
- `services/filter_service.py` - visibility computation
- `services/tag_service.py` - tag extraction
- `app.py` routes:
  - `/api/accounts/<id>/process-tags` (POST)
  - `/api/accounts/<id>/preview` (GET)
  - `/playlist/<id>.m3u` (GET)

## What's NOT Tested

These focused test files do **not** cover:
- Full feature integration tests (see [test_app.py](tests/test_app.py))
- Tag rule management (see [test_rulesets_api.py](tests/test_rulesets_api.py))
- Tag extraction patterns (see [test_tag_service.py](tests/test_tag_service.py))
- Web UI routes
- EPG generation
- Config-based playlists (Phase migration pending)

## Test Strategy

**Write-time computation, read-time simplicity:**
1. During sync: Compute `cleaned_name` and `is_visible`
2. During filter/tag changes: Recompute affected channels
3. During reads: Query pre-computed columns

**Tests validate:**
- ✅ Computation happens at write-time
- ✅ Database columns store correct values
- ✅ Reads use pre-computed data
- ✅ No fallback to expensive on-the-fly computation

## Expected Results

All tests should pass:
```
tests/test_phase1_cleaned_names.py ......          [ 19%]
tests/test_phase2_filter_visibility.py .............[ 61%]
tests/test_phase4_database_first.py ............    [100%]
```

**Total: 31 passing tests**

## Debugging Failed Tests

### Test fails with "unable to open database file"
- Issue: conftest.py not setting DATABASE_URL before import
- Fix: Ensure `os.environ['DATABASE_URL'] = 'sqlite:///:memory:'` runs before importing app

### Test fails with "is_visible is None"
- Issue: FilterService not called during test setup
- Fix: Call `FilterService().compute_visibility_for_account(account.id)` after creating channels

### Test fails with "cleaned_name is None"
- Issue: Sync service not called, or TagService not configured
- Fix: Create test_ruleset fixture with TagRules, call tag processing

### Test fails with "Account not synced"
- Issue: No channels exist for the account
- Fix: Create Channel objects with `is_active=True` in fixture

## Related Documentation

- [PHASE4_BACKWARD_COMPAT_REMOVAL.md](PHASE4_BACKWARD_COMPAT_REMOVAL.md) - Phase 4 changes
- [ANTIPATTERNS_REVIEW.md](ANTIPATTERNS_REVIEW.md) - Code quality review
- [TESTING.md](TESTING.md) - General testing guide
- [README.md](README.md) - Project overview
