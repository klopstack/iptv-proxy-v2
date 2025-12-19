# Performance Optimizations

This document describes performance optimizations implemented in IPTV Proxy v2.
## Memory Optimization (December 2025)

### Problem
With large channel counts (10,000+ channels), the application was running out of memory and timing out when:
1. Loading preview channels
2. Generating playlists
3. Filtering channels by tags

The issue was loading ALL channel tags into memory at once, even when only a small subset was needed for paginated results.

### Solution
Implemented lazy loading and batching strategies:

**Preview Endpoint (`/api/accounts/<id>/preview`)**:
- Only loads tags for channels that pass filters (not all channels)
- Uses batched queries (500 stream IDs at a time) to avoid huge IN clauses
- Loads tags for offset+limit range, not entire dataset

**Playlist Generation (`/playlist/<id>.m3u`)**:
- Pre-filters streams before loading tags
- Only loads tags when tag-based filters are active
- Batches tag queries (1000 stream IDs per batch)

**Impact**:
- Memory usage: 90%+ reduction for large accounts
- Response time: Sub-second for paginated requests
- No more worker timeouts or OOM kills

## UI Performance (December 2025)

### Problem
The tag filter dropdown was loading ALL tags for an account upfront, causing:
1. Very long load times (30+ seconds for accounts with thousands of unique tags)
2. Poor UX with massive multi-select dropdowns
3. Browser memory issues with large tag lists

### Solution
Implemented Jellyseerr-style autocomplete tag selector:

**Features**:
- **Autocomplete search**: Type to search, shows matching tags instantly
- **Lazy loading**: Only loads tags as you search (20 results max)
- **Tag chips**: Selected tags shown as dismissible badges
- **Fast API**: New `/api/accounts/<id>/tags/search?q=term` endpoint with indexed search
- **Debouncing**: 300ms delay to avoid excessive queries

**Database Optimization**:
- Added index on `tags.name` column for LIKE/ILIKE queries
- Search queries return results in milliseconds, not seconds

**Impact**:
- Tag search: < 100ms response time (vs 30+ seconds before)
- Memory: Minimal - only loads 20 tags at a time
- UX: Smooth autocomplete experience like Jellyseerr

## Database Indexes (December 2025)

### Problem
Users experienced significant slowdowns when selecting accounts on the preview channels page. The `/api/accounts/<account_id>/tags` endpoint was performing slow queries on the `channel_tags` table without proper indexes.

### Solution
Added database indexes to optimize tag-related queries:

1. **Individual column indexes:**
   - `ix_channel_tags_account_id` on `channel_tags.account_id`
   - `ix_channel_tags_tag_id` on `channel_tags.tag_id`

2. **Composite index:**
   - `idx_channel_tags_account_tag` on `(account_id, tag_id)`

### Impact
- **Account tag listing**: Significantly faster queries when loading tags for an account
- **Channel preview filtering**: More responsive when filtering channels by tags
- **Playlist generation**: Optimized tag-based filtering across accounts

### For New Installations
The indexes are automatically created when the database is initialized (via `db.create_all()` and automatic migrations).

### For Existing Installations

**Recommended: Use the migration system:**
```bash
python run_migrations.py
```

**Deprecated: Standalone script (still works but use migrations instead):**
```bash
python add_indexes.py
```

Both methods are idempotent and safe to run multiple times.

**Docker users:**
```bash
# Migrations run automatically on container restart
docker-compose restart iptv-proxy-v2

# Or run manually
docker exec -it iptv-proxy-v2 python run_migrations.py
```

**Note:** The migration system (`run_migrations.py`) runs automatically on every container startup via `entrypoint.sh`. This means indexes will be added automatically the next time your container restarts.

### Query Performance
The indexes optimize these common query patterns:

1. **Get tags for an account** (`/api/accounts/<id>/tags`):
   ```sql
   SELECT Tag.id, Tag.name, COUNT(ChannelTag.id)
   FROM tags JOIN channel_tags ON Tag.id = ChannelTag.tag_id
   WHERE ChannelTag.account_id = ?
   GROUP BY Tag.id, Tag.name
   ```
   - Uses: `ix_channel_tags_account_id` + `idx_channel_tags_account_tag`

2. **Filter channels by tags** (preview and playlist generation):
   ```python
   channel_tags_query = db.session.query(
       ChannelTag.stream_id, Tag.name
   ).join(Tag).filter(ChannelTag.account_id == account_id).all()
   ```
   - Uses: `idx_channel_tags_account_tag`

3. **Tag-based playlist configs**:
   - Composite index on `(account_id, tag_id)` speeds up joins and filters

### Technical Details

**Model Changes** (models.py):
```python
class ChannelTag(db.Model):
    account_id = db.Column(..., index=True)
    tag_id = db.Column(..., index=True)
    
    __table_args__ = (
        db.UniqueConstraint(...),
        db.Index("idx_channel_tags_account_tag", "account_id", "tag_id"),
    )
```

**Database Schema**:
- SQLite uses B-tree indexes for fast lookups
- Composite index allows efficient queries on both columns together
- Individual indexes cover single-column queries and JOIN operations

## Migration System

The project uses an idempotent migration system that runs automatically on container startup.

### How It Works

1. **Automatic**: Migrations run via `entrypoint.sh` on every container start
2. **Idempotent**: Safe to run multiple times - checks if changes are needed first
3. **Sequential**: Migrations execute in alphabetical order by filename
4. **Graceful**: Each migration handles errors and reports status

### Migration Files

Located in `migrations/` directory:
- `2024_01_add_indexes.py` - Adds performance indexes to channel_tags table

### Running Manually

```bash
# Run all migrations
python run_migrations.py

# Run specific migration (for testing)
python migrations/2024_01_add_indexes.py
```

### Creating New Migrations

1. Create file in `migrations/` with format: `YYYY_MM_description.py`
2. Implement `migrate(db_path)` function that returns `(success: bool, message: str)`
3. Make it idempotent - check if changes are needed before applying
4. Test with both fresh and existing databases

See `migrations/README.md` for detailed instructions and examples.

### Future Optimizations

Potential areas for further improvement:

1. **Caching**: Consider caching tag counts and lists with TTL
2. **Pagination**: Add pagination to tag listings for accounts with thousands of tags
3. **Query optimization**: Review N+1 queries in playlist generation
4. **Database**: Consider PostgreSQL for larger deployments (better index support)

### Monitoring

To check if indexes are being used (SQLite):
```bash
sqlite3 data/iptv_proxy.db
sqlite> EXPLAIN QUERY PLAN 
        SELECT Tag.id, Tag.name, COUNT(ChannelTag.id)
        FROM tags JOIN channel_tags ON Tag.id = ChannelTag.tag_id
        WHERE ChannelTag.account_id = 1
        GROUP BY Tag.id, Tag.name;
```

Look for `USING INDEX` in the output to confirm index usage.
