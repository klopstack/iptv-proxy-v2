# PPV Event Enrichment Service

## Overview

The PPV Event Enrichment Service is a background processing system that automatically enriches PPV (Pay-Per-View) channels with detailed event information from TheSportsDB. It uses a queue-based architecture with intelligent rate limiting to respect the free tier API limits (~500 requests/day).

**Key Features:**
- ✅ Automatic background enrichment on hourly schedule
- ✅ Rate-limited API calls (respects free tier: 500/day limit)
- ✅ Queue-based processing with persistent tracking
- ✅ Tiered matching strategies (Direct Search → Calendar Browse)
- ✅ Automatic retry with exponential backoff
- ✅ Manual enrichment triggering via API
- ✅ Real-time status monitoring and statistics

## Architecture

### Components

**1. PPVEnrichmentQueue Service** (`services/ppv_enrichment_service.py`)
```
Queue Manager
├─ Queue channels for enrichment
├─ Process queue with rate limiting
├─ Track enrichment progress
└─ Manage API usage tracking

Services Used
├─ TheSportsDBService (API calls)
├─ PPVEventExtractor (event matching)
└─ Database (Channel, Event, EventChannelLink models)
```

**2. Scheduler Integration** (`services/scheduler.py`)
```
Hourly Task: _enrich_ppv_events()
├─ Check if PPV enrichment is due
├─ Call queue.process_queue()
├─ Log statistics
└─ Respect rate limits automatically
```

**3. API Endpoints** (`routes/ppv_enrichment.py`)
```
GET  /api/ppv-enrichment/status             - Queue status & statistics
POST /api/ppv-enrichment/process            - Manual enrichment trigger
POST /api/ppv-enrichment/queue/channels     - Queue specific channels
POST /api/ppv-enrichment/queue/all-ppv      - Queue all PPV channels
GET  /api/ppv-enrichment/settings           - Enrichment configuration
```

## Rate Limiting Strategy

### TheSportsDB Free Tier Limits

```
Rate Limit:         30 requests/minute
Window:             60 seconds (per-minute rolling window)
Conservative Limit: 25 requests/minute (safety margin)
```

### Implementation Details

**Request Throttling:**
- Maximum 30 requests per minute (official API limit)
- Conservative limit: 25 requests/minute (with safety margin)
- Automatic pause if limit would be exceeded
- Automatic resume when per-minute window resets

**Per-Minute Tracking:**
- Persistent request counter per minute (SyncMetadata)
- Automatic reset every 60 seconds
- Prevents exceeding quota even across restarts

**Smart Processing:**
- Stops processing if per-minute limit would be exceeded
- Resumes automatically when window resets
- Each request is conservative (~1 API call per channel using tiered strategies)

## Processing Flow

### Queue Lifecycle

```
1. Channel Marked as PPV
   ↓
2. Queue via API or scheduler
   │ └─ Set ppv_enrichment_status = 'queued'
   │ └─ Assign ppv_enrichment_queue_id
   ↓
3. Hourly Scheduler Check
   │ └─ Call _enrich_ppv_events()
   ├─ Check API rate limit
   ├─ Get next batch (10 channels)
   └─ Process each channel
   ↓
4. For Each Channel
   │ ├─ Extract event name
   │ ├─ Try matching to TheSportsDB
   │ │  ├─ Tier 1: Direct Search (team names)
   │ │  └─ Tier 2: Calendar Browse (date-based)
   │ ├─ Create Event record
   │ ├─ Link Channel to Event
   │ └─ Update ppv_enrichment_status
   ↓
5. Final Status
   ├─ 'matched' - Successfully linked to event
   ├─ 'no_match' - Tried 3 times, no match found
   ├─ 'retry_pending' - Waiting for retry (< 3 attempts)
   └─ 'error' - Unexpected error occurred
```

### Enrichment Statuses

| Status | Meaning | Action |
|--------|---------|--------|
| `queued` | Ready to process | Wait for scheduler |
| `processing` | Currently being matched | In progress |
| `matched` | Successfully linked to event | Done, visible to users |
| `no_match` | Tried 3 times, no match | Dequeued, no further attempts |
| `retry_pending` | Attempt < 3, will retry | Wait for next scheduler run |
| `error` | Unexpected error | Will retry, error logged |

## Configuration

### Default Settings

```python
# Batch processing
BATCH_SIZE = 10  # Channels per batch

# Rate limiting
REQUESTS_PER_MINUTE = 25  # TheSportsDB official limit is 30/minute
REQUEST_INTERVAL_SECONDS = 2.4  # 60 / 25

# Retry logic
MAX_RETRY_ATTEMPTS = 3  # Max attempts before marking no_match
DEFAULT_RETRY_DELAY_MINUTES = 60  # Wait 1 hour before next batch

# API limits
THESPORTSDB_REQUESTS_PER_MINUTE = 30  # Official API limit
THESPORTSDB_REQUEST_WINDOW_SECONDS = 60  # 1-minute rolling window
```

### Customization

To adjust settings, modify `PPVEnrichmentQueue` initialization:

```python
# In app initialization or scheduler setup
queue = PPVEnrichmentQueue(
    app,
    batch_size=15,  # Process more channels per batch
    requests_per_minute=28,  # Get closer to limit (max 30)
)
```

## API Usage

### 1. Get Enrichment Status

Get current queue status, API usage, and progress:

```bash
curl http://localhost:8000/api/ppv-enrichment/status
```

**Response:**
```json
{
  "queue_status": {
    "queued": 245,
    "processing": 0,
    "retry_pending": 12,
    "matched": 1203,
    "no_match": 45,
    "error": 8
  },
  "cumulative_stats": {
    "total_queued": 1513,
    "total_processed": 1268,
    "total_failures": 8
  },
  "api_usage": {
    "requests_this_minute": 8,
    "minute_limit": 30,
    "requests_remaining": 22,
    "minute_window_reset_at": "2026-01-02T20:16:30+00:00",
    "requests_per_minute_limit": 25
  },
  "timing": {
    "last_run": "2026-01-02T20:15:00+00:00",
    "next_run": "2026-01-02T21:15:00+00:00"
  }
}
```

### 2. Manually Process Queue

Trigger enrichment immediately (useful for testing):

```bash
curl -X POST http://localhost:8000/api/ppv-enrichment/process \
  -H "Content-Type: application/json" \
  -d '{"max_requests": 20}'
```

**Response:**
```json
{
  "processed": 10,
  "matched": 8,
  "failed": 1,
  "retried": 1,
  "api_requests_made": 9,
  "rate_limited": false
}
```

### 3. Queue Specific Channels

Queue particular channels for enrichment:

```bash
curl -X POST http://localhost:8000/api/ppv-enrichment/queue/channels \
  -H "Content-Type: application/json" \
  -d '{
    "channel_ids": [123, 456, 789],
    "account_id": 1
  }'
```

**Response:**
```json
{
  "queued": 3,
  "skipped_already_matched": 0,
  "total_queued": 248
}
```

### 4. Queue All PPV Channels

Queue all unmatched PPV channels:

```bash
curl -X POST http://localhost:8000/api/ppv-enrichment/queue/all-ppv \
  -H "Content-Type: application/json" \
  -d '{"account_id": 1}'
```

### 5. Get Settings

View current enrichment configuration:

```bash
curl http://localhost:8000/api/ppv-enrichment/settings
```

**Response:**
```json
{
  "batch_size": 10,
  "requests_per_hour": 20,
  "request_interval_seconds": 180,
  "max_retry_attempts": 3,
  "thesportsdb_daily_limit": 500,
  "thesportsdb_free_limit": true
}
```

## Database Schema

### New Columns in `channels` Table

```sql
ppv_enrichment_status VARCHAR(20)      -- Current enrichment status
ppv_enrichment_queue_id VARCHAR(100)   -- Unique queue identifier
ppv_enrichment_attempts INTEGER        -- Number of enrichment attempts
ppv_enrichment_error TEXT              -- Last error message
ppv_enrichment_last_attempt DATETIME   -- Timestamp of last attempt
```

### Tracking Tables

**SyncMetadata (existing)** - Persistent state:
```
ppv_enrichment_queued_count            -- Total channels queued
ppv_enrichment_processed_count         -- Total channels processed
ppv_enrichment_failures                -- Total failures
ppv_enrichment_last_run                -- Last enrichment timestamp
ppv_enrichment_next_run                -- Next scheduled run
thesportsdb_requests_today             -- API requests made today
thesportsdb_requests_reset_at          -- Daily quota reset time
```

### Event Linking

**Event** ↔ **EventChannelLink** ↔ **Channel**
- Event: External event data from TheSportsDB
- EventChannelLink: Maps channels to events with confidence/method
- Channel: PPV channel being enriched

## Monitoring & Troubleshooting

### Check Enrichment Progress

```bash
# Get current status
curl http://localhost:8000/api/ppv-enrichment/status | jq '.queue_status'

# Check API usage
curl http://localhost:8000/api/ppv-enrichment/status | jq '.api_usage'
```

### Manual Trigger for Testing

```bash
# Process immediately with limited requests
curl -X POST http://localhost:8000/api/ppv-enrichment/process \
  -H "Content-Type: application/json" \
  -d '{"max_requests": 3}'
```

### View Channel Enrichment Status

```sql
SELECT name, ppv_enrichment_status, ppv_enrichment_attempts, 
       ppv_enrichment_error, ppv_enrichment_last_attempt
FROM channels
WHERE is_ppv = TRUE
ORDER BY ppv_enrichment_status, ppv_enrichment_last_attempt DESC
LIMIT 20;
```

### Database Query Examples

```sql
-- Channels still queued for enrichment
SELECT COUNT(*) FROM channels 
WHERE is_ppv = TRUE AND ppv_enrichment_status IN ('queued', 'retry_pending');

-- Recently matched channels
SELECT name, ppv_enrichment_last_attempt FROM channels
WHERE ppv_enrichment_status = 'matched'
ORDER BY ppv_enrichment_last_attempt DESC
LIMIT 10;

-- Channels with errors
SELECT name, ppv_enrichment_error, ppv_enrichment_attempts FROM channels
WHERE ppv_enrichment_status = 'error'
LIMIT 10;
```

### Common Issues & Solutions

**Issue:** Enrichment not running
- **Check:** Scheduler is running (`GET /api/sync-status`)
- **Check:** PPV channels are marked with `is_ppv = TRUE`
- **Solution:** Manually trigger: `POST /api/ppv-enrichment/process`

**Issue:** API rate limit hit (requests_remaining = 0)
- **Check:** Status shows `requests_today ≈ 500`
- **Solution:** Wait for daily reset (UTC midnight)
- **Alternative:** Upgrade to TheSportsDB premium API

**Issue:** Channels marked "no_match" after 3 attempts
- **Check:** Channel name format in `ppv_enrichment_error`
- **Solution:** Update channel name with standard format (e.g., "Arsenal vs Chelsea")

**Issue:** Memory usage increasing
- **Check:** Batch size is reasonable (default 10)
- **Check:** No channels stuck in "processing" status
- **Solution:** Restart if needed, queries paginate automatically

## Persistence & Restart Behavior

The enrichment system is designed to survive restarts:

1. **Queue State Persisted** - `ppv_enrichment_status` stored in database
2. **API Usage Tracked** - Daily requests counted across restarts
3. **Progress Tracking** - Cumulative stats in SyncMetadata
4. **Automatic Resume** - Restart continues from where it left off

### Example Scenario

```
Day 1, 10:00 AM - Start processing, 250 requests made
Day 1, 12:00 PM - API limit hit, enrichment pauses
[App restarts]
Day 1, 1:00 PM - Scheduler detects: 250 requests today, 250 remaining
Day 2, 12:01 AM - UTC midnight hits, daily reset, resumes
```

## Performance Considerations

### Processing Speed

- **Batch Size:** 10 channels/batch
- **Rate Limit:** 20 requests/hour
- **Expected:** ~10 channels/hour matched
- **Daily Capacity:** ~200 channels/day

### Database Impact

- **Indexes:** `ppv_enrichment_status`, `ppv_enrichment_queue_id`
- **Disk:** ~500 bytes per enrichment attempt
- **Queries:** Efficient pagination, no N+1 queries

### Network Requests

- **Per Channel:** 1-2 TheSportsDB API calls (Direct Search + optional Calendar Browse)
- **Timeout:** 5 seconds per request (reasonable for free tier)
- **Retries:** Automatic with backoff

## Future Enhancements

### Planned Improvements

1. **Multi-language Support**
   - Translate month names, team names
   - Handle regional league names

2. **Confidence-based Filtering**
   - Only show matches above confidence threshold
   - Manual review queue for low-confidence matches

3. **Webhook Integration**
   - Notify when enrichment completes for a channel
   - Export to external systems

4. **Premium API Support**
   - Switch to premium TheSportsDB API if key provided
   - Higher rate limits (10,000+/day)
   - Additional data (live scores, odds, etc.)

5. **Event Update Scheduling**
   - Periodic re-enrichment of matched events
   - Update status when events complete
   - Fetch live scores during events

## References

- **TheSportsDB API:** https://www.thesportsdb.com/api.php
- **Python Library:** `thesportsdb` package
- **Rate Limiting:** Conservative free tier (500/day)
- **Documentation:** See `docs/THESPORTSDB_IMPLEMENTATION_SUMMARY.md`
