# EPG Auto-Match Timeout Fix

## Problem
When running auto-match for accounts with thousands of channels, the operation would timeout with a "NetworkError when attempting to fetch resource" message. Additionally, the system was attempting to match filtered-out channels unnecessarily.

## Root Causes
1. **Long-running operation**: Matching 10,000+ channels can take several minutes
2. **Browser timeout**: Default fetch() timeout (typically 300s) was exceeded
3. **Server timeout**: Gunicorn worker timeout of 120s was insufficient for large accounts
4. **Unnecessary work**: Matching filtered-out (is_visible=False) channels that won't be displayed anyway

## Solutions Implemented

### 1. Skip Filtered Channels by Default
**Files**: `services/epg_service.py`, `routes/epg.py`
- Added `include_filtered` parameter (default: `False`) to `match_channels_to_epg()`
- By default, only matches visible channels (`is_visible=True`)
- Dramatically reduces processing time for accounts with many filtered channels
- Can override with `?include_filtered=true` query parameter if needed

```python
# Default: only match visible channels
stats = EpgService.match_channels_to_epg(account_id)

# Optional: include filtered channels
stats = EpgService.match_channels_to_epg(account_id, include_filtered=True)
```

### 2. Increased Server Timeout
**File**: `entrypoint.sh`
- Changed gunicorn timeout from 120s to 600s (10 minutes)
- Reasoning: EPG matching is a legitimate long-running operation that can take several minutes for large accounts
- Workers use gevent, so they can handle concurrent requests efficiently

```bash
exec gunicorn --bind 0.0.0.0:${PORT} --worker-class gevent --workers 4 --timeout 600 app:app
```

### 3. Frontend Timeout Handling
**File**: `templates/epg.html`
- Added AbortController with 600s (10 minute) timeout to match backend
- Improved error messages to suggest filtering by category for large accounts
- Added progress indication showing whether filtering is active

### 4. Backend Optimization (Already in Place)
**File**: `services/epg_service.py`
- Batch size reduced to 50 channels (from 100)
- Added `db.session.flush()` after commits to prevent memory buildup
- Progress logging every batch for monitoring
- Commits happen in batches, so progress is saved even if interrupted

### 5. PPV Channel Exclusion
**File**: `services/epg_service.py`
- Added automatic detection and skipping of PPV (Pay-Per-View) channels
- PPV channels update dynamically and typically don't have EPG data
- Reduces unnecessary matching attempts

## Usage Recommendations

### For Large Accounts (1000+ channels)
1. **Apply filters first**: Use channel filters to mark irrelevant channels as filtered out
2. **Filter by category**: Use the category dropdown to match channels in smaller groups
3. **Monitor logs**: Server logs show progress every 50 channels processed
4. **Be patient**: Operation may take 5-10 minutes for 10,000+ channels

### Expected Performance Improvement
For an account with:
- 10,000 total channels
- 5,000 filtered out by user filters
- 500 PPV channels

**Before**: Attempts to match all 10,000 channels
**After**: Only matches 4,500 channels (55% reduction)

### Frontend Behavior
- Shows estimated time based on whether filtering is active
- Displays helpful error messages if timeout occurs
- Suggests category filtering for better performance

## Technical Details

### Channel Filtering
- By default, `is_visible=False` channels are skipped
- Override with `include_filtered=true` query parameter
- Respects the "Include filtered out channels" checkbox state in UI

### Batch Processing
- Default batch size: 50 channels
- Each batch commits to database (progress is saved)
- Session flushed after each batch to prevent memory issues
- Progress logged: `channels_processed/total (XX.X%) - XX matched, XX unmatched (visible only)`

### Timeout Chain
1. **Browser**: 600s (fetch AbortController)
2. **Gunicorn**: 600s (worker timeout)
3. **Database**: 30s (SQLite lock timeout - separate concern)

### Error Messages
- **"Operation timed out after 10 minutes"**: Try filtering by category
- **"Network error or server timeout"**: For large channel lists, filter by category first
- Server logs will show how far matching progressed before timeout

## Testing
```bash
# Run tests including new filtering behavior
pytest tests/test_ppv_detection.py -v

# Test shows:
# - PPV channels are automatically skipped
# - Filtered channels are excluded by default
# - include_filtered=True processes all channels
```

To test with large datasets:
```bash
# Monitor logs while running auto-match
docker logs -f iptv-proxy-v2

# Look for progress messages like:
# EPG matching: Found 500 active channels (visible only) for account 1
# EPG matching progress: 50/500 channels (10.0%) - 35 matched, 5 unmatched
```

## Future Improvements
For extremely large accounts (20,000+ channels), consider:
1. Async/background task processing with Celery or similar
2. WebSocket progress updates to frontend
3. Pagination of matching results
4. Chunked HTTP responses with streaming
