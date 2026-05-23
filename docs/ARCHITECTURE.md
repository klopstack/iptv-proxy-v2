# IPTV Proxy v2 - Architecture Guide

## Overview

IPTV Proxy v2 is a Flask-based IPTV proxy that sits between Xtream Codes API services and clients, providing advanced filtering, tag extraction, EPG management, and channel health monitoring.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IPTV Proxy v2                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐      ┌──────────────────────────────┐│
│  │   Web UI     │     │   REST API   │      │    Playlist/EPG Endpoints    ││
│  │  (Jinja2)    │───▶│  (Flask BP)  │────▶│   /playlist/<id>.m3u         ││
│  │  templates/  │     │   routes/*   │      │   /epg/<id>.xml              ││
│  └──────────────┘     └──────────────┘      │   /xtream-api/*              ││
│         │                    │              └──────────────────────────────┘│
│         │                    │                         │                    │
│         ▼                    ▼                         ▼                    │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                         Services Layer                               │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐ │   │
│  │  │ IPTVService │ │ TagService  │ │ EPGService  │ │ CacheService    │ │   │
│  │  │ (Xtream API)│ │ (Extract)   │ │ (XMLTV/SD)  │ │ (In-Memory)     │ │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘ │   │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐ │   │
│  │  │ FilterSvc   │ │ PPVEnrich   │ │ ScheduleSvc │ │ FccFacilitySvc  │ │   │
│  │  │             │ │ +Calendar   │ │ (Background)│ │ (Callsign->City)│ │   │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │                       Data Layer (SQLite)                           │   │
│  │  Account → Filters, Rulesets, EPG Sources, Channels                 │   │
│  │  Channel → Tags, EPG Mappings, Health Status                        │   │
│  │  Event → PPV Events from TheSportsDB                                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Core Components

### Entry Point
- **`app.py`**: Clean entry point (177 lines) with blueprint registration and scheduler setup

### Routes Layer
- **`routes/`**: Flask blueprints organized by feature (17 blueprints)
  - `routes/web.py` - HTML page rendering
  - `routes/accounts.py` - Account CRUD and credentials
  - `routes/epg/` - EPG management (sources, channels, match_rules, etc.)
  - `routes/xtream.py` - Xtream Codes API compatibility (TiviMate, IPTV Smarters)

### Business Logic
- **`services/`**: Business logic services (29 files, ~18,500 lines)
  - `IPTVService` - Xtream Codes API integration
  - `TagService` - Tag extraction and rule processing
  - `EPGService` - EPG data management and XMLTV generation
  - `services/ppv/` - PPV enrichment, visibility, and event-based EPG
  - `CacheService` - Simple in-memory caching (3600s TTL)
  - `FilterService` - Channel filtering logic

### Data Layer
- **`models/`**: SQLAlchemy models split by domain (`__init__.py` re-exports all 44 models; `_core.py` is a deprecated shim)
  - `_base.py` — `db` instance
  - `account.py` — Account, Credential, XtreamCredential, PlaylistConfig, ActiveStream
  - `channel.py` — Channel, Category, tags, filters, rulesets
  - `epg.py` / `epg_match.py` — EPG sources, programs, mappings, matching rules
  - `ppv.py` — Event, EventChannelLink, SportsTeam
  - `fcc.py` — FCC facility data and match patterns
  - `sync.py` — SyncMetadata, Settings
  - `health.py` — Channel health monitoring
- **`migrations/`**: Database schema evolution scripts

## Data Flow

1. **Account Setup**: Users add IPTV accounts and configure filters via web UI
2. **Channel Sync**: Background scheduler syncs channels from Xtream Codes API
3. **Tag Extraction**: Tag extraction rules parse channel/category names (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ")
4. **EPG Mapping**: EPG match rules map channels to EPG data sources (Schedules Direct, XMLTV)
5. **EPG Sync**: Background scheduler syncs program data from external sources to `EpgProgram` database
6. **Playlist Generation**: Filtered playlists served at `/playlist/<id>.m3u` and EPG at `/epg/<id>.xml` (generated from database)

## Key Model Relationships

### Account-Centric
- `Account` → many `Filter`, `Credential`, `EpgSource` (cascade delete)
- `Account` ↔ many `RuleSet` through `AccountRuleSet` (priority-ordered)
- `Account` ↔ many `EpgMatchRuleSet` through `AccountEpgMatchRuleSet`

### Channel Data
- `Channel` → `Category`, many `ChannelTag`, `ChannelEpgMapping`, `ChannelHealthStatus`
- `Tag` ↔ many channels via `ChannelTag` (composite key: account_id + stream_id + tag_id)
- `RuleSet` → many `TagRule` (cascade delete, sorted by priority)

### EPG Integration
- `EpgSource` → many `EpgChannel`, `SdLineup` → many `SdStation`
- `EpgMatchRuleSet` → many `EpgMatchRule` (cascade delete, sorted by priority)

### PPV Events
- `Event` ↔ many channels via `EventChannelLink` (PPV event tracking from TheSportsDB)

## Tag Extraction System

The tag system parses messy channel names to extract metadata:

**Pattern Types**: `prefix`, `suffix`, `contains`, `regex` (case-insensitive by default)

**Special Behaviors**:
- `__LOCATION__`: Extracts `[bracketed]` content as location tag
- `__CALLSIGN__`: Extracts `(parenthesized)` content as callsign tag  
- `__CLEANUP__`: Removes pattern without creating a tag

**Example**:
```python
# "US| PRIME: SHADES OF BLACK ᴿᴬᵂ" + category "US| PRIME ⁶⁰ᶠᵖˢ"
# → tags: {'US', 'PRIME', 'RAW', '60FPS'}, clean name: "SHADES OF BLACK"
```

## Performance Considerations

⚠️ **Critical**: With 10,000+ channels, loading all tags at once causes OOM kills.

**Best Practices**:
1. **Lazy loading**: Only load tags for channels that need them
2. **Batching**: Query tags in batches of 500-1000 stream IDs
3. **Filtering first**: Apply non-tag filters before loading tags
4. **Pagination**: Never load all channels into memory

**Good Pattern**:
```python
# DO THIS - only load tags for specific streams in batches
batch_size = 500
for i in range(0, len(stream_ids), batch_size):
    batch = stream_ids[i:i + batch_size]
    tags = db.session.query(ChannelTag.stream_id, Tag.name).join(Tag).filter(
        ChannelTag.account_id == account_id,
        ChannelTag.stream_id.in_(batch)
    ).all()
```

## External Integrations

### Xtream Codes API
Core dependency. `IPTVService` wraps HTTP calls to `player_api.php`:
- `authenticate()` - validate credentials
- `get_live_streams(category_id=None)` - fetch channels
- `get_live_categories()` - fetch categories
- `get_xmltv()` - fetch EPG XML

### Schedules Direct
Premium EPG source. `SchedulesDirectClient` provides:
- `authenticate()` - get session token
- `get_lineups()` - list subscribed lineups
- `get_lineup_channels()` - channels in lineup
- `get_schedules()` / `get_programs()` - program data

### TheSportsDB
PPV event enrichment (free tier has rate limits). Used by `PPVEnrichmentService`.

### FCC Database
`FccFacilityService` lookups for callsign → city/market mapping.

## EPG Generation Architecture

### Database-First Approach
EPG generation in v2 uses a **database-first architecture** - all EPG program data is synced to the `EpgProgram` table before being served to clients. This provides:
- **Better performance**: No external API calls during playlist/EPG generation
- **Consistency**: All clients see the same EPG data
- **Reliability**: EPG works even if external sources are temporarily unavailable
- **Simplicity**: Single code path for all EPG generation

### EPG Data Sync
Background scheduler (`services/scheduler.py`) syncs EPG data:

**XMLTV Sources:**
- Parsed by `services/epg_sync_service.py`
- Programs extracted and stored in `EpgProgram` table
- Supports gzip-compressed XMLTV files

**Schedules Direct:**
- Synced by `services/epg/sd_programs.py`
- Fetches schedules for all stations in lineup
- Fetches detailed program metadata (title, description, episode info, ratings)
- Updates existing programs, adds new ones, deletes old ones

**Provider EPG (Legacy):**
- Direct passthrough from IPTV provider (deprecated)
- Recommendation: Use EPG mappings to Schedules Direct or XMLTV sources instead

### EPG Generation Flow

```
Client Request
      ↓
generate_epg_for_channels()
      ↓
  ┌───────────────────────────────────────┐
  │ 1. Query EpgProgram via Mappings     │
  │    - Join ChannelEpgMapping           │
  │    - Filter by time range (now ± 7d)  │
  │    - Apply time_offset_hours          │
  └───────────────────────────────────────┘
      ↓
  ┌───────────────────────────────────────┐
  │ 2. Handle ChannelLink Inheritance     │
  │    - Find source channel's programs   │
  │    - Copy with time offset applied    │
  └───────────────────────────────────────┘
      ↓
  ┌───────────────────────────────────────┐
  │ 3. Generate Synthetic Channels        │
  │    - Create <channel> elements        │
  │    - No <programme> elements          │
  └───────────────────────────────────────┘
      ↓
  XMLTV XML Response
```

**Key Points:**
- **No external API calls** during generation
- **Single database query** per EPG source (batch loading)
- **Time offsets** applied at generation time (not stored in DB)
- **Synthetic channels** for unmapped channels (valid XMLTV without programs)

### EPG Database Models

```python
EpgProgram:
  - epg_channel_id (FK to EpgChannel)
  - start_time, stop_time (naive UTC)
  - title, description
  - season_number, episode_number
  - categories (JSON array)
  - rating (JSON object)
  - external_id (program ID from source)

EpgChannel:
  - source_id (FK to EpgSource)
  - channel_id (unique per source)
  - display_name, icon_url
  - Programs synced from external sources

ChannelEpgMapping:
  - channel_id (FK to Channel)
  - epg_channel_id (FK to EpgChannel)
  - time_offset_hours (timezone adjustment)
  - mapping_type, confidence
```

## JSON Field Handling

⚠️ **Important**: Several models store arrays as JSON text fields.

**Current pattern**: Always use `json.loads()` when reading and `json.dumps()` when writing:
- `PlaylistConfig`: include_accounts, exclude_accounts, include_tags, exclude_tags
- `EpgMatchRule`: required_tags, excluded_tags, country_codes, epg_source_ids
- `EpgChannel`: display_names_json, matched_channels_json

**Future**: Converting to native SQLAlchemy JSON type will eliminate all json.loads()/json.dumps() calls.

## Deployment

### Docker (Recommended)
```bash
docker-compose up -d  # Port 8889 → 8000
```

### Local Development
```bash
export DATABASE_URL="sqlite:////app/data/iptv_proxy.db"
export SECRET_KEY="dev-key"
python app.py  # Runs on port 8000
```

## Testing Architecture

- `pytest` with in-memory SQLite (`sqlite:///:memory:`)
- 75% minimum code coverage enforced
- Test organization:
  - `tests/test_app.py` - API endpoints and filter logic
  - `tests/test_tag_service.py` - Tag extraction and ruleset logic
  - `tests/test_rulesets_api.py` - Ruleset/tag rule CRUD operations
