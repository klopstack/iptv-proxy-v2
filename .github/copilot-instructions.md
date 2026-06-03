# IPTV Proxy v2 - AI Coding Agent Instructions

⚠️ **Note:** This is an actively evolving project. Patterns and architecture may change as requirements become clearer. Use these instructions as a current snapshot, not rigid rules.

## Quick Reference

## Architecture Overview

Flask-based IPTV proxy that sits between Xtream Codes API services and clients, adding tag extraction, advanced filtering, EPG management, and channel health monitoring.

**Current Structure:**
- `app.py`: Clean entry point (177 lines) with blueprint registration and scheduler setup
- `routes/`: Flask blueprints organized by feature (17 blueprints)
- `routes/epg/`: Decomposed EPG routes (sources, channels, match_rules, schedules_direct, xmltv)
- `models/`: SQLAlchemy models package (`__init__.py` re-exports from `_core.py`)
- `services/`: Business logic services (29 files, ~18,500 lines covering IPTV, caching, EPG, PPV, etc.)
- `templates/`: Web UI built with Jinja2 templates

**Data Flow:**
1. Users add IPTV accounts and configure filters via web UI
2. Background scheduler syncs channels from Xtream Codes API
3. Tag extraction rules parse channel/category names (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ")
4. EPG match rules map channels to EPG data sources (Schedules Direct, XMLTV)
5. Background scheduler syncs EPG program data from external sources to EpgProgram database
6. Filtered playlists served at `/playlist/<id>.m3u` and EPG at `/epg/<id>.xml` (generated from database)

**Key Model Relationships:**
- `Account` → many `Filter`, `Credential`, `EpgSource` (cascade delete)
- `Account` ↔ many `RuleSet` through `AccountRuleSet` (priority-ordered)
- `Account` ↔ many `EpgMatchRuleSet` through `AccountEpgMatchRuleSet`
- `RuleSet` → many `TagRule` (cascade delete, sorted by priority)
- `EpgMatchRuleSet` → many `EpgMatchRule` (cascade delete, sorted by priority)
- `Channel` → `Category`, many `ChannelTag`, `ChannelEpgMapping`, `ChannelHealthStatus`, `EventChannelLink`
- `EpgSource` → many `EpgChannel`, `SdLineup` → many `SdStation`
- `Tag` ↔ many channels via `ChannelTag` (composite key: account_id + stream_id + tag_id)
- `Event` ↔ many channels via `EventChannelLink` (PPV event tracking from TheSportsDB)

**⚠️ IMPORTANT - JSON Field Handling:** Several models store arrays as JSON text fields.
- **Current pattern**: Always use `json.loads()` when reading and `json.dumps()` when writing:
  - `PlaylistConfig`: include_accounts, exclude_accounts, include_tags, exclude_tags
  - `EpgMatchRule`: required_tags, excluded_tags, country_codes, epg_source_ids
  - `EpgChannel`: display_names_json, matched_channels_json
- **Future**: Converting to native SQLAlchemy JSON type will eliminate all json.loads()/json.dumps() calls

## EPG Generation Architecture

EPG generation is now **database-first** - all EPG data is synced to the `EpgProgram` table before generation.

**EPG Data Sync (Background Scheduler):**
- XMLTV sources: Parsed and synced by `services/epg_sync_service.py`
- Schedules Direct: Synced by `services/epg/sd_programs.py` (fetches schedules + program details)
- Provider EPG: Legacy - not recommended, use mapped sources instead

**EPG Generation Flow:**
1. `generate_epg_for_channels()` queries `EpgProgram` records via `ChannelEpgMapping`
2. For channels with `ChannelLink`, inherits programs from linked source channel
3. Synthetic channel elements created for unmapped channels (no programmes)
4. **No external API calls during generation** - all data comes from database

**Key Functions:**
- `services/epg/programs.py:generate_xmltv_from_database()` - Core DB-to-XMLTV conversion
- `services/epg/generation.py:generate_epg_for_channels()` - Main entry point (database-only)
- `services/epg/sd_programs.py:sync_sd_programs_for_source()` - SD data sync

## Tag Extraction System (Core Feature)

The tag system parses messy channel names to extract metadata. Currently supports:

**Pattern Types:** `prefix`, `suffix`, `contains`, `regex` (case-insensitive by default)

**Special Tag Behaviors:**
- `__LOCATION__`: Extracts `[bracketed]` content as location tag
- `__CALLSIGN__`: Extracts `(parenthesized)` content as callsign tag  
- `__CLEANUP__`: Removes pattern without creating a tag

**Processing:** Rules run in priority order (lower numbers first). Can search in `channel_name`, `category_name`, or `both`. The `remove_from_name` flag controls whether matched text is stripped from the channel name.

**Real example from codebase:**
```python
# "US| PRIME: SHADES OF BLACK ᴿᴬᵂ" + category "US| PRIME ⁶⁰ᶠᵖˢ"
# → tags: {'US', 'PRIME', 'RAW', '60FPS'}, clean name: "SHADES OF BLACK"
```

Implementation: `services/tag_service.py:extract_tags()`. Test suite: `test_tags.py`.

## Performance Considerations (Critical!)

**Memory Management:** With 10,000+ channels, loading all tags at once causes OOM kills. Always use:
1. **Lazy loading**: Only load tags for channels that need them
2. **Batching**: Query tags in batches of 500-1000 stream IDs
3. **Filtering first**: Apply non-tag filters before loading tags
4. **Pagination**: Never load all channels into memory

**Bad Pattern (causes OOM):**
```python
# DON'T DO THIS - loads all tags for entire account
channel_tags = db.session.query(ChannelTag, Tag).join(Tag).filter(
    ChannelTag.account_id == account_id
).all()
```

**Good Pattern:**
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

See `app.py:preview_playlist()` and `app.py:generate_playlist()` for reference implementations.

## Current Patterns (Subject to Change)

**Caching:** Simple in-memory cache with 3600s TTL in `CacheService`. Cache cleared on account updates via `cache_service.clear_account_cache(account_id)`. May evolve to Redis or more sophisticated invalidation.

**Filtering:** Currently in `_apply_filters()` helper (~line 1300). Supports category/channel_name whitelists/blacklists and regex patterns. Filter architecture may be refactored as complexity grows.

**Playlist Generation:** 
- `/playlist/<account_id>.m3u` - per-account with filters applied
- `/playlist/config/<config_id>.m3u` - tag-based cross-account playlists
- `/epg/<account_id>.xml` - EPG data passthrough
- Tag-based: `/playlist/config/<config_id>.m3u` (applies tag/account rules from PlaylistConfig)

## Development Workflows

**Database Initialization:**
```bash
python app.py  # Auto-creates tables on startup
# Or: flask init-db
```

**Creating Migrations:**
Migrations live in `migrations/` and are named with a date prefix (e.g., `2024_19_add_tag_rule_replacement.py`). Each migration must have a `migrate(db_path)` function that receives the database path as a string and returns `(success: bool, message: str)`:

```python
"""Description of what this migration does"""
import logging
import sqlite3

logger = logging.getLogger(__name__)

def migrate(db_path):
    """Add/modify database schema"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Check if change already applied (idempotent)
        cursor.execute("PRAGMA table_info(table_name)")
        columns = [row[1] for row in cursor.fetchall()]
        
        if "new_column" not in columns:
            cursor.execute("ALTER TABLE table_name ADD COLUMN new_column VARCHAR(255)")
            conn.commit()
            return True, "Added new_column"
        else:
            return True, "new_column already exists, skipping"
    finally:
        conn.close()
```

**Migration Guidelines:**
- Always make migrations idempotent (safe to run multiple times)
- Check if changes exist before applying
- Use raw sqlite3, not SQLAlchemy (migrations receive db_path string)
- Return `(True, "message")` for success, `(False, "error")` for failure
- Run migrations with: `python run_migrations.py`
- In Docker: `docker exec -it iptv-proxy-v2 python run_migrations.py`

**Testing:**
```bash
pip install -r requirements-dev.txt
pytest tests/ -v  # Run all tests
pytest tests/test_tag_service.py -v  # Run specific test file
make test  # Run with coverage (requires 75% minimum)
make test-fast  # Run without coverage checks
```

**Linting and Formatting:**
```bash
make lint  # Check code quality
make format  # Auto-format with black and isort
flake8 .  # Check style issues
black --check .  # Check formatting
mypy app.py models/ services/  # Type checking
```

**Test Organization:**
- `tests/test_app.py` - API endpoints and filter logic
- `tests/test_tag_service.py` - Tag extraction and ruleset logic
- `tests/test_rulesets_api.py` - Ruleset/tag rule CRUD operations
- `test_tags.py` - Standalone tag extraction validation (uses mock objects)

**Coverage Requirements:**
- Minimum 75% code coverage enforced in CI
- Run `make test` to generate HTML coverage report in `htmlcov/`

**Running Locally:**
```bash
export DATABASE_URL="sqlite:////app/data/iptv_proxy.db"
python app.py  # Runs on port 8000 by default
# Or: make run
```

**Docker:**
```bash
docker-compose up -d  # Port 8889 → 8000
make docker-build  # Build image
make docker-logs  # View logs
docker exec -it iptv-proxy-v2 pytest tests/  # Run tests in container
```

## Project Conventions

**Error Handling:** Uses `db.session.get(Model, id)` or `Model.query.get_or_404(id)` patterns. Errors logged with `logger.error()`, API returns JSON with status codes. The `@handle_errors` decorator provides consistent error responses.

**Route Organization:** Routes organized into blueprints in `routes/` directory:
- `routes/web.py` - HTML page rendering
- `routes/accounts.py` - Account CRUD and credentials
- `routes/epg/` - EPG management (decomposed into sources, channels, match_rules, etc.)

**Database:** Models use `updated_at` with `onupdate=datetime.now(timezone.utc).replace(tzinfo=None)`. Changes committed with `db.session.commit()`. SQLite configured with 30s timeout for background scheduler compatibility.

**Testing:** pytest with in-memory SQLite (`sqlite:///:memory:`). Fixtures defined in `tests/conftest.py` and individual test files. Run `make test` for coverage-enforced tests (75% minimum).
## Integration Points

**Xtream Codes API:** Core dependency. `IPTVService` wraps HTTP calls to `player_api.php`:
- `authenticate()` - validate credentials
- `get_live_streams(category_id=None)` - fetch channels
- `get_live_categories()` - fetch categories
- `get_xmltv()` - fetch EPG XML

**Schedules Direct:** Premium EPG source. `SchedulesDirectClient` provides:
- `authenticate()` - get session token
- `get_lineups()` - list subscribed lineups
- `get_lineup_channels()` - channels in lineup
- `get_schedules()` / `get_programs()` - program data
- Data synced to `EpgProgram` database by `services/epg/sd_programs.py`

**TheSportsDB:** PPV event enrichment (free tier has rate limits). Used by `PPVEnrichmentService`.

**FCC Database:** `FccFacilityService` lookups for callsign → city/market mapping.

**Dependencies:** Minimal by design. `requests` for HTTP, `Flask-SQLAlchemy` for ORM, `Flask-CORS` for API access. No message queues, job processors, or complex middleware.

## Common Pitfalls

**JSON field handling:** `PlaylistConfig` stores arrays as JSON text. Must use `json.dumps()`/`json.loads()` when reading/writing. This pattern exists elsewhere - watch for it.

**Cache invalidation:** Currently manual. After account changes, call `cache_service.clear_account_cache(account_id)` or stale data persists.

**Tag rule priority:** Counter-intuitive - LOWER numbers run FIRST (10 before 20). Critical for proper tag extraction order.

**Database location:** Docker path is `/app/data/iptv_proxy.db`, local dev varies. Check `DATABASE_URL` environment variable.

**RuleSet behavior:** If account has no assigned rulesets, falls back to rulesets with `is_default=True`.

**Regex in patterns:** When creating tag rules with regex, use raw strings in code (`r'\b4K\b'`) but stored as normal strings in DB.

## Quality Assurance (Required!)

**ALWAYS run these commands after making code changes:**

```bash
make lint    # Check code quality and formatting (black, flake8, isort, mypy)
make test    # Run full test suite with 75% coverage requirement
```

Both commands must pass before considering your changes complete. These checks are enforced in CI and will prevent merges if they fail.

**Quick Reference:**
- `make format` - Auto-fix formatting issues before running `make lint`
- `make test-fast` - Run tests without coverage checks (for rapid iteration)
- Check `htmlcov/index.html` after `make test` to see detailed coverage report

## Contributing to This Project

Since patterns are still emerging, feel free to propose refactorings or architectural changes. When making significant changes, consider:
- Is this solving a real problem or premature optimization?
- Will this scale if the codebase grows?
- Are there tests to prevent regressions?
- Does it maintain backward compatibility with existing data?
- **Have you run `make lint` and `make test`?** (Required!)
