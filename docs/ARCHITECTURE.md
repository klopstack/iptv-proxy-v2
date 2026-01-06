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
  - `routes/xtream_api.py` - Xtream Codes API compatibility

### Business Logic
- **`services/`**: Business logic services (29 files, ~18,500 lines)
  - `IPTVService` - Xtream Codes API integration
  - `TagService` - Tag extraction and rule processing
  - `EPGService` - EPG data management and XMLTV generation
  - `PPVEnrichmentService` - TheSportsDB integration for events
  - `CacheService` - Simple in-memory caching (3600s TTL)
  - `FilterService` - Channel filtering logic

### Data Layer
- **`models.py`**: SQLAlchemy models (2,063 lines, 41 models)
- **`migrations/`**: Database schema evolution scripts

## Data Flow

1. **Account Setup**: Users add IPTV accounts and configure filters via web UI
2. **Channel Sync**: Background scheduler syncs channels from Xtream Codes API
3. **Tag Extraction**: Tag extraction rules parse channel/category names (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ")
4. **EPG Mapping**: EPG match rules map channels to EPG data (provider, Schedules Direct, XMLTV)
5. **Playlist Generation**: Filtered playlists served at `/playlist/<id>.m3u` and EPG at `/epg/<id>.xml`

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
