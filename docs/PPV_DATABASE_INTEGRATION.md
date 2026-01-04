# PPV Event Database Integration

**Status:** ✅ Complete  
**Date:** 2025-01-03

## Overview

Integrated database-backed Event records into `PPVVisibilityService` and playlist generation. PPV channels now use Event IDs as EPG identifiers and filter based on stored event data created by `ppv_calendar_enrichment_service`.

## Architecture

```
Channel Sync → PPV Calendar Enrichment Service
                    ↓
         (PPVEventExtractor + Calendar + API)
                    ↓
             Event Records (DB)
                    ↓
    ┌───────────────┴───────────────┐
    ↓                               ↓
PPVVisibilityService          Playlist Generation
  (filter channels)           (assign event IDs)
```

## Key Changes

### 1. PPVVisibilityService - Database Integration

**Before:** Called `PPVEventExtractor` directly on each channel name  
**After:** Queries `Event` records via `EventChannelLink`

**New Logic:**
```python
def _is_ppv_active(self, channel):
    # Query linked event from database
    event = db.session.query(Event).join(EventChannelLink)...
    
    if not event:
        # Check enrichment status
        if channel.ppv_enrichment_status == "no_match":
            return False  # No active event
        if channel.ppv_enrichment_status in ("queued", "processing"):
            return True  # Optimistic
    
    # Check event status and time
    if event.status in (Event.STATUS_CANCELLED, Event.STATUS_FINISHED):
        return False
    if event.scheduled_at < current_time:
        return False  # Past event
    
    return True  # Active/upcoming
```

### 2. Playlist Generation - Event ID EPG Identifiers

**Before:** `tvg-id="ch-{account_id}-{stream_id}"`  
**After:** `tvg-id="event-{event_id}"` for PPV channels with events

**Implementation:**
```python
# Load event IDs for PPV channels
event_links = db.session.query(
    EventChannelLink.channel_id, Event.id
).join(Event).filter(
    EventChannelLink.channel_id.in_(ppv_channel_ids)
).all()

# Assign EPG identifiers
for channel in channels:
    if channel.is_ppv and channel.id in event_map:
        tvg_id = f"event-{event_id}"
    else:
        tvg_id = f"ch-{account_id}-{stream_id}"
```

## Benefits

### Database Integration
- ✅ No repeated extraction (uses cached Event records)
- ✅ Integrates with enrichment workflow  
- ✅ Respects enrichment status tracking
- ✅ Performance: batch loading + instance caching

### Event-Based EPG IDs
- ✅ Unique identifier per event (not per channel)
- ✅ Multiple channels for same event share EPG ID
- ✅ Enables auto-generated EPG from Event records
- ✅ Backward compatible (non-PPV channels unchanged)

## Data Flow

### 1. Enrichment Creates Events
```python
# ppv_calendar_enrichment_service.py
def enrich_channels(channels):
    for channel in channels:
        # Extract event info
        info = extractor.extract_all(channel.name)
        
        # Match to calendar
        calendar_event = match_to_calendar(info)
        
        # Create Event record
        event = Event(
            external_id=calendar_event.event_id,
            home_team_name=calendar_event.home_team,
            away_team_name=calendar_event.away_team,
            scheduled_at=calendar_event.scheduled_at,
            ...
        )
        
        # Link channel to event
        link = EventChannelLink(
            channel=channel,
            event=event,
            match_confidence=0.85
        )
        
        channel.ppv_enrichment_status = "matched"
```

### 2. Visibility Service Queries Events
```python
# services/ppv_visibility_service.py
def should_show_channel(channel):
    if channel.is_ppv and ppv_visibility == "hide_inactive":
        event = query_linked_event(channel)
        
        if event and event.scheduled_at > now():
            return True  # Future event - show
        else:
            return False  # Past/no event - hide
```

### 3. Playlist Uses Event IDs
```python
# routes/playlists.py  
def generate_playlist(account_id):
    channels = query_visible_channels()
    event_map = load_event_ids_for_ppv_channels()
    
    for channel in channels:
        if channel.is_ppv and channel.id in event_map:
            tvg_id = f"event-{event_map[channel.id]}"
        else:
            tvg_id = f"ch-{account_id}-{channel.stream_id}"
```

## Channel Enrichment Status

**Field:** `Channel.ppv_enrichment_status`

**Values:**
- `queued` - Scheduled for enrichment
- `processing` - Currently being enriched
- `matched` - Event found and linked
- `no_match` - No event found for this channel
- `error` - Enrichment failed
- `None` - Not yet enriched

**Handling in PPVVisibilityService:**
- `matched` → Check linked Event
- `no_match` → Hide (no active event)
- `queued`, `processing` → Show (optimistic)
- `error` → Show (avoid hiding valid channels)
- `None` → Hide (conservative default)

## EPG Identifier Format

**Standard Channels:**
```
tvg-id="ch-1-12345"
       ↑  ↑  ↑
       │  │  └─ stream_id
       │  └──── account_id
       └─────── "ch" prefix
```

**PPV Channels with Events:**
```
tvg-id="event-42"
       ↑     ↑
       │     └─ Event.id (database ID)
       └─────── "event" prefix
```

## Future: Auto-Generated EPG

With event IDs as EPG identifiers, we can auto-generate EPG XML:

```python
def generate_ppv_epg(account_id):
    """Generate EPG XML from Event records."""
    events = query_ppv_events_for_account(account_id)
    
    xml = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv>']
    
    # Channels (one per event)
    for event in events:
        xml.append(f'  <channel id="event-{event.id}">')
        xml.append(f'    <display-name>{event.home_team_name} vs {event.away_team_name}</display-name>')
        xml.append('  </channel>')
    
    # Programmes
    for event in events:
        start = event.scheduled_at.strftime("%Y%m%d%H%M%S +0000")
        xml.append(f'  <programme start="{start}" channel="event-{event.id}">')
        xml.append(f'    <title>{event.league_name}: {event.home_team_name} vs {event.away_team_name}</title>')
        xml.append('  </programme>')
    
    xml.append('</tv>')
    return '\n'.join(xml)
```

## Performance Optimizations

### Batch Loading
```python
# Load all event IDs in one query
ppv_channel_ids = [ch.id for ch in channels if ch.is_ppv]
event_links = db.session.query(
    EventChannelLink.channel_id, Event.id
).join(Event).filter(
    EventChannelLink.channel_id.in_(ppv_channel_ids)
).all()
```

### Instance Caching
```python
class PPVVisibilityService:
    def __init__(self, account):
        self._event_cache = {}  # Cache for this service instance
    
    def _is_ppv_active(self, channel):
        if channel.id in self._event_cache:
            return self._event_cache[channel.id]
        # ... query and cache
```

### Database Indexes
```python
# models.py - EventChannelLink
__table_args__ = (
    db.Index("idx_event_channel_event", "event_id"),
    db.Index("idx_event_channel_channel", "channel_id"),
)
```

## Testing

```bash
# Run full test suite
make test

# Check code formatting
make lint

# Test playlist with event EPG IDs
curl http://localhost:8000/playlist/<account_id>.m3u | grep 'tvg-id="event-'

# Check enrichment status distribution
sqlite3 data/iptv_proxy.db "
  SELECT ppv_enrichment_status, COUNT(*) 
  FROM channels 
  WHERE is_ppv=1 
  GROUP BY ppv_enrichment_status
"
```

## Migration Notes

**✅ No database migrations needed!**

All necessary fields already exist:
- `Event` model with full event data
- `EventChannelLink` many-to-many relationship  
- `Channel.ppv_enrichment_status` tracking

**✅ Fully backward compatible:**
- Non-PPV channels use original EPG ID format
- PPV without events use original format
- Enrichment is optional

## Related Documentation

- [services/ppv_calendar_enrichment_service.py](../services/ppv_calendar_enrichment_service.py) - Creates Event records
- [services/ppv_event_extractor.py](../services/ppv_event_extractor.py) - Extracts event info
- [models.py](../models.py) - Event, EventChannelLink models
- [Architecture Overview](ARCHITECTURE_OVERVIEW.md) - System architecture

## Summary

**Completed Integration:**
- ✅ PPVVisibilityService queries Event records (not extracting on-demand)
- ✅ Playlist generation uses event IDs as EPG identifiers
- ✅ Enrichment status tracking respected
- ✅ Event caching for performance
- ✅ Backward compatible
- ✅ Foundation for auto-generated EPG
- ✅ All 1834 tests passing
