# IPTV Proxy v2 - Architecture Overview

> **Document Status**: Generated January 2026  
> **Purpose**: Comprehensive architecture documentation with known issues, duplications, and improvement recommendations.

## Table of Contents

1. [High-Level Architecture](#high-level-architecture)
2. [Core Components](#core-components)
3. [Data Models](#data-models)
4. [API Structure](#api-structure)
5. [Known Issues](#known-issues)
6. [Dead Code & Unused Features](#dead-code--unused-features)
7. [Documentation Discrepancies](#documentation-discrepancies)
8. [Recommendations](#recommendations)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              IPTV Proxy v2                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐│
│  │   Web UI     │     │   REST API   │     │    Playlist/EPG Endpoints    ││
│  │  (Jinja2)    │────▶│  (Flask BP)  │────▶│   /playlist/<id>.m3u         ││
│  │  templates/  │     │   routes/*   │     │   /epg/<id>.xml              ││
│  └──────────────┘     └──────────────┘     └──────────────────────────────┘│
│         │                    │                         │                    │
│         ▼                    ▼                         ▼                    │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         Services Layer                                │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐ │  │
│  │  │ IPTVService │ │ TagService  │ │ EPGService  │ │ CacheService    │ │  │
│  │  │ (Xtream API)│ │ (Extract)   │ │ (XMLTV/SD)  │ │ (In-Memory)     │ │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘ │  │
│  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────────┐ │  │
│  │  │ FilterSvc   │ │ PPVEnrich   │ │ ScheduleSvc │ │ FccFacilitySvc  │ │  │
│  │  │             │ │ (TheSportsDB│ │ (Background)│ │ (Callsign->City)│ │  │
│  │  └─────────────┘ └─────────────┘ └─────────────┘ └─────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                                    ▼                                        │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                       SQLite Database (SQLAlchemy)                    │  │
│  │  accounts, channels, categories, tags, filters, rulesets, epg_*      │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         External Services                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────────┐ │
│  │ Xtream Codes    │  │ Schedules Direct│  │ TheSportsDB (PPV Events)    │ │
│  │ IPTV Providers  │  │ (EPG Data)      │  │ (Free tier limited)         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. Flask Application (`app.py`)

**Status**: ✅ Clean entry point (153 lines)

The application has been successfully refactored from a monolithic ~1300-line file to a clean entry point that:
- Initializes Flask app and extensions
- Registers 20+ blueprints for routes
- Starts the background sync scheduler
- Provides CLI commands (`flask init-db`)

```python
# Registered Blueprints (in order)
web_bp, accounts_bp, filters_bp, rulesets_bp, playlists_bp, api_bp,
streams_bp, epg_sources_bp, epg_channels_bp, account_epg_channels_bp,
epg_match_rules_bp, account_epg_match_rules_bp, schedules_direct_bp,
xmltv_bp, fcc_match_patterns_bp, images_bp, channel_links_bp,
stations_bp, channel_health_bp, ppv_enrichment_bp, settings_bp
```

### 2. Routes Organization (`routes/`)

| Blueprint | File | Purpose |
|-----------|------|---------|
| `web_bp` | `web.py` | HTML page rendering |
| `accounts_bp` | `accounts.py` | Account CRUD, credentials |
| `filters_bp` | `filters.py` | Filter CRUD |
| `rulesets_bp` | `rulesets.py` | Tag extraction rulesets |
| `playlists_bp` | `playlists.py` | M3U generation, playlist configs |
| `api_bp` | `api.py` | Sync, cache, scheduler control |
| `streams_bp` | `streams.py` | Stream proxy, multiplexing |
| `epg_sources_bp` | `epg/sources.py` | EPG source management |
| `epg_channels_bp` | `epg/channels.py` | EPG channel CRUD |
| `epg_match_rules_bp` | `epg/match_rules.py` | EPG matching configuration |
| `schedules_direct_bp` | `epg/schedules_direct.py` | SD API integration |
| `xmltv_bp` | `epg/xmltv.py` | XMLTV grabber management |
| `fcc_match_patterns_bp` | `fcc_match_patterns.py` | FCC database patterns |
| `images_bp` | `images.py` | Icon caching proxy |
| `channel_links_bp` | `channel_links.py` | ⚠️ **UNUSED** - Time-shifted channel links |
| `stations_bp` | `stations.py` | FCC station lookup |
| `channel_health_bp` | `channel_health.py` | Stream health monitoring |
| `ppv_enrichment_bp` | `ppv_enrichment.py` | PPV event enrichment |
| `settings_bp` | `settings.py` | Global app settings |

### 3. Services Layer (`services/`)

| Service | File | Purpose | Status |
|---------|------|---------|--------|
| `IPTVService` | `iptv_service.py` | Xtream Codes API wrapper | ✅ Active |
| `TagService` | `tag_service.py` | Tag extraction from names | ✅ Active |
| `CacheService` | `cache_service.py` | In-memory TTL cache | ✅ Active |
| `FilterService` | `filter_service.py` | Channel filtering logic | ✅ Active |
| `EpgService` | `epg_service.py` | EPG/XMLTV generation | ✅ Active |
| `EpgMatchRulesService` | `epg_match_rules_service.py` | Channel-to-EPG matching | ✅ Active |
| `EpgSyncService` | `epg_sync_service.py` | EPG source synchronization | ✅ Active |
| `SchedulesDirectClient` | `schedules_direct.py` | SD API client | ✅ Active |
| `XmltvGrabberService` | `xmltv_grabber_service.py` | XMLTV grabber management | ✅ Active |
| `SyncScheduler` | `scheduler.py` | Background sync jobs | ✅ Active |
| `FccFacilityService` | `fcc_facility_service.py` | FCC database lookups | ✅ Active |
| `ImageCacheService` | `image_cache_service.py` | Icon proxy cache | ✅ Active |
| `QualityService` | `quality_service.py` | Quality tag ranking | ✅ Active |
| `ChannelHealthService` | `channel_health_service.py` | Stream health checks | ✅ Active |
| `PPVEnrichmentService` | `ppv_enrichment_service.py` | PPV event enrichment | ⚠️ Partial |
| `TheSportsDBService` | `thesportsdb_service.py` | TheSportsDB API | ⚠️ Partial |
| `PPVFilterService` | `ppv_filter_service.py` | PPV visibility filtering | ⚠️ **NOT INTEGRATED** |
| `SdMatchingService` | `sd_matching_service.py` | SD callsign matching | ⚠️ **NOT INTEGRATED** |
| `SyncDateService` | `sync_date_service.py` | PPV date inference | ⚠️ **NOT INTEGRATED** |
| `StreamProxyService` | `stream_proxy_service.py` | Stream proxying | ✅ Active |
| `StreamMultiplexer` | `stream_multiplexer.py` | Multi-credential streams | ✅ Active |
| `ConnectionManager` | `connection_manager.py` | Credential pool management | ✅ Active |
| `FfmpegStreamService` | `ffmpeg_stream_service.py` | Stream analysis | ✅ Active |
| `PPVEventExtractor` | `ppv_event_extractor.py` | Event info extraction | ⚠️ Partial |
| `PPVVisibilityService` | `ppv_visibility_service.py` | PPV visibility logic | ✅ Active |

---

## Data Models

### Core Models (`models.py` - 2033 lines)

```
Account
├── Credential[]              # Multiple credentials per account
├── Filter[]                  # Filtering rules
├── RuleSet[] (via M2M)       # Tag extraction rulesets
├── EpgMatchRuleSet[] (via M2M)  # EPG matching rulesets
└── EpgSource[]               # Provider EPG sources

Channel
├── Category (FK)             # Parent category
├── ChannelTag[] (via M2M)    # Extracted tags
├── ChannelEpgMapping[]       # EPG mappings
├── ChannelLink[]             # Time-shifted variants
├── ChannelHealthStatus       # Health monitoring
└── EventChannelLink[]        # PPV event associations

RuleSet
└── TagRule[]                 # Tag extraction rules

EpgMatchRuleSet
├── EpgMatchRule[]            # EPG matching rules
└── EpgExclusionPattern[]     # Exclusion patterns

EpgSource
├── EpgChannel[]              # Channels in source
├── SdLineup[]                # Schedules Direct lineups
└── SdStation[]               # SD stations
```

### Configuration Models

| Model | Purpose |
|-------|---------|
| `Settings` | Global app settings (proxy_hostname, etc.) |
| `SyncMetadata` | Scheduler state persistence |
| `PlaylistConfig` | Saved playlist filter configurations |
| `ChannelHealthConfig` | Health monitoring settings |

### FCC/EPG Pattern Models

| Model | Purpose |
|-------|---------|
| `FccFacility` | FCC TV station database |
| `FccCorrection` | Manual FCC data corrections |
| `FccMatchNetwork` | Network affiliation patterns |
| `FccMatchChannelPattern` | Channel number extraction |
| `FccMatchLocationPattern` | Location parsing patterns |
| `FccMatchStrategy` | FCC lookup strategies |
| `EpgCountrySuffix` | Country code to EPG suffix mapping |
| `QualityTag` | Quality tag definitions |
| `CountryTag` | Country tag definitions |
| `CallsignSuffix` | Callsign suffix variations |
| `EpgChannelNameMapping` | Legacy name mappings |

---

## API Structure

### Endpoint Count by Category

| Category | Count | Notes |
|----------|-------|-------|
| Accounts | 19 | Full CRUD, sync, credentials |
| Filters | 4 | CRUD operations |
| Rulesets & Tag Rules | 13 | Tag extraction config |
| Playlists | 10 | M3U/EPG generation |
| EPG Sources | 8 | Source CRUD, sync |
| EPG Channels | 7 | Channel management |
| EPG Match Rules | 25 | Complex matching system |
| Schedules Direct | 10 | SD integration |
| FCC Match Patterns | 35 | FCC database patterns |
| Channel Health | 16 | Health monitoring |
| Channel Links | 9 | ⚠️ **UNUSED IN UI** |
| Streams | 9 | Proxy, multiplexing |
| Images | 5 | Icon caching |
| PPV Enrichment | 6 | Event enrichment |
| Settings | 4 | Global settings |
| XMLTV Grabbers | 6 | Grabber management |
| **Total** | **~186** | |

---

## Known Issues

### 1. Dead Code Files

#### `routes/epg.py` - **1336 lines of DEAD CODE**

The file `routes/epg.py` contains a complete EPG routing implementation that is **NOT REGISTERED** in `app.py`. The functionality has been refactored into `routes/epg/*.py` modules.

**Action**: Delete `routes/epg.py` (ensure tests import from `routes/epg/sources.py` instead)

### 2. Duplicate Code

#### `sync_sd_channels_to_epg` Function

Exists in THREE locations with identical implementation:
- `routes/epg.py:29` (dead file)
- `routes/epg/common.py:18` (canonical)
- Used via import aliasing in `routes/epg/sources.py:13`

**Action**: Keep only `routes/epg/common.py` implementation, update test imports

#### `sync_sd_lineup_impl` Function

Duplicated between:
- `routes/epg.py:800` (dead file)
- `routes/epg/common.py:106` (canonical)

### 3. PPV Placeholder Patterns

The same PPV placeholder detection patterns are defined in multiple files:
- `services/ppv_filter_service.py`
- `services/ppv_visibility_service.py`
- `services/ppv_event_extractor.py`

**Action**: Centralize to single module (suggest `services/ppv_constants.py`)

---

## Dead Code & Unused Features

### Unused API Endpoints (Not Called by UI)

#### Channel Links Module - **ENTIRE MODULE UNUSED**
```
/api/channel-links                    GET, POST
/api/channel-links/<id>               GET, PUT, DELETE
/api/channel-links/bulk               POST
/api/channel-links/auto-detected      DELETE
/api/channel-links/detect             POST
/api/channels/<id>/links              GET
```
**Status**: Backend complete, no UI integration. The `ChannelLink` model exists for time-shifted channels but feature is not exposed.

#### EPG Name Mappings - **FEATURE INCOMPLETE**
```
/api/epg-match-rules/name-mappings    GET, POST
/api/epg-match-rules/name-mappings/<id>  GET, PUT, DELETE
/api/epg-match-rules/name-mappings/preview  POST
```
**Status**: API and model (`EpgChannelNameMapping`) exist, no UI.

### Unused Services

| Service | File | Issue |
|---------|------|-------|
| `SdMatchingService` | `sd_matching_service.py` | 385 lines, fully implemented, not imported by any route |
| `PPVFilterService` | `ppv_filter_service.py` | 1019 lines, not integrated into FilterService |
| `SyncDateService` | `sync_date_service.py` | Created for PPV, not wired to routes |

### Unused Models

| Model | Issue |
|-------|-------|
| `EpgChannelNameMapping` | Has API but no UI |
| `ChannelLink` | Has API but no UI |

---

## Documentation Discrepancies

### Missing Implementation

| Documented Feature | Status |
|-------------------|--------|
| `PPVEventFilter` Model | ❌ Not implemented (documented in 6+ files) |
| `/api/ppv-filters/*` Endpoints | ❌ Not implemented |
| Database-driven PPV rules | ❌ Hardcoded in service instead |

### Outdated Documentation

| File | Issue |
|------|-------|
| `.github/copilot-instructions.md` | States `app.py` is "~1300 lines" - actually 153 lines now |
| `.github/copilot-instructions.md` | Lists models that don't include EPG/FCC models |
| `docs/PPV_FILTERING_*.md` | Reference `PPVEventFilter` model that doesn't exist |

### Contradictory Status

| Topic | Conflict |
|-------|----------|
| TheSportsDB Rate Limits | Docs say 500/day, 20/hour, 30/min - actual code uses 25/min |
| PPV Enrichment | Some docs say "Complete ✅", `EPG_GENERATION_STATUS.md` says "NOT GENERATING" |

---

## Recommendations

### High Priority

1. **Delete `routes/epg.py`**
   - 1336 lines of dead code
   - Update test imports to use `routes/epg/sources.py`

2. **Fix copilot-instructions.md**
   - Update architecture description (app.py is 153 lines, not 1300)
   - Add EPG/FCC models to key relationships
   - Update file references

3. **Integrate or Remove `PPVFilterService`**
   - Either wire into `FilterService` or delete
   - 1019 lines of unused code

4. **Integrate or Remove `SdMatchingService`**
   - Either wire into EPG matching or delete
   - 385 lines of unused code

### Medium Priority

5. **Centralize PPV Constants**
   - Create `services/ppv_constants.py`
   - Move placeholder patterns to single location

6. **Complete Channel Links UI**
   - Either add UI for time-shifted channels or remove API
   - Model `ChannelLink` is orphaned

7. **Complete EPG Name Mappings UI**
   - Add to EPG management page or remove API

8. **Update PPV Documentation**
   - Remove references to non-existent `PPVEventFilter` model
   - Mark feature as "hardcoded rules, no DB model"

### Low Priority

9. **Add Status Badges to Docs**
   - ✅ Implemented
   - ⚠️ Partial
   - 🔲 Planned
   - ❌ Deprecated

10. **Consolidate Test Files**
    - Multiple files test same functionality (`test_epg_comprehensive.py`, `test_epg_routes_comprehensive.py`, `test_coverage_boost.py`)

---

## File Counts

| Directory | Files | Lines (approx) |
|-----------|-------|----------------|
| `routes/` | 18 | ~6,500 |
| `routes/epg/` | 7 | ~3,000 |
| `services/` | 28 | ~12,000 |
| `models.py` | 1 | 2,033 |
| `templates/` | 17 | ~3,500 |
| `tests/` | 40+ | ~20,000 |
| `docs/` | 60+ | ~15,000 |

---

## Appendix: Full Route List

<details>
<summary>Click to expand all 186 routes</summary>

```
/                                          GET
/accounts                                  GET
/api/accounts                              GET, POST
/api/accounts/<id>                         PUT, DELETE
/api/accounts/<id>/categories              GET
/api/accounts/<id>/channels/<stream_id>    GET
/api/accounts/<id>/connection-status       GET
/api/accounts/<id>/credentials             GET, POST
/api/accounts/<id>/credentials/<id>        PUT, DELETE
/api/accounts/<id>/credentials/<id>/test   POST
/api/accounts/<id>/epg-match-rulesets      GET, POST
/api/accounts/<id>/epg-match-rulesets/<id> DELETE
/api/accounts/<id>/epg-source              POST
/api/accounts/<id>/filters                 GET
/api/accounts/<id>/ppv-visibility          PUT
/api/accounts/<id>/preview                 GET
/api/accounts/<id>/preview-channels        POST
/api/accounts/<id>/process-tags            POST
/api/accounts/<id>/recompute-visibility    POST
/api/accounts/<id>/rulesets                GET, POST
/api/accounts/<id>/rulesets/<id>           DELETE
/api/accounts/<id>/stats                   GET
/api/accounts/<id>/sync                    POST
/api/accounts/<id>/sync/status             GET
/api/accounts/<id>/tags                    GET
/api/accounts/<id>/tags/search             GET
/api/accounts/<id>/test                    POST
/api/cache/clear                           POST
/api/cache/clear/<id>                      POST
/api/categories                            GET
/api/channel-health/*                      (16 endpoints)
/api/channel-links/*                       (9 endpoints) ⚠️ UNUSED
/api/epg/*                                 (multiple)
/api/epg-match-rules/*                     (25 endpoints)
/api/fcc-match-patterns/*                  (35 endpoints)
/api/fcc/*                                 (8 endpoints)
/api/filters                               GET, POST
/api/filters/<id>                          PUT, DELETE
/api/image-cache/*                         (4 endpoints)
/api/playlist-configs/*                    (5 endpoints)
/api/ppv-enrichment/*                      (6 endpoints)
/api/rulesets/*                            (9 endpoints)
/api/scheduler/*                           (4 endpoints)
/api/settings/*                            (4 endpoints)
/api/sync/all                              POST
/api/tag-rules/*                           (5 endpoints)
/api/tags                                  GET
/api/tags/cleanup-orphans                  POST
/api/xmltv/*                               (6 endpoints)
/categories                                GET
/channel-health                            GET
/configurable-patterns                     GET
/epg                                       GET
/epg/<id>.xml                              GET
/epg/config/<id>.xml                       GET
/epg/config/<slug>.xml                     GET
/fcc-match-patterns                        GET
/filters                                   GET
/icon/<url_hash>                           GET
/icon/fetch                                POST
/player/<id>/<stream_id>                   GET
/playlist/<id>.m3u                         GET
/playlist/config/<id>.m3u                  GET
/playlist/config/<slug>.m3u                GET
/ppv                                       GET
/rulesets                                  GET
/settings                                  GET
/stations                                  GET
/stream/<id>/<stream_id>.m3u8              GET
/stream/<id>/<stream_id>.ts                GET
/stream/<id>/<stream_id>/test              GET
/stream/<id>/status                        GET
/stream/<token>/release                    POST
/stream/active                             GET
/stream/cleanup                            POST
/stream/multiplexer/stats                  GET
/stream/shared                             GET
/test                                      GET
```

</details>

---

## Database Schema Analysis

### Schema Overview

The database uses SQLite with 40+ tables organized into several domains:

| Domain | Tables | Purpose |
|--------|--------|---------|
| **Core** | accounts, credentials, filters | User accounts and authentication |
| **Content** | channels, categories, tags, channel_tags | IPTV channel data |
| **Rules** | rulesets, tag_rules, account_rulesets | Tag extraction |
| **EPG** | epg_sources, epg_channels, channel_epg_mappings | EPG data |
| **EPG Matching** | epg_match_rulesets, epg_match_rules, epg_exclusion_patterns | EPG matching rules |
| **Schedules Direct** | sd_lineups, sd_stations | SD integration |
| **FCC** | fcc_facilities, fcc_corrections, fcc_match_* | FCC database |
| **PPV** | events, event_channel_links | PPV event tracking |
| **Health** | channel_health_checks, channel_health_status | Stream monitoring |
| **Config** | settings, sync_metadata, channel_health_config | App configuration |
| **Cache** | cached_images, active_streams | Runtime state |

### Index Coverage

The database has **57 explicit indexes** plus automatic unique constraint indexes. Generally well-indexed.

#### Well-Indexed Tables ✅
- `channels` - 6 indexes (account_id, name, category_id, is_ppv, thesportsdb_id, enrichment)
- `channel_tags` - 4 indexes (account_id, tag_id, source, composite)
- `fcc_facilities` - 6 indexes (callsign, city/state, network, DMA)
- `events` - 6 indexes (external_id, scheduled_at, teams, league, status)
- `channel_health_checks` - 2 indexes (channel+time composite, result)

#### Missing Indexes ⚠️

| Table | Missing Index | Impact |
|-------|---------------|--------|
| `filters` | `account_id` | Slow filter lookups per account |
| `tag_rules` | `ruleset_id` | Slow rule lookups per ruleset |
| `account_rulesets` | `account_id`, `ruleset_id` individual | Uses composite only |
| `account_epg_match_rulesets` | `account_id`, `ruleset_id` individual | Uses composite only |
| `epg_match_rules` | `ruleset_id` | Slow rule lookups ⚠️ Has index but FK query may not use |
| `channels` | `is_active` | Common filter not indexed |
| `channels` | `is_visible` | Common filter not indexed |
| `channels` | `(account_id, is_active)` composite | Frequently queried together |

---

### Data Duplication Issues

#### 1. **JSON Fields Storing Relationships** (Design Smell)

Several models store arrays as JSON text instead of using proper relational tables:

| Model | JSON Field | Should Be |
|-------|------------|-----------|
| `PlaylistConfig` | `include_accounts` | Separate `playlist_config_accounts` table |
| `PlaylistConfig` | `exclude_accounts` | Separate table |
| `PlaylistConfig` | `include_tags` | Separate `playlist_config_tags` table |
| `PlaylistConfig` | `exclude_tags` | Separate table |
| `EpgMatchRule` | `required_tags` | Separate `epg_rule_tags` table |
| `EpgMatchRule` | `excluded_tags` | Separate table |
| `EpgMatchRule` | `country_codes` | Separate table |
| `EpgMatchRule` | `epg_source_ids` | Separate table |
| `EpgChannel` | `display_names_json` | Separate `epg_channel_names` table |
| `EpgChannel` | `matched_channels_json` | Use `channel_epg_mappings` instead |
| `FccMatchNetwork` | `tag_patterns` | Separate `fcc_network_tags` table |
| `FccMatchChannelPattern` | `networks` | Separate table |
| `EpgCountrySuffix` | `epg_suffixes` | Separate `country_suffix_values` table |

**Impact:**
- Cannot query by array contents efficiently (no SQL `WHERE tag IN (...)`)
- Requires application-level JSON parsing on every access
- No referential integrity for stored IDs
- Difficult to update single elements

#### 2. **Denormalized Counts**

| Table | Field | Issue |
|-------|-------|-------|
| `EpgSource` | `channel_count` | Must be manually kept in sync |
| `SdLineup` | `channel_count` | Must be manually kept in sync |
| `EpgChannel` | `program_count` | Must be manually kept in sync |
| `ChannelHealthStatus` | `total_checks`, `successful_checks`, `failed_checks` | Aggregates of `channel_health_checks` |

**Recommendation:** Use `COUNT()` queries or triggers instead of cached counts that can become stale.

#### 3. **Duplicate Category Information**

The `Channel.category_id` points to `Category.id`, but `Category` also stores `category_id` (the provider's external ID). This creates confusion and potential inconsistency.

```
Channel.category_id → Category.id (internal)
Category.category_id → Provider's external ID (string)
```

**Better approach:** Rename `Category.category_id` to `external_category_id` for clarity.

---

### Application Workarounds

The application code contains several workarounds for database design issues:

#### 1. **Manual JSON Serialization Throughout**

Every route that reads `PlaylistConfig` must do:
```python
"include_accounts": json.loads(c.include_accounts) if c.include_accounts else [],
"exclude_accounts": json.loads(c.exclude_accounts) if c.exclude_accounts else [],
```

**Files affected:** `routes/playlists.py`, `routes/epg/match_rules.py`, `services/epg_match_rules_service.py`

**Fix:** Add `@property` methods to models:
```python
@property
def include_accounts_list(self):
    return json.loads(self.include_accounts) if self.include_accounts else []
```

#### 2. **N+1 Query Patterns**

Found in multiple locations where relationships are accessed in loops without eager loading:

| File | Pattern | Fix |
|------|---------|-----|
| `routes/accounts.py` | `for cred in credentials: ActiveStream.query.filter_by(credential_id=cred.id).count()` | Use `GROUP BY` |
| `routes/rulesets.py` | `len(rs.rules)` in list comprehension | Use `joinedload(RuleSet.rules)` |
| `services/tag_service.py` | Tag lookup per tag name | Use `IN` query |
| `services/connection_manager.py` | Active stream count per credential | Use `GROUP BY` |
| `services/fcc_facility_service.py` | Callsign suffix loop queries | Use `OR` conditions |

#### 3. **Python Filtering Instead of SQL**

```python
# routes/playlists.py - loads all configs then filters in Python
configs = PlaylistConfig.query.all()
for c in configs:
    if slugify(c.name) == slug.lower():  # Should be SQL WHERE
```

#### 4. **Legacy Field Handling**

The `Account` model has legacy `username`/`password` fields alongside the `credentials` relationship:
```python
def get_primary_credential(self):
    if self.credentials:
        return self.credentials[0]
    # Fallback to legacy fields for backward compatibility
    if self.username and self.password:
        return type("LegacyCredential", (), {...})()  # Creates fake object!
```

**This creates a mock object at runtime** - a workaround for incomplete data migration.

---

### Performance Issues

#### 1. **Missing Composite Indexes for Common Queries**

| Query Pattern | Tables | Current | Recommended |
|---------------|--------|---------|-------------|
| Channels by account + active | channels | Separate indexes | `(account_id, is_active)` |
| Channels by account + visible | channels | Separate indexes | `(account_id, is_visible)` |
| Tags by account + source | channel_tags | Has `(account_id, tag_id)` | Add `(account_id, source)` |
| Health checks by channel + time | channel_health_checks | Has composite ✅ | Good |

#### 2. **Large Text Fields Without Length Limits**

| Table | Field | Issue |
|-------|-------|-------|
| `Channel` | `stream_icon` | VARCHAR(500) may truncate URLs |
| `Channel` | `direct_source` | VARCHAR(500) may truncate URLs |
| `CachedImage` | `original_url` | VARCHAR(2000) - good |
| `FccFacility` | `nielsen_dma` | VARCHAR(100) - DMA names can be long |

#### 3. **No Soft Delete Pattern**

Channels use `is_active` flag but:
- No index on `is_active` alone
- Queries must always filter by `is_active=True`
- Stale data accumulates

**Recommendation:** Either add index or implement periodic cleanup.

#### 4. **Channel Health Check Growth**

`channel_health_checks` stores every health check forever. With 10,000 channels and checks every 30 minutes:
- 10,000 × 48 checks/day = 480,000 rows/day
- 14.4 million rows/month

**Recommendation:** Implement retention policy (keep last N days, aggregate older data).

---

### Key-Value Tables Pattern

Three tables use the key-value pattern: `settings`, `sync_metadata`, `channel_health_config`

**Issues:**
- No type safety (all values are TEXT)
- No schema validation
- Difficult to query multiple settings efficiently

**These tables duplicate each other's pattern** - could be consolidated into single `app_config` table with `category` column.

---

### Foreign Key Cascade Issues

#### Missing ON DELETE CASCADE

| Table | FK Field | Issue |
|-------|----------|-------|
| `filters` | `account_id` | No cascade - orphans on account delete |
| `tag_rules` | `ruleset_id` | No cascade - orphans on ruleset delete |
| `active_streams` | `credential_id` | No cascade - orphans on credential delete |

The SQLAlchemy models define `cascade="all, delete-orphan"` but the **database constraints** may not have been created with `ON DELETE CASCADE`, causing inconsistency between ORM and raw SQL operations.

---

### Recommendations Summary

#### High Priority (Performance)

1. **Add missing indexes:**
   ```sql
   CREATE INDEX idx_filters_account ON filters(account_id);
   CREATE INDEX idx_tag_rules_ruleset ON tag_rules(ruleset_id);
   CREATE INDEX idx_channels_account_active ON channels(account_id, is_active);
   CREATE INDEX idx_channels_account_visible ON channels(account_id, is_visible);
   ```

2. **Fix N+1 queries** in routes/accounts.py, services/tag_service.py

3. **Add computed properties** to models for JSON fields

#### Medium Priority (Design)

4. **Normalize JSON arrays** to proper tables (PlaylistConfig tags/accounts first)

5. **Add retention policy** for channel_health_checks

6. **Complete Account migration** - remove legacy username/password fields

#### Low Priority (Cleanup)

7. **Consolidate key-value tables** (settings, sync_metadata, channel_health_config)

8. **Rename ambiguous fields** (Category.category_id → external_category_id)

9. **Add ON DELETE CASCADE** to all FK constraints in database
