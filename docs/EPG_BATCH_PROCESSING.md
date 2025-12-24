# EPG Batch Processing Implementation

## Problem
The original EPG auto-match implementation processed ALL channels in a single HTTP request, which caused:
1. **Browser timeouts** for large accounts (10+ minutes)
2. **No progress visibility** for users
3. **All-or-nothing failure** - if timeout occurred, no work was saved
4. **Poor user experience** - long waits with no feedback

Even though the backend committed in batches, the HTTP response wasn't sent until the entire operation completed.

## Solution: Category-by-Category Processing

Instead of processing all channels at once, the new implementation:

1. **Fetches all categories** for the account
2. **Processes each category sequentially** in separate HTTP requests
3. **Shows real-time progress** with a progress bar
4. **Accumulates statistics** across all categories
5. **Continues on error** - if one category fails, others still process

### Benefits
- ✅ **No timeouts** - Each category processes quickly (typically < 2 minutes)
- ✅ **Real-time progress** - Users see exactly what's happening
- ✅ **Graceful degradation** - Partial success if some categories fail
- ✅ **Work is saved** - Each category commits independently
- ✅ **Better UX** - Progress bar, category names, running totals

## Implementation Details

### Frontend (`templates/epg.html`)

**Main Function: `runAutoMatch()`**
- If specific category selected → calls `matchSingleCategory()`
- If no category selected → calls `matchAllCategoriesSequentially()`

**Function: `matchSingleCategory(accountId, categoryId, skipThreshold, listContainer, alertDiv)`**
- Makes single API call to `/api/epg/match/{accountId}?category_id={categoryId}`
- Displays results
- Same behavior as before, just extracted for reuse

**Function: `matchAllCategoriesSequentially(accountId, skipThreshold, listContainer, alertDiv)`**
1. Fetches categories: `GET /api/categories?account_id={accountId}&include_empty=false`
2. Filters to categories with `visible_count > 0`
3. For each category:
   - Updates progress UI with:
     - Category name
     - Progress percentage
     - Progress bar
     - Running total of matches
   - Makes API call: `POST /api/epg/match/{accountId}?category_id={categoryId}`
   - 2-minute timeout per category (not 10 minutes for all!)
   - Accumulates statistics
   - Continues even if one category fails
4. Displays final accumulated results

### Backend (No Changes Required!)

The existing API already supports category filtering:
```
POST /api/epg/match/{account_id}?category_id={category_id}&skip_threshold={threshold}&include_filtered={bool}
```

By calling this multiple times (once per category), we:
- Keep each request short and fast
- Get automatic database commits after each category
- Maintain proper progress tracking

### UI Flow

**Before (Single Category Selected):**
```
[Loading spinner]
→ Match category
→ Show results
```

**After (No Category / All Categories):**
```
[Progress bar showing "Sports | Category 1 of 25 (4%)"]
[Running total: "Matched so far: 145 channels"]
→ Match category 1
→ Match category 2
→ Match category 3
...
→ Show final accumulated results
```

## Performance Characteristics

### Before
- **Single HTTP request**: 10+ minutes for 10,000 channels
- **Timeout**: Guaranteed for large accounts
- **Progress**: None visible to user
- **Failure mode**: All-or-nothing

### After
- **Multiple HTTP requests**: ~30-120 seconds per category
- **Timeout**: Only if individual category takes > 2 minutes (rare)
- **Progress**: Real-time with category names and percentage
- **Failure mode**: Graceful - other categories still process

### Example Timings
Account with 10,000 channels across 25 categories (400 channels avg per category):

| Metric | Before | After |
|--------|--------|-------|
| Total time | 10+ minutes | 5-10 minutes |
| Visible progress | None | Real-time |
| Timeout risk | High | Low |
| User experience | Poor | Good |
| Recovery from errors | None | Automatic |

## Configuration

### Timeouts
- **Per-category timeout**: 120 seconds (2 minutes)
- **Backend batch size**: 50 channels
- **Gunicorn worker timeout**: 600 seconds (10 minutes)

These settings allow:
- Categories with up to ~3,000 channels to complete
- Progress updates every 50 channels
- Recovery if network hiccups

### Filtering Behavior
- **Default**: Only processes `is_visible=True` channels
- **PPV detection**: Automatically skips PPV channels
- **Category filtering**: Only processes categories with `visible_count > 0`

## Error Handling

### Category-Level Errors
If a single category fails:
- Error logged to console
- Processing continues with next category
- Final results show what was completed
- User sees partial success

### Network Errors
If network fails mid-processing:
- Work up to that point is already committed
- User sees results for completed categories
- Can re-run to complete remaining categories
- Already-matched channels are skipped (via `skip_threshold`)

### Timeout Handling
If individual category times out:
- 2-minute timeout is generous for most categories
- If hit, that category skips and next one processes
- Can always match that specific category manually later

## Testing

### Test Scenarios

1. **Small account (< 1000 channels)**
   - Should complete in seconds
   - No noticeable difference from before

2. **Large account (10,000+ channels)**
   - Shows progress through all categories
   - Completes without timeout
   - User can see real-time updates

3. **Account with filtered categories**
   - Only processes categories with visible channels
   - Skips empty/hidden categories
   - Saves time

4. **Network interruption**
   - Completed categories already saved
   - Can re-run to finish remaining
   - No duplicate work (skip_threshold)

### Manual Testing
```bash
# 1. Rebuild container with changes
docker-compose down
docker-compose up -d --build

# 2. Navigate to EPG tab in web UI
# 3. Select account with many channels
# 4. Click "Auto-Match" (don't select specific category)
# 5. Observe:
#    - Progress bar updates
#    - Category names shown
#    - Running total increases
#    - No timeout even for large accounts
```

## Migration Notes

### Backwards Compatibility
✅ **Fully backwards compatible**
- Old single-category behavior unchanged
- API endpoints unchanged
- Database schema unchanged
- Only frontend JavaScript changed

### Upgrade Path
1. Pull latest code
2. Rebuild Docker container
3. No database migrations needed
4. Works immediately with existing data

## Future Enhancements

Possible improvements:
1. **Parallel category processing** - Process 2-3 categories at once
2. **WebSocket streaming** - Real-time server logs to browser
3. **Background jobs** - Queue work, check status later
4. **Smart ordering** - Process smallest categories first for faster perceived progress
5. **Resume capability** - Remember where it left off if interrupted

## Summary

This implementation solves the timeout problem through **architectural change** rather than just increasing timeouts:
- ✅ Breaks work into manageable chunks
- ✅ Shows real-time progress
- ✅ Saves work incrementally
- ✅ Handles errors gracefully
- ✅ No backend changes required
- ✅ Fully backwards compatible

The key insight: **There's no need for a single HTTP request to process all channels** - breaking it into category-sized chunks provides better UX and reliability.
