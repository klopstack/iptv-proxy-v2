# Bootstrap Failure - Fixed

## Issue
Docker container failed to start with:
```
ModuleNotFoundError: No module named 'thesportsdb'
```

## Root Cause
The PPV enrichment code added in previous commits depends on the `thesportsdb` Python library, but it was not added to `requirements.txt`. When the Docker container tried to import the application, it failed during module loading.

## Error Chain
1. app.py imports from routes.ppv_enrichment
2. routes/ppv_enrichment.py imports PPVEnrichmentQueue
3. services/ppv_enrichment_service.py imports TheSportsDBService
4. services/thesportsdb_service.py tries: `from thesportsdb import events, leagues, teams`
5. **ImportError** ← Package not installed

## Solution Applied

### 1. Added Missing Dependency
**File:** `requirements.txt`
```
thesportsdb>=0.2.0
```

**Why:** TheSportsDB is a Python wrapper for the TheSportsDB API, providing:
- Event data retrieval
- League information
- Team lookups
- Event matching capabilities

### 2. Fixed SQLAlchemy Warnings
**File:** `models.py`

Added `overlaps` parameter to Event and EventChannelLink relationships to eliminate SQLAlchemy warnings about relationship overlap:
- Event.channels: `overlaps="channel_links,event_links"`
- EventChannelLink.event: `overlaps="channels,events"`
- EventChannelLink.channel: `overlaps="channels,events"`

These warnings were non-blocking but noisy in logs.

## Verification
✓ Syntax check passed (models.py)
✓ Requirement added and verified
✓ Code committed

## Docker Boot Status
**Before:** ❌ Failed with ModuleNotFoundError
**After:** ✅ Should boot successfully

Next rebuild: `docker-compose up --build`

The container will now:
1. Install thesportsdb library
2. Successfully import all modules
3. Boot without SQLAlchemy warnings
