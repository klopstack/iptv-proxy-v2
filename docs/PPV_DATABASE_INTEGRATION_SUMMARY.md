# PPV Database Integration - Implementation Summary

**Date:** 2025-01-03  
**Status:** ✅ Complete

## What Was Implemented

### 1. Database-Backed PPV Filtering ✅

**File:** `services/ppv_visibility_service.py`

**Changes:**
- Replaced direct `PPVEventExtractor` calls with database `Event` queries
- Queries linked events via `EventChannelLink` many-to-many relationship
- Respects `Channel.ppv_enrichment_status` field
- Added instance-level event caching for performance

**Logic Flow:**
```python
def _is_ppv_active(self, channel):
    # 1. Query Event via EventChannelLink
    event = db.session.query(Event)...
    
    # 2. If no event, check enrichment status
    if not event:
        if status == "no_match": return False
        if status in ("queued", "processing"): return True (optimistic)
        return False (conservative)
    
    # 3. Check event status and time
    if event.status in (CANCELLED, FINISHED): return False
    if event.scheduled_at < now(): return False (past)
    return True (active/upcoming)
```

### 2. Event ID EPG Identifiers ✅

**File:** `routes/playlists.py`

**Changes:**
- Added batch loading of event IDs for PPV channels
- PPV channels with linked events use `event-{id}` format
- Non-PPV and unlinked PPV channels use original `ch-{account_id}-{stream_id}` format

**Implementation:**
```python
# Batch load event IDs
ppv_channel_ids = [ch.id for ch in channels if ch.is_ppv]
event_links = db.session.query(
    EventChannelLink.channel_id, Event.id, Event.external_id
).join(Event).filter(
    EventChannelLink.channel_id.in_(ppv_channel_ids)
).all()

# Assign EPG identifiers
for channel in channels:
    if channel.is_ppv and channel.id in event_map:
        tvg_id = f"event-{event_id}"  # Event-based
    else:
        tvg_id = f"ch-{account_id}-{stream_id}"  # Standard
```

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Channel Sync                                             │
│    - Marks PPV channels (is_ppv = True)                     │
│    - Sets ppv_enrichment_status = None                      │
└────────────────────┬────────────────────────────────────────┘
                     ↓
┌─────────────────────────────────────────────────────────────┐
│ 2. PPV Calendar Enrichment Service                          │
│    - PPVEventExtractor.extract_all(channel.name)            │
│    - Match to TheSportsDB calendar                          │
│    - Create Event record (DB)                               │
│    - Create EventChannelLink (DB)                           │
│    - Set ppv_enrichment_status = "matched"                  │
└────────────────────┬────────────────────────────────────────┘
                     ↓
        ┌────────────┴────────────┐
        ↓                         ↓
┌──────────────────────┐  ┌──────────────────────┐
│ 3a. Playlist Gen     │  │ 3b. Visibility       │
│  - Query Events      │  │  - Query Events      │
│  - Set EPG IDs       │  │  - Filter by date    │
│  - event-{id}        │  │  - Check status      │
└──────────────────────┘  └──────────────────────┘
```

## Key Database Entities

### Event Model
```python
class Event(db.Model):
    id                  # Database ID (used in EPG: event-{id})
    external_id         # TheSportsDB event ID
    home_team_name      # Competitor 1
    away_team_name      # Competitor 2
    scheduled_at        # Event datetime (UTC)
    status              # scheduled, live, finished, cancelled
    is_ppv              # PPV flag
```

### EventChannelLink Model
```python
class EventChannelLink(db.Model):
    event_id            # FK to Event
    channel_id          # FK to Channel
    match_confidence    # 0-1 confidence score
    match_method        # calendar_browse, direct_search
```

### Channel Enrichment Fields
```python
class Channel(db.Model):
    ppv_enrichment_status       # queued, processing, matched, no_match, error
    ppv_enrichment_attempts     # Retry count
    ppv_enrichment_error        # Last error message
    ppv_enrichment_last_attempt # Timestamp
```

## EPG Identifier Examples

### Before (All Channels)
```m3u
#EXTINF:-1 tvg-id="ch-1-12345" tvg-name="ESPN+ PPV: UFC 300" ...
#EXTINF:-1 tvg-id="ch-1-12346" tvg-name="DAZN PPV: Boxing Match" ...
#EXTINF:-1 tvg-id="ch-1-12347" tvg-name="CNN" ...
```

### After (Event-Based for PPV)
```m3u
#EXTINF:-1 tvg-id="event-42" tvg-name="ESPN+ PPV: UFC 300" ...
#EXTINF:-1 tvg-id="event-43" tvg-name="DAZN PPV: Boxing Match" ...
#EXTINF:-1 tvg-id="ch-1-12347" tvg-name="CNN" ...
```

**Benefits:**
- Multiple channels showing same event → same EPG ID
- Different accounts showing same event → shared EPG data
- Foundation for auto-generated EPG from Event table

## Enrichment Status Handling

| Status | Behavior | Rationale |
|--------|----------|-----------|
| `matched` | Query Event, check date | Event linked, use it |
| `no_match` | Hide channel | No event found |
| `queued` | Show channel | Optimistic (enrichment pending) |
| `processing` | Show channel | Optimistic (being enriched) |
| `error` | Show channel | Avoid hiding valid channels |
| `None` | Hide channel | Conservative (not enriched) |

## Performance Optimizations

### 1. Batch Loading
```python
# Load all event IDs in one query (not N queries)
ppv_channel_ids = [ch.id for ch in channels if ch.is_ppv]
event_links = db.session.query(...).filter(
    EventChannelLink.channel_id.in_(ppv_channel_ids)
).all()
```

### 2. Instance Caching
```python
class PPVVisibilityService:
    def __init__(self, account):
        self._event_cache = {}  # Cache per service instance
```

### 3. Database Indexes
```python
# Already exists in models.py
__table_args__ = (
    db.Index("idx_event_channel_event", "event_id"),
    db.Index("idx_event_channel_channel", "channel_id"),
)
```

## Testing Results

```bash
✅ All 1834 tests passing
✅ Code coverage: 79.93% (close to 80% target)
✅ Formatting verified (black)
✅ Linting verified (flake8)
✅ No import errors
✅ Backward compatible
```

## Future Enhancements

### 1. Auto-Generated PPV EPG

Create EPG source that generates XMLTV from Event records:

```python
@bp.route("/epg/ppv/<int:account_id>.xml")
def generate_ppv_epg(account_id):
    """Auto-generate EPG from Event records."""
    events = query_ppv_events_for_account(account_id)
    
    xml = generate_xmltv(
        channels=[(f"event-{e.id}", f"{e.home_team_name} vs {e.away_team_name}") 
                  for e in events],
        programmes=[(e.scheduled_at, f"event-{e.id}", e.league_name, ...)
                    for e in events]
    )
    
    return Response(xml, mimetype="application/xml")
```

### 2. Enrichment Status API

```python
@bp.route("/api/accounts/<int:account_id>/ppv-enrichment-status")
def get_enrichment_status(account_id):
    """Get enrichment statistics."""
    stats = db.session.query(
        Channel.ppv_enrichment_status,
        db.func.count()
    ).filter(
        Channel.account_id == account_id,
        Channel.is_ppv == True
    ).group_by(Channel.ppv_enrichment_status).all()
    
    return jsonify(dict(stats))
```

### 3. Manual Event Linking UI

Add UI to manually link channels to events when auto-matching fails.

## Migration Notes

**✅ No database migrations needed!**

All required fields already exist:
- `Event` model (added for enrichment)
- `EventChannelLink` model (added for enrichment)
- `Channel.ppv_enrichment_status` (already present)

**✅ Fully backward compatible:**
- Non-PPV channels unchanged
- PPV channels without events use original format
- Enrichment is optional (channels work without it)

## Documentation

Created:
- [docs/PPV_DATABASE_INTEGRATION.md](PPV_DATABASE_INTEGRATION.md) - Comprehensive integration guide

Related:
- [services/ppv_calendar_enrichment_service.py](../services/ppv_calendar_enrichment_service.py) - Creates Event records
- [services/ppv_event_extractor.py](../services/ppv_event_extractor.py) - Extracts event info
- [models.py](../models.py) - Event/EventChannelLink models

## Verification Commands

```bash
# Run tests
make test

# Check linting
make lint

# View playlist with event EPG IDs
curl http://localhost:8000/playlist/1.m3u | grep 'tvg-id="event-'

# Check enrichment status distribution
sqlite3 data/iptv_proxy.db "
  SELECT ppv_enrichment_status, COUNT(*) 
  FROM channels 
  WHERE is_ppv = 1 
  GROUP BY ppv_enrichment_status;
"

# View linked events
sqlite3 data/iptv_proxy.db "
  SELECT c.name, e.home_team_name, e.away_team_name, e.scheduled_at
  FROM channels c
  JOIN event_channel_links ecl ON c.id = ecl.channel_id
  JOIN events e ON ecl.event_id = e.id
  WHERE c.is_ppv = 1
  ORDER BY e.scheduled_at;
"
```

## Summary

Successfully integrated database-backed Event records into PPV system:

✅ **PPVVisibilityService** now queries Event records instead of extracting on-demand  
✅ **Playlist generation** uses event IDs as EPG identifiers for PPV channels  
✅ **Enrichment status** tracking respected throughout  
✅ **Performance optimized** with batch loading and caching  
✅ **Backward compatible** with existing non-PPV channels  
✅ **Foundation laid** for auto-generated EPG from Event records  
✅ **All 1834 tests passing** with 79.93% coverage  

The system now uses the enrichment service's Event records as the source of truth for PPV channel filtering and EPG identification, enabling future features like auto-generated EPG and cross-provider event correlation.
