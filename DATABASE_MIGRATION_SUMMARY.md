# Database Migration Summary

## Overview
This document summarizes the migration from API-based channel querying to database-backed channel storage with periodic synchronization.

## What Changed

### 1. Database Schema Extensions
- **New Models**: `Channel` and `Category` tables for storing IPTV channel/category data locally
- **Updated Model**: `ChannelTag` now includes `updated_at` timestamp for stale data cleanup
- **Migrations Applied**:
  - `2024_03_add_channels_categories.py`: Creates channels and categories tables
  - `2024_04_add_channel_tag_updated_at.py`: Adds updated_at column to channel_tags

### 2. Sync System
- **New Service**: `services/sync_service.py` - `ChannelSyncService` 
  - Fetches channels/categories from IPTV API
  - Stores locally with `last_seen` timestamps
  - Marks channels as `is_active=False` instead of deleting (soft delete)
  - Uses upsert logic for efficient incremental updates

- **New Scheduler**: `services/scheduler.py` - `SyncScheduler`
  - Background daemon thread for periodic sync
  - Configurable interval via `SYNC_INTERVAL_HOURS` env var (default: 6 hours)
  - Automatically syncs all active accounts

- **New API Endpoints**:
  - `POST /api/accounts/<id>/sync` - Manual sync for specific account
  - `POST /api/sync/all` - Manual sync for all accounts
  - `GET /api/accounts/<id>/sync/status` - Check sync status (last sync time, channel count)

### 3. Preview Endpoint Migration
- **Updated**: `/api/accounts/<id>/preview` now uses hybrid approach
  - Checks if channels are synced to database
  - Uses `preview_playlist_from_db()` for database path (fast, supports pagination)
  - Falls back to `preview_playlist_from_api()` if not synced (backward compatible)
  - Returns `using_database: true/false` to indicate data source

- **New Endpoint**: `/api/channels/preview` - Cross-account channel preview
  - Filter by tags across all accounts (or specific account_ids)
  - Search by channel name
  - Pagination support
  - Only works with synced accounts (requires database)

### 4. Tag Processing Migration
- **Updated**: `/api/accounts/<id>/process-tags` now uses hybrid approach
  - Checks if channels are synced to database
  - Uses `_process_tags_from_channels()` for database path
  - Falls back to `_process_tags_from_api()` if not synced
  - Returns `using_database: true/false` to indicate data source

- **Timestamp-Based Cleanup**: Tag processing now uses `updated_at` column
  - Mark processing start time
  - Update existing tags with current timestamp
  - Create new tags with current timestamp
  - Delete only tags where `updated_at < processing_start` (stale tags)
  - Returns stats: `tags_created`, `tags_updated`, `tags_removed`

### 5. Tags API Enhancement
- **Updated**: `/api/tags` now supports query parameters
  - `?account_id=X` - Filter tags to specific account
  - `?with_counts=true` - Include channel counts per tag
  - Without params: returns all tags across all accounts (cross-account support)

### 6. UI Improvements
- **Accounts Page** (`templates/accounts.html`):
  - Shows sync status badge (Database/API)
  - Displays last sync time and channel count
  - Manual sync button with progress indicator
  - Sync button refreshes display after completion

- **Preview Page** (`templates/test.html`):
  - Shows data source indicator (Database/API badge)
  - Visual feedback for which data source is being used

## Performance Benefits

### Memory Management
- **Before**: Loading 10,000+ channels with tags caused OOM kills
- **After**: Database queries with pagination, lazy loading, and batched tag loading (500-1000 at a time)

### Speed
- **Database Path**: Sub-second response times with proper indexes
- **API Fallback**: Still available for backward compatibility

### Efficiency
- **Incremental Sync**: Only updates changed channels, marks inactive instead of deleting
- **Periodic Sync**: Background updates keep data fresh without manual intervention
- **Smart Cleanup**: Tag processing only removes stale tags, preserves valid ones

## Backward Compatibility

All changes maintain backward compatibility:
- API fallback ensures accounts work even if not synced
- Existing filters, rulesets, and tag rules work unchanged
- M3U/EPG endpoints continue to function
- No breaking changes to existing workflows

## Configuration

### Environment Variables
- `SYNC_INTERVAL_HOURS` - Periodic sync interval (default: 6)
- `DATABASE_URL` - Database location (unchanged)
- `SECRET_KEY` - Flask secret key (unchanged)

### Database Location
- Docker: `/app/data/iptv_proxy.db`
- Local: Varies (check `DATABASE_URL` env var)

## Usage Guide

### Manual Sync
1. Go to Accounts page
2. Click sync button (circular arrow icon) for specific account
3. Wait for sync to complete (shows progress)
4. Status badge updates to "Database synced" with channel count

### Automatic Sync
- Runs every 6 hours by default (configurable)
- Syncs all active accounts
- Logs sync activity to console

### Cross-Account Tag Filtering
Use the new `/api/channels/preview` endpoint:
```
GET /api/channels/preview?tags=US,HD&search=ESPN&limit=50
```

### Checking Sync Status
```
GET /api/accounts/1/sync/status
```
Returns:
```json
{
  "synced": true,
  "last_sync": "2024-03-15T10:30:00",
  "channel_count": 8542,
  "category_count": 127
}
```

## Testing Recommendations

1. **Test database-based preview**: Sync an account, verify preview works
2. **Test API fallback**: Preview un-synced account, verify fallback works
3. **Test tag processing from database**: Process tags on synced account
4. **Test tag processing from API**: Process tags on un-synced account
5. **Test cross-account preview**: Sync multiple accounts, filter by shared tags
6. **Test sync status UI**: Verify badges and timestamps display correctly
7. **Test timestamp cleanup**: Change rulesets, reprocess tags, verify old tags removed

## Known Limitations

1. **SQLite Limitations**: Used table recreation for `updated_at` migration (can't use non-constant DEFAULT)
2. **Cross-Account Preview**: Only works with synced accounts (requires database)
3. **Large Account Performance**: First sync for 10,000+ channel account may take 1-2 minutes

## Future Enhancements

- [ ] Progress indicators during sync (websocket/SSE)
- [ ] Sync error recovery and retry logic
- [ ] Sync history/audit log
- [ ] Configurable sync schedules per account
- [ ] Selective sync (categories only, channels only)
- [ ] Database vacuum/optimize tools
- [ ] Cross-account playlist configs using database queries
