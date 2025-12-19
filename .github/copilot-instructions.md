# IPTV Proxy v2 - AI Coding Agent Instructions

⚠️ **Note:** This is an actively evolving project. Patterns and architecture may change as requirements become clearer. Use these instructions as a current snapshot, not rigid rules.

## Architecture Overview

Flask-based IPTV proxy that sits between Xtream Codes API services and clients, adding tag extraction and advanced filtering capabilities.

**Current Structure:**
- `app.py`: ~1300 line monolithic Flask app containing routes and business logic
- `models.py`: SQLAlchemy models (Account, Filter, TagRule, RuleSet, Tag, ChannelTag, PlaylistConfig)
- `services/`: Separate concerns for IPTV API calls, caching, and tag extraction
- `templates/`: Web UI built with Jinja2 templates

**Data Flow (as currently implemented):**
1. Users add IPTV accounts and configure filters via web UI
2. App fetches channels from Xtream Codes API endpoints
3. Tag extraction rules parse channel/category names (e.g., "US|", "ᴿᴬᵂ", "⁶⁰ᶠᵖˢ") 
4. Filtered playlists are generated at `/playlist/<id>.m3u` and `/epg/<id>.xml`
 (Current State)

**Key Relationships:**
- `Account` → many `Filter` (cascade delete)
- `RuleSet` ↔ many `Account` through `AccountRuleSet` (priority-ordered)
- `RuleSet` → many `TagRule` (cascade delete, sorted by priority)
- `Tag` ↔ many channels via `ChannelTag` (composite key: account_id + stream_id + tag_id)

**JSON Storage:** `PlaylistConfig` uses text fields for arrays (serialized with `json.dumps()`/`json.loads()`). Watch for this pattern elsewhere - it may evolve to proper JSON columns or separate tables
**JSON storage pattern:** `PlaylistConfig` stores arrays as JSON text fields (`include_accounts`, `exclude_accounts`, `include_tags`, `exclude_tags`). Always use `json.loads()` when reading and `json.dumps()` when writing.

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
Current Patterns (Subject to Change)

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

**Testing:**
```bash
pip install -r requirements-dev.txt
pytest tests/ -v  # Run all tests
pytest tests/test_tag_service.py -v  # Run specific test file
make test  # Run with coverage (requires 70% minimum)
make test-fast  # Run without coverage checks
```

**Linting and Formatting:**
```bash
make lint  # Check code quality
make format  # Auto-format with black and isort
flake8 .  # Check style issues
black --check .  # Check formatting
mypy app.py models.py services/  # Type checking
```

**Test Organization:**
- `tests/test_app.py` - API endpoints and filter logic
- `tests/test_tag_service.py` - Tag extraction and ruleset logic
- `tests/test_rulesets_api.py` - Ruleset/tag rule CRUD operations
- `test_tags.py` - Standalone tag extraction validation (uses mock objects)

**Coverage Requirements:**
- Minimum 70% code coverage enforced in CI
- Run `make test` to generate HTML coverage report in `htmlcov/`

**Running Locally:**
```bash
export DATABASE_URL="sqlite:////app/data/iptv_proxy.db"
export SECRET_KEY="dev-key"
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
Observed Patterns (may evolve)

**Error Handling:** Currently uses `Account.query.get_or_404(id)` pattern. Errors logged with `logger.error()`, API returns JSON with status codes.

**Route Organization:** In `app.py`, routes grouped by comment blocks (`# Web UI Routes`, `# API Routes - Accounts`, etc.). This monolithic structure may be split into blueprints as the app grows.

**Database:** Models use `updated_at` with `onupdate=datetime.utcnow`. Changes committed immediately with `db.session.commit()`. May need transaction management for complex operations.

**Testing:** pytest with in-memory SQLite (`sqlite:///:memory:`). Fixtures in `tests/test_app.py`. Standalone tag tests in `test_tags.py` using mock objects
## Integration Points
External Integration

**Xtream Codes API:** Core dependency. `IPTVService` wraps HTTP calls to `player_api.php`:
- `authenticate()` - validate credentials
- `get_live_streams(category_id=None)` - fetch channels
- `get_live_categories()` - fetch categories
- `get_xmltv()` - fetch EPG XML

**Dependencies:** Minimal by design. `requests` for HTTP, `Flask-SQLAlchemy` for ORM, `Flask-CORS` for API access. No message queues, job processors, or complex middleware ye
## Common Pitfalls
Things to Know

**JSON field handling:** `PlaylistConfig` stores arrays as JSON text. Must use `json.dumps()`/`json.loads()` when reading/writing. This pattern exists elsewhere - watch for it.

**Cache invalidation:** Currently manual. After account changes, call `cache_service.clear_account_cache(account_id)` or stale data persists.

**Tag rule priority:** Counter-intuitive - LOWER numbers run FIRST (10 before 20). Critical for proper tag extraction order.

**Database location:** Docker path is `/app/data/iptv_proxy.db`, local dev varies. Check `DATABASE_URL` environment variable.

**RuleSet behavior:** If account has no assigned rulesets, falls back to rulesets with `is_default=True`.

**Regex in patterns:** When creating tag rules with regex, use raw strings in code (`r'\b4K\b'`) but stored as normal strings in DB.

## Contributing to This Project

Since patterns are still emerging, feel free to propose refactorings or architectural changes. When making significant changes, consider:
- Is this solving a real problem or premature optimization?
- Will this scale if the codebase grows?
- Are there tests to prevent regressions?
- Does it maintain backward compatibility with existing data?
