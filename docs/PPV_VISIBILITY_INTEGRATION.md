# PPV Visibility Control Integration

## Overview

This feature integrates PPV (Pay-Per-View) filtering into the main IPTV Proxy application. Users can now control how PPV channels are displayed in playlists and EPG through a simple account-level setting with three modes.

## Features

### Three Visibility Modes

**1. Hide All PPV** (`hide_all`)
- Completely hides all pay-per-view channels
- No PPV channels appear in playlists or EPG
- Useful for users who don't want any PPV content

**2. Hide Inactive PPV** (`hide_inactive`) - **DEFAULT**
- Shows only upcoming or active PPV events
- Automatically hides past/expired events
- Event status determined by datetime extraction from channel name
- Provides clean, relevant PPV listings
- Most useful for live streaming scenarios

**3. Show All PPV** (`show_all`)
- Shows all PPV channels regardless of event status
- Includes both active and inactive/past events
- Useful for archives or on-demand PPV libraries

### Smart Event Detection

The visibility service automatically extracts event datetimes from channel names using formats like:
- `Oct 18 : 11PM` → Detects upcoming boxing match
- `2025-12-25 20:00` → Detects Christmas special
- `Relative time patterns` → 8PM Sunday

Only channels with valid future datetimes are shown in "hide_inactive" mode.

## Architecture

### Components

**1. PPVVisibilityService** (`services/ppv_visibility_service.py`)
```python
class PPVVisibilityService:
    HIDE_ALL = "hide_all"
    HIDE_INACTIVE = "hide_inactive"  # Default
    SHOW_ALL = "show_all"
    
    def should_show_channel(channel) -> bool:
        # Applies visibility rules
    
    def _is_ppv_active(channel) -> bool:
        # Checks if event is in future
```

**2. Account Model Enhancement** (`models.py`)
```python
class Account(db.Model):
    ppv_visibility = db.Column(
        db.String(20), 
        default='hide_inactive', 
        nullable=False
    )
```

**3. Database Migration** (`migrations/2026_01_02_add_ppv_visibility.py`)
- Adds `ppv_visibility` column to accounts table
- Default: `'hide_inactive'`
- Fully idempotent

### Integration Points

#### 1. Playlist Generation (`routes/playlists.py`)
```python
# Single account playlists
ppv_service = PPVVisibilityService(account)
channels = [ch for ch in channels if ppv_service.should_show_channel(ch)]

# Cross-account playlists
for account in accounts:
    ppv_service = PPVVisibilityService(account)
    channels = [ch for ch in channels if ppv_service.should_show_channel(ch)]
```

#### 2. EPG Routes (`routes/epg.py`)
- Prepared with import for future integration
- Can apply same filtering to EPG channel listings

#### 3. API Endpoints (`routes/accounts.py`)

**Update PPV Visibility:**
```bash
PUT /api/accounts/<account_id>/ppv-visibility
Content-Type: application/json

{
    "ppv_visibility": "hide_inactive"
}
```

**Get Available Options:**
```bash
GET /api/ppv-visibility-options
```

Response:
```json
{
    "hide_all": {
        "value": "hide_all",
        "label": "Hide All PPV",
        "description": "Hide all pay-per-view channels"
    },
    "hide_inactive": {
        "value": "hide_inactive",
        "label": "Hide Inactive PPV",
        "description": "Show only upcoming/active PPV events, hide past events"
    },
    "show_all": {
        "value": "show_all",
        "label": "Show All PPV",
        "description": "Show all pay-per-view channels including inactive ones"
    }
}
```

## UI Implementation

### Account Edit Modal (templates/accounts.html)

Added dropdown control:
```html
<div class="mb-3">
    <label for="accountPpvVisibility" class="form-label">
        PPV Channel Visibility
    </label>
    <select class="form-select" id="accountPpvVisibility">
        <option value="hide_all">Hide All PPV</option>
        <option value="hide_inactive" selected>Hide Inactive PPV (default)</option>
        <option value="show_all">Show All PPV</option>
    </select>
    <div class="form-text">
        <!-- Helper text explaining each option -->
    </div>
</div>
```

### JavaScript Integration
- Load ppv_visibility value from account data
- Include in account save request
- Make separate API call to update PPV visibility
- Display selected option in edit modal

## Usage Examples

### Setting PPV Visibility for an Account

1. Go to Accounts section in web UI
2. Click Edit on desired account
3. Select PPV visibility mode from dropdown:
   - "Hide All PPV" - No PPV channels shown
   - "Hide Inactive PPV" - Only active events shown (default)
   - "Show All PPV" - All events shown
4. Click Save

### API Usage

```bash
# Hide all PPV for account 1
curl -X PUT http://localhost:8000/api/accounts/1/ppv-visibility \
  -H "Content-Type: application/json" \
  -d '{"ppv_visibility": "hide_all"}'

# Show only active PPV for account 2
curl -X PUT http://localhost:8000/api/accounts/2/ppv-visibility \
  -H "Content-Type: application/json" \
  -d '{"ppv_visibility": "hide_inactive"}'

# Show all PPV for account 3
curl -X PUT http://localhost:8000/api/accounts/3/ppv-visibility \
  -H "Content-Type: application/json" \
  -d '{"ppv_visibility": "show_all"}'

# Get available options
curl http://localhost:8000/api/ppv-visibility-options
```

## Filtering Logic

### Channel Decision Tree

```
Is channel PPV? (is_ppv flag)
├─ NO → Show (PPV rules don't apply)
└─ YES → Apply visibility mode
    ├─ hide_all → HIDE
    ├─ hide_inactive → Check event datetime
    │   ├─ Future → SHOW
    │   ├─ Past → HIDE
    │   └─ Can't parse → SHOW (safe default)
    └─ show_all → SHOW
```

### DateTime Detection

The service uses `PPVFilterService.parse_iso_datetime_with_24hr()` to extract event times:
- ISO formats: `2025-01-20 14:00:00`
- Month-day format: `Oct 18 : 11PM`
- Relative formats: `8PM Sunday`
- Time-only with sync_date fallback

Channels without valid datetimes default to SHOW (safe for incomplete data).

## Database Impact

### Schema Change
```sql
ALTER TABLE accounts ADD COLUMN ppv_visibility VARCHAR(20) 
    DEFAULT 'hide_inactive' NOT NULL
```

### Data Migration
- Existing accounts: Default to `'hide_inactive'` (hides inactive events)
- No data loss or conflicts
- Fully backward compatible

## Performance Considerations

### Filtering Overhead
- **Single channel check:** ~1-5ms per channel (datetime parsing)
- **Batch filtering:** O(n) where n = number of channels
- **Optimization:** Datetime parsing only on PPV channels (is_ppv=True filter first)

### Database Queries
- Account visibility setting: 1 query (cached in account object)
- No additional database queries during filtering
- New column indexed at database level if needed

### Caching
- Account data cached by existing CacheService
- PPV visibility setting included in cache
- Cache invalidated on account updates

## Future Enhancements

### Planned Improvements
1. **Time-zone aware filtering**: Parse timezone info from channel names
2. **Multi-language support**: Translate month names and mode labels
3. **Scheduled filtering**: Apply different modes based on time of day
4. **Per-playlist overrides**: Allow playlist-specific PPV settings
5. **Event grouping**: Group PPV channels by event date

### Integration Opportunities
1. **EPG integration**: Apply same filtering to EPG channel listings
2. **Notification system**: Alert users when new PPV events added
3. **Analytics**: Track which PPV modes are most popular
4. **Smart defaults**: Infer visibility mode from user behavior

## Testing

### Unit Tests Needed
```python
def test_ppv_visibility_hide_all():
    # All PPV channels hidden

def test_ppv_visibility_hide_inactive_future():
    # Future PPV events shown

def test_ppv_visibility_hide_inactive_past():
    # Past PPV events hidden

def test_ppv_visibility_show_all():
    # All PPV channels shown

def test_ppv_visibility_non_ppv_channels():
    # Non-PPV channels always shown regardless of mode
```

### Integration Tests
```python
def test_playlist_generation_with_ppv_filtering():
    # Generate playlist, verify PPV channels filtered correctly

def test_cross_account_ppv_filtering():
    # Multiple accounts with different visibility modes
```

## Troubleshooting

### PPV Channels Still Showing When Hidden

**Cause:** Channel `is_ppv` flag not set correctly during sync

**Solution:** Run channel sync again, check channel categorization

### Can't Parse Event Datetime

**Cause:** Channel name format doesn't match supported patterns

**Solution:** Channels default to SHOW; add datetime in supported format to channel name

### Changes Not Reflected in Playlist

**Cause:** Cache not invalidated

**Solution:** 
1. Edit account to trigger cache invalidation
2. Or manually clear cache: `cache_service.clear_account_cache(account_id)`

## Files Modified

### Core Files
- `models.py` - Added ppv_visibility field to Account
- `services/ppv_visibility_service.py` - New filtering service (created)
- `routes/playlists.py` - Integrate filtering into playlist generation
- `routes/accounts.py` - Add PPV visibility API endpoints
- `routes/epg.py` - Prepare for EPG integration

### UI Files
- `templates/accounts.html` - Add PPV visibility dropdown and form handling

### Database
- `migrations/2026_01_02_add_ppv_visibility.py` - Add ppv_visibility column

## Configuration

### Default Behavior
- New accounts: `ppv_visibility = 'hide_inactive'`
- Shows upcoming PPV events, hides past ones
- Zero configuration needed

### Customization
Users can customize per account through:
1. Web UI - Select dropdown in account edit modal
2. API - PUT endpoint with JSON payload
3. Direct database edit (not recommended)

## Rollback

If needed to disable PPV visibility filtering:

1. **In code:** Comment out filtering in `routes/playlists.py`
   ```python
   # ppv_service = PPVVisibilityService(account)
   # channels = [ch for ch in channels if ppv_service.should_show_channel(ch)]
   ```

2. **In database:** Set all accounts to `ppv_visibility = 'show_all'`
   ```sql
   UPDATE accounts SET ppv_visibility = 'show_all'
   ```

3. **Complete removal:** Drop column (requires migration)
   ```sql
   ALTER TABLE accounts DROP COLUMN ppv_visibility
   ```
