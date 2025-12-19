# Database Schema Changes

## New Tables

### 1. `tag_rules` - Tag Extraction Rules

Defines patterns for extracting tags from channel/category names.

```sql
CREATE TABLE tag_rules (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- Rule description
    pattern VARCHAR(255) NOT NULL,        -- Pattern to match (e.g., "US|", "ᴿᴬᵂ")
    pattern_type VARCHAR(20) NOT NULL,    -- prefix, suffix, contains, regex
    tag_name VARCHAR(50) NOT NULL,        -- Tag to assign (e.g., "US", "RAW")
    source VARCHAR(20) NOT NULL,          -- channel_name, category_name, both
    remove_from_name BOOLEAN DEFAULT TRUE,-- Remove pattern from channel name
    priority INTEGER DEFAULT 100,         -- Processing order (lower first)
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Example Records:**
| id | name | pattern | pattern_type | tag_name | source | remove_from_name | priority |
|----|------|---------|--------------|----------|--------|------------------|----------|
| 1 | US Prefix | US\| | prefix | US | both | true | 10 |
| 2 | RAW Quality | ᴿᴬᵂ | contains | RAW | both | true | 20 |
| 3 | 60fps | ⁶⁰ᶠᵖˢ | contains | 60FPS | both | true | 20 |

### 2. `tags` - Normalized Tag Names

Stores unique tag names extracted from channels.

```sql
CREATE TABLE tags (
    id INTEGER PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,     -- Normalized tag name (e.g., "US", "RAW")
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Example Records:**
| id | name |
|----|------|
| 1 | US |
| 2 | PRIME |
| 3 | RAW |
| 4 | 60FPS |

### 3. `channel_tags` - Channel-Tag Associations

Many-to-many relationship linking channels to their tags.

```sql
CREATE TABLE channel_tags (
    id INTEGER PRIMARY KEY,
    account_id INTEGER NOT NULL,          -- FK to accounts
    stream_id VARCHAR(50) NOT NULL,       -- Stream ID from IPTV provider
    tag_id INTEGER NOT NULL,              -- FK to tags
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (tag_id) REFERENCES tags(id),
    UNIQUE (account_id, stream_id, tag_id)  -- Prevent duplicates
);
```

**Example Records:**
| id | account_id | stream_id | tag_id |
|----|------------|-----------|--------|
| 1 | 1 | 12345 | 1 |  -- Channel 12345 has tag "US"
| 2 | 1 | 12345 | 2 |  -- Channel 12345 has tag "PRIME"
| 3 | 1 | 12345 | 3 |  -- Channel 12345 has tag "RAW"

### 4. `playlist_configs` - Saved Playlist Configurations

Stores tag-based playlist filter configurations.

```sql
CREATE TABLE playlist_configs (
    id INTEGER PRIMARY KEY,
    name VARCHAR(100) NOT NULL,           -- Playlist name
    description TEXT,                     -- Optional description
    
    -- Account filters (JSON arrays)
    include_accounts TEXT,                -- JSON: [1, 2, 3] or empty
    exclude_accounts TEXT,                -- JSON: [] or [4, 5]
    
    -- Tag filters (JSON arrays)
    include_tags TEXT,                    -- JSON: ["US", "PRIME"]
    exclude_tags TEXT,                    -- JSON: ["RAW"]
    
    -- Match mode
    tag_match_mode VARCHAR(10) DEFAULT 'any',  -- 'any' or 'all'
    
    enabled BOOLEAN DEFAULT TRUE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

**Example Records:**
| id | name | include_tags | exclude_tags | tag_match_mode |
|----|------|--------------|--------------|----------------|
| 1 | US RAW | ["US", "RAW"] | [] | all |
| 2 | US PRIME (No RAW) | ["US", "PRIME"] | ["RAW"] | all |
| 3 | High Quality | ["4K", "60FPS"] | [] | any |

## Existing Tables (Unchanged)

The following tables remain unchanged:

- `accounts` - IPTV service accounts
- `filters` - Legacy account-level filters (still supported)

## Relationships

```
accounts (1) ----< (many) channel_tags
                            |
                            v
                          tags (many) ---- (many) tag_rules (for extraction)

playlist_configs (references accounts via JSON, references tags via JSON)
```

## Migration Notes

1. **No breaking changes** - All existing tables and functionality remain intact
2. **Backward compatible** - Old filter system continues to work
3. **Additive only** - Only new tables are created
4. **Safe to run** - Migration script is idempotent (can run multiple times)

## Query Examples

### Get all tags for a channel
```sql
SELECT t.name 
FROM channel_tags ct
JOIN tags t ON ct.tag_id = t.id
WHERE ct.account_id = 1 AND ct.stream_id = '12345';
```

### Get channels with specific tags
```sql
SELECT DISTINCT ct.stream_id
FROM channel_tags ct
JOIN tags t ON ct.tag_id = t.id
WHERE ct.account_id = 1 
  AND t.name IN ('US', 'PRIME')
GROUP BY ct.stream_id
HAVING COUNT(DISTINCT t.name) = 2;  -- Must have both tags
```

### Get tag counts per account
```sql
SELECT t.name, COUNT(ct.id) as channel_count
FROM tags t
JOIN channel_tags ct ON t.id = ct.tag_id
WHERE ct.account_id = 1
GROUP BY t.id, t.name
ORDER BY t.name;
```

## Performance Considerations

1. **Indexes recommended** (auto-created by SQLAlchemy):
   - `channel_tags(account_id, stream_id)`
   - `channel_tags(tag_id)`
   - `tags(name)` - UNIQUE index

2. **Tag processing** should be done:
   - After adding new accounts
   - After modifying tag rules
   - Periodically if channel lists change frequently

3. **Caching** is maintained:
   - Stream and category data is still cached
   - Tag extraction happens on-demand during processing
   - M3U generation uses processed tags from database

## Data Flow

```
1. User creates tag_rules → Stored in DB

2. User triggers process-tags for account →
   - Fetch channels from IPTV provider (cached)
   - Apply tag_rules to each channel
   - Extract tags and cleaned names
   - Store in channel_tags and tags tables

3. User creates playlist_config → Stored in DB

4. User requests M3U (/playlist/config/1.m3u) →
   - Load playlist_config
   - Fetch channels from configured accounts
   - Apply tag filters from config
   - Generate M3U with cleaned names
   - Return to user
```

## Storage Estimates

Based on typical usage:

- **tag_rules**: ~10-50 rules (KB)
- **tags**: ~20-100 unique tags (KB)
- **channel_tags**: ~10,000 channels × 3 tags avg = 30,000 rows (~1-2 MB)
- **playlist_configs**: ~5-20 configs (KB)

**Total additional storage**: < 5 MB for typical deployment
