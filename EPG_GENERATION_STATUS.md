# EPG Entry Generation & Channel Association Status Report

## Current Status: ❌ NOT GENERATING

**Problem:** No EPG entries are being generated, and no channels are linked to events.

---

## What Was Built

### 1. **Event Model & Database** ✅
- **Table:** `events` (empty - 0 records)
- **Fields:** external_id, sport, league, teams, scheduled_at, status, venue, metadata
- **Purpose:** Stores enriched PPV event data from TheSportsDB
- **Status:** Table exists but NO events created yet

### 2. **Event-Channel Linking** ✅
- **Table:** `event_channel_links` (empty - 0 records)
- **Fields:** event_id, channel_id, confidence, method, feed_type
- **Purpose:** Associates channels with events they broadcast
- **Status:** Table exists but NO associations created yet

### 3. **PPV Enrichment Service** ✅
- **File:** `services/ppv_enrichment_service.py` (550 lines)
- **Class:** `PPVEnrichmentQueue`
- **Capabilities:**
  - Queue channels for enrichment
  - Process queued channels in batches
  - Rate-limited API calls (30/min)
  - Create Event records from TheSportsDB matches
  - Link channels to events via EventChannelLink
  - Persistent tracking with retry logic
- **Status:** CODE EXISTS but NOT ACTIVATED

### 4. **PPV Event Extractor** ✅
- **File:** `services/ppv_event_extractor.py` (668 lines)
- **Purpose:** Parse channel names and extract event info
- **Features:**
  - Extract team names (vs, @, -, versus separators)
  - Extract dates (ISO, Month DD, time-only, weekday)
  - Placeholder detection (NO EVENT STREAMING)
  - Inactive channel filtering
  - Tiered matching (Direct → Calendar Browse)
- **Status:** CODE EXISTS, TESTED, WORKING

### 5. **API Endpoints** ✅
- **GET** `/api/ppv-enrichment/status` → Queue & API usage status
- **POST** `/api/ppv-enrichment/process` → Manual enrichment trigger
- **POST** `/api/ppv-enrichment/queue/channels` → Queue specific channels
- **POST** `/api/ppv-enrichment/queue/all-ppv` → Queue all unmatched PPV
- **GET** `/api/ppv-enrichment/settings` → Configuration info
- **Status:** Routes defined but rarely called

### 6. **Background Scheduler** ✅
- **File:** `services/scheduler.py`
- **Task:** `_enrich_ppv_events()` (hourly enrichment)
- **Integration:** Added to `_check_and_sync()` periodic check
- **Status:** INTEGRATED but not actively enriching

---

## Why No Events Are Being Generated

### Root Causes (in order of likelihood):

1. **Enrichment task never called**
   - Scheduler runs, but `_enrich_ppv_events()` may not execute
   - No channels queued (ppv_enrichment_status is all NULL)

2. **Channels never queued for enrichment**
   - Status field: ALL 11,937 PPV channels have `ppv_enrichment_status = NULL`
   - Expected: channels should have status 'queued', 'processing', etc.
   - **This indicates the queue initialization step never ran**

3. **No matching/validation happening**
   - If queue existed, enrichment would attempt TheSportsDB matching
   - Channel-event associations would be created
   - None exist → enrichment process not executing

4. **Service not instantiated with Flask context**
   - `PPVEnrichmentQueue` requires Flask app instance
   - May not have proper app context when scheduler calls it

---

## Data Currently in Database

| Metric | Count | Status |
|--------|-------|--------|
| PPV Channels | 11,937 | ✓ Loaded |
| PPV Channels Queued | 0 | ✗ None |
| Events | 0 | ✗ Not generated |
| Event-Channel Links | 0 | ✗ Not created |
| EPG Channels (from XMLTV) | 32,478 | ✓ Loaded |
| Regular EPG Mappings | 10,698 | ✓ Created |
| Enrichment Metadata | 0 | ✗ Not recorded |

---

## What Would Need to Happen to Generate EPG

### Step 1: Queue Channels
```python
queue_service = PPVEnrichmentQueue(app)
stats = queue_service.queue_channels_for_enrichment(ppv_channels)
# Should update ppv_enrichment_status from NULL → "queued"
# Should set ppv_enrichment_queue_id
# Should create SyncMetadata entries
```

### Step 2: Extract Event Info from Channel Names
```python
extractor = PPVEventExtractor()

# Parse "UFC 300: Volkanovski vs Yair" → extract teams, date
info = extractor.extract_all("UFC 300: Volkanovski vs Yair (2025-01-15 22:00)")
# Returns: {
#   "competitors": ("Volkanovski", "Yair"),
#   "date": datetime(2025, 1, 15, 22, 0),
#   "inferred_how": "full_date"
# }
```

### Step 3: Match to TheSportsDB
```python
thesportsdb = TheSportsDBService()
events = thesportsdb.get_next_league_events("133602")  # UFC or MMA league ID

# Find matching event in results
for event in events:
    if matches_channel_info(event, "Volkanovski", "Yair"):
        match_found = True
        break
```

### Step 4: Create Event Record
```python
event = Event(
    external_id="event_123456",
    source="thesportsdb",
    home_team_name="Volkanovski",
    away_team_name="Yair",
    scheduled_at=datetime(2025, 1, 15, 22, 0),
    is_ppv=True
)
db.session.add(event)
db.session.commit()
```

### Step 5: Link Channel to Event
```python
link = EventChannelLink(
    event_id=event.id,
    channel_id=channel.id,
    match_confidence=0.95,
    match_method="direct_search"
)
db.session.add(link)
db.session.commit()
```

### Step 6: Generate EPG XML
```python
# Now when EPG is requested, system can:
# 1. Find events from EventChannelLink
# 2. Generate XMLTV with program entries
# 3. Include team names, times, metadata
```

---

## How to Activate EPG Generation

### Option 1: Manual API Call
```bash
# Queue all PPV channels
curl -X POST http://localhost:8000/api/ppv-enrichment/queue/all-ppv

# Check status
curl http://localhost:8000/api/ppv-enrichment/status

# Run enrichment
curl -X POST http://localhost:8000/api/ppv-enrichment/process
```

### Option 2: Code-Based Activation
```python
# In app startup or management command
from services.ppv_enrichment_service import PPVEnrichmentQueue
from models import Channel, db

app = create_app()

with app.app_context():
    queue = PPVEnrichmentQueue(app)
    
    # Queue all PPV channels
    ppv_channels = Channel.query.filter_by(is_ppv=True).all()
    stats = queue.queue_channels_for_enrichment(ppv_channels)
    print(f"Queued {stats['queued']} channels")
    
    # Process queue
    process_stats = queue.process_queue(max_requests=25)
    print(f"Processed {process_stats['processed']} channels")
    print(f"Matched: {process_stats['matched']}")
```

### Option 3: Scheduler Activation
```python
# Ensure scheduler is running
from scheduler import schedule_sync_tasks

schedule_sync_tasks(app)
# This will call _enrich_ppv_events() hourly
```

---

## Current System Architecture

```
┌─ PPV Channels (11,937) ─┐
│  - is_ppv = True        │
│  - enrichment_status = NULL (not queued)
└────────────────┬────────┘
                 │
                 ▼
        ┌─ PPVEnrichmentQueue ─┐
        │  (NOT ACTIVATED)     │
        │  - queue_channels()  │
        │  - process_queue()   │
        └──────────┬───────────┘
                   │
        ┌──────────▼───────────┐
        │ PPVEventExtractor    │
        │ (TESTED - WORKING)   │
        │ - extract_teams()    │
        │ - extract_dates()    │
        └──────────┬───────────┘
                   │
        ┌──────────▼───────────┐
        │ TheSportsDBService   │
        │ (TESTED - WORKING)   │
        │ - get_events()       │
        │ - match_channels()   │
        └──────────┬───────────┘
                   │
        ┌──────────▼───────────┐
        │ Event Table (EMPTY)  │
        │ + EventChannelLink   │
        │ (NO RECORDS)         │
        └──────────┬───────────┘
                   │
        ┌──────────▼───────────┐
        │ EPG Generation       │
        │ (BLOCKED - no events)│
        │ - generate_epg()     │
        └──────────────────────┘
```

---

## Summary

| Component | Status | Issue |
|-----------|--------|-------|
| Database Schema | ✅ | Events & links tables exist |
| Service Code | ✅ | PPVEnrichmentQueue implemented |
| Event Extractor | ✅ | Tested & working |
| TheSportsDB Integration | ✅ | API verified functional |
| API Endpoints | ✅ | Routes registered |
| Data Generation | ❌ | **BLOCKED - Never activated** |
| Channel Queuing | ❌ | **Status fields NULL** |
| EPG Entry Generation | ❌ | **Depends on queued channels** |

---

## Next Steps to Enable EPG

1. **Verify scheduler is running**
   ```python
   # Check scheduler logs or add logging
   ```

2. **Call queue initialization endpoint**
   ```bash
   POST /api/ppv-enrichment/queue/all-ppv
   ```

3. **Monitor enrichment progress**
   ```bash
   GET /api/ppv-enrichment/status
   ```

4. **Manually trigger first enrichment run**
   ```bash
   POST /api/ppv-enrichment/process
   ```

5. **Verify events and links are created**
   ```bash
   python check_epg_status.py
   ```

6. **Confirm EPG generation includes enriched data**
   ```bash
   GET /playlist/<id>.m3u  # Should have enriched PPV
   GET /epg/<id>.xml       # Should have PPV program entries
   ```

---

## Recommendations

1. **Immediate:** Call `/api/ppv-enrichment/queue/all-ppv` to queue channels
2. **Short-term:** Enable automatic queuing in scheduler startup
3. **Medium-term:** Add UI for manual PPV enrichment triggers
4. **Long-term:** Monitor enrichment success rates and adjust strategies

Once activated, the system should generate EPG entries automatically for all matched PPV events.
