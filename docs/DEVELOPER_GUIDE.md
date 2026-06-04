# Developer Guide

This guide provides everything you need to develop, test, and contribute to IPTV Proxy v2.

## Table of Contents

1. [Development Setup](#development-setup)
2. [Testing](#testing)
3. [Code Quality](#code-quality)
4. [Database Migrations](#database-migrations)
5. [Development Workflows](#development-workflows)
6. [Contributing Guidelines](#contributing-guidelines)
7. [Performance Guidelines](#performance-guidelines)
8. [Common Patterns](#common-patterns)

## Development Setup

### Prerequisites
- Python 3.11 (matches CI and pre-commit)
- SQLite 3
- Docker (optional)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/klopstack/iptv-proxy-v2.git
cd iptv-proxy-v2

# Create virtual environment (Makefile uses venv/)
make install   # install-py + install-js + pre-commit hooks
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Set environment variables
export DATABASE_URL="sqlite:///$(pwd)/data/iptv_proxy.db"

# Initialize database
python app.py  # Auto-creates tables on startup

# Run the application
python app.py  # Runs on http://localhost:8000
```

### Docker Development

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f iptv-proxy-v2

# Run commands in container
docker exec -it iptv-proxy-v2 python app.py
docker exec -it iptv-proxy-v2 pytest tests/
```

## Testing

Post-merge operator smoke checks (Waves 1–9): [SMOKE_TEST_POST_MERGE.md](./SMOKE_TEST_POST_MERGE.md).

### Test Requirements
- **Minimum 75% code coverage** (enforced in CI)
- All tests must pass before merging
- Write tests for new features

### Test Commands

Tests use **pytest-xdist** (`-n auto`) by default so each worker gets its own SQLite file (`instance/pytest_gw0.db`, …). Serial runs still use `instance/pytest.db`.

**pytest-randomly** shuffles test collection order on every run (including parallel) to catch order-dependent failures. The first line of pytest output includes `Using --randomly-seed=…`; failed runs repeat the seed so you can reproduce:

```bash
make test-clean
venv/bin/pytest tests/ -q --no-cov -n auto --randomly-seed=1234567890
```

To keep the same seed across multiple local runs while debugging, add `--randomly-dont-reset-seed`. To disable shuffling for one run: `--randomly-dont-shuffle`.

```bash
# Run all tests with coverage (parallel; matches CI)
make test

# Run tests without coverage (parallel, fastest local loop)
make test-fast

# Serial run (debugging flakes or comparing pass counts)
make test-clean
venv/bin/pytest tests/ -q --no-cov

# Explicit parallel without Make (same as make test-fast / make test-parallel)
venv/bin/pytest tests/ -q --no-cov -n auto
make test-parallel   # alias for test-fast

# Run specific test file
pytest tests/test_tag_service.py -v --no-cov

# Run specific test
pytest tests/test_app.py::test_playlist_generation -v --no-cov

# Generate HTML coverage report
make test  # Creates htmlcov/ directory
```

### Test Structure

- **`tests/test_app.py`**: API endpoints, filter logic, playlist generation
- **`tests/test_tag_service.py`**: Tag extraction, pattern matching, ruleset logic
- **`tests/test_rulesets_api.py`**: Ruleset and TagRule CRUD operations
- **`tests/test_stream_service_factory.py`**: `STREAM_BACKEND` selection (`ffmpeg` vs `mediaflow`)
- **`tests/test_mediaflow_stream_service.py`**: MediaFlow proxy URL construction and streaming (mocked HTTP)
- **`tests/test_ffmpeg_stream_service.py`**: FFmpeg stream service (skipped when `ffmpeg` binary absent)

### Stream backend tests

Stream proxying supports two backends via `.env` / environment variables (see `.env.example`):

| Variable | Purpose |
|----------|---------|
| `STREAM_BACKEND` | `ffmpeg` (default) or `mediaflow` |
| `MEDIAFLOW_PROXY_URL` | MediaFlow Proxy base URL when using `mediaflow` |
| `MEDIAFLOW_API_PASSWORD` | Optional API password for MediaFlow Proxy |

Factory and MediaFlow unit tests use mocked HTTP and run in default CI with no external services:

```bash
pytest tests/test_stream_service_factory.py tests/test_mediaflow_stream_service.py -v --no-cov
```

FFmpeg integration tests require the `ffmpeg` and `ffprobe` binaries on `PATH`; they are skipped automatically when missing. To run them locally after installing ffmpeg:

```bash
pytest tests/test_ffmpeg_stream_service.py -v --no-cov
```

For a live MediaFlow stack, use `docker-compose.mediaflow.yml` and set `STREAM_BACKEND=mediaflow`.

### Writing Tests

```python
import pytest
from app import app, db
from models import Account, Channel, Tag

@pytest.fixture
def client():
    """Flask test client with in-memory database."""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

def test_channel_filtering(client):
    """Test that channel filters work correctly."""
    # Setup test data
    account = Account(name="Test", server="test.tv", username="user", password="pass")
    db.session.add(account)
    db.session.commit()
    
    # Test the endpoint
    response = client.get(f'/api/accounts/{account.id}/channels')
    assert response.status_code == 200
```

## Code Quality

### Required Commands

Pre-commit hooks run the same linters as CI on every `git commit` (`make lint-py` and `make lint-js`). Run **`make install` once** after clone (creates `venv/`, installs Python/JS deps, and registers hooks via `make install-hooks`). Hooks assume the venv is ready — they do **not** re-run `pip install`, `npm install`, or `pre-commit install` on each commit.

⚠️ **Run full CI parity before pushing** (pre-commit covers lint only; tests are not hooked):

```bash
make ci        # lint-py + lint-js + test-js + test (coverage ≥75%)
```

Individual targets:

```bash
make lint      # Python + JavaScript linters (same as pre-commit)
make test-fast # parallel pytest without coverage (quick local loop)
make test      # parallel pytest with coverage (matches CI test job)
make vulture   # dead-code scan (CI vulture job, warn-only)
make docker-build  # local image build (CI docker-build-smoke on PRs)
```

`make lint` and `make test` must pass before considering changes complete.

### Individual Quality Tools

```bash
# Auto-format code
make format

# Individual tools
black --check .          # Code formatting
flake8 .                 # Style checking
isort --check-only .     # Import sorting
mypy app.py models/ services/  # Type checking
```

### Code Style Guidelines

- Follow PEP 8
- Use type hints for function parameters and returns
- Maximum line length: 88 characters (black default)
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and single-purpose

## Database Lifecycle (SQLite)

### Boot order (Docker / production)

[`entrypoint.sh`](../entrypoint.sh) runs **`flask db upgrade`** (Alembic via Flask-Migrate) on container start. This creates or updates all tables and records the revision in `alembic_version`.

**Fresh install:** `flask db upgrade` creates the full schema (~46 tables).

**Existing database (legacy runner):** If the DB was already migrated by the old `run_migrations.py` system (has a populated `schema_migrations` table), stamp Alembic once before upgrading the container image:

```bash
DATABASE_URL=sqlite:///data/iptv_proxy.db alembic stamp head
```

Leave the legacy `schema_migrations` table in place; it is historical only.

**Local init:** `flask init-db` runs `create_all()` only (dev convenience). For production parity use `flask db upgrade`.

### Foreign keys

SQLite requires `PRAGMA foreign_keys=ON` per connection. The app enables this in [`app.py`](../app.py) (`set_sqlite_pragma`). Alembic migrations run through the same SQLAlchemy engine. Migration DDL with `ON DELETE CASCADE` only takes effect when this pragma is set.

### Account deletion

Use [`services/account_delete_service.py`](../services/account_delete_service.py) — explicit deletion of all account-scoped rows. Global `tags`, `events`, and `rulesets` are preserved.

### Backups

Copy all three files when the app is running with WAL mode:

- `iptv_proxy.db`
- `iptv_proxy.db-wal`
- `iptv_proxy.db-shm`

### Scheduled data retention

The background scheduler (`services/scheduler.py`) prunes stale rows on interval:

| Data | Default retention | Schedule | Module |
|------|-------------------|----------|--------|
| EPG programs | 7 days | Daily | `services/epg/programs` |
| Health check history | 30 days | Weekly | `services/channel_health_service` |
| Finished events | 90 days (`EVENT_RETENTION_DAYS`) | Weekly | `services/event_retention` |
| Cached images (past `expires_at`) | Per-entry TTL | Daily | `services/image_cache_service` |

Manual event cleanup: `python scripts/cleanup_old_events.py --execute`. Image cache cleanup API: `POST /api/image-cache/cleanup`.

PPV orphan event pruning remains inline during enrichment (not scheduled).

### Adding a schema change

1. Update SQLAlchemy models in `models/`
2. `flask db revision --autogenerate -m "describe_change"`
3. Review the generated file in `alembic_migrations/versions/`
4. `flask db upgrade` locally
5. Add or extend `tests/test_migrations.py` / `tests/test_schema_parity.py`

### Indexes

Define indexes on SQLAlchemy models or in Alembic revisions. Apply with `flask db upgrade`.

## Database Migrations (Alembic)

Migrations live in [`alembic_migrations/`](../alembic_migrations/) (Flask-Migrate + Alembic). Legacy SQLite-only files are archived in [`migrations/legacy_sqlite/`](../migrations/legacy_sqlite/).

### Commands

```bash
# Apply pending migrations
flask db upgrade

# Roll back one revision
flask db downgrade

# Generate migration from model changes
flask db revision --autogenerate -m "add_foo_column"

# Stamp existing DB at current head (no DDL)
alembic stamp head

# Direct Alembic CLI (uses root alembic.ini)
alembic upgrade head
alembic current
```

### Migration guidelines

- Review autogenerate output — Alembic may miss renames or data backfills
- SQLite uses batch mode (`render_as_batch=True` in `alembic_migrations/env.py`); PostgreSQL uses native `ALTER TABLE`
- `compare_type=True` detects column type drift between models and database

### Running migrations

```bash
# Local
flask db upgrade

# Docker
docker exec -it iptv-proxy-v2 flask db upgrade
```

## Development Workflows

### Adding a New Feature

1. **Create a branch**: `git checkout -b feature/my-feature`
2. **Write tests first** (TDD approach)
3. **Implement the feature**
4. **Run quality checks**: `make lint && make test`
5. **Commit and push**
6. **Create pull request**

### Adding a New Service

```python
# services/my_service.py
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class MyService:
    """Service for handling X functionality."""
    
    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}
    
    def process_data(self, data: str) -> dict:
        """Process some data and return results."""
        try:
            # Implementation
            return {"result": "processed"}
        except Exception as e:
            logger.error(f"Error processing data: {e}")
            raise
```

### Adding a New Route

```python
# routes/my_routes.py
from flask import Blueprint, jsonify, request
from services.my_service import MyService

my_bp = Blueprint('my_routes', __name__)

@my_bp.route('/api/my-endpoint', methods=['GET'])
def my_endpoint():
    """Handle my endpoint."""
    service = MyService()
    result = service.process_data(request.args.get('data', ''))
    return jsonify(result)

# Register in app.py
from routes.my_routes import my_bp
app.register_blueprint(my_bp)
```

## Performance Guidelines

### Memory Management
With 10,000+ channels, avoid loading all data at once:

```python
# ❌ BAD - loads all tags for entire account
channel_tags = db.session.query(ChannelTag, Tag).join(Tag).filter(
    ChannelTag.account_id == account_id
).all()

# ✅ GOOD - batch processing
batch_size = 500
for i in range(0, len(stream_ids), batch_size):
    batch = stream_ids[i:i + batch_size]
    tags = db.session.query(ChannelTag.stream_id, Tag.name).join(Tag).filter(
        ChannelTag.account_id == account_id,
        ChannelTag.stream_id.in_(batch)
    ).all()
```

### Database Queries
1. **Lazy loading**: Only load tags for channels that need them
2. **Batching**: Query in batches of 500-1000 items
3. **Filtering first**: Apply non-tag filters before loading tags
4. **Pagination**: Never load all channels into memory

### Caching
- Use `CacheService` for expensive operations
- Clear cache after account updates: `cache_service.clear_account_cache(account_id)`
- Current TTL: 3600 seconds

## Common Patterns

### Route extraction services (Wave 9)

Large route modules from TODO 78 now follow **parse request → call service → serialize response**:

| Route module | Service | Notes |
|--------------|---------|-------|
| `routes/accounts.py` | `AccountAdminService` | Phase 1, PR #36 |
| `routes/config_transfer.py` | `ConfigTransferService` | Export/import bundle, PR #39 |
| `routes/epg/match_rules.py` | `EpgMatchRulesRouteService` | Preview/rematch orchestration, PR #42 |
| `routes/fcc_match_patterns.py` | `FccMatchPatternsService` | CRUD via `register_json_crud_routes`, PR #41 |

Shared entity serialization: `services/serializers/` (TODO 79). When adding endpoints to these areas, extend the service and tests first, then thin the route handler.

### PPV package layout (TODO 102)

After Wave 9 batch **AA** (PR #45), monolithic `services/ppv/epg.py` and `extraction.py` are packages:

| Package / module | Role |
|------------------|------|
| `services/ppv/epg/xmltv.py` | XMLTV builder |
| `services/ppv/epg/queries.py` | Event listing and detail queries |
| `services/ppv/epg/sync.py` | EpgSource / EpgChannel sync helpers |
| `services/ppv/epg/service.py` | `PPVEpgService` coordinator |
| `services/ppv/extraction/patterns.py` | Regex constants |
| `services/ppv/extraction/competitors.py` | Team/matchup extraction |
| `services/ppv/extraction/date_strategies/` | Per-format date parsers |
| `services/ppv/extraction/extractor.py` | `PPVEventExtractor` coordinator |
| `services/ppv/enrichment/` | Calendar enrichment pipeline (TODO 65 phase 1) |

Public imports remain stable at package boundaries (`from services.ppv.epg import PPVEpgService`, etc.).

### Service Import Paths

Use package imports for EPG and PPV services:

```python
# EPG — prefer submodule imports for new code
from services.epg.generation import generate_epg_for_channels
from services.epg.parsing import sync_epg_source, parse_xmltv
from services.epg.coverage import get_epg_coverage_stats
from services.epg.match_rules import EpgMatchRulesService
from services.ppv.detection import is_ppv_channel, is_ppv_category, is_ppv_placeholder_name
from services.epg.utils import normalize_xmltv_url, make_sd_xmltv_id

# PPV
from services.ppv.visibility import PPVVisibilityService
from services.ppv.enrichment import get_calendar_enrichment_service
from services.ppv.epg import PPVEpgService
from services.ppv.extraction import PPVEventExtractor
from services.ppv.matching.enhanced import EnhancedPPVMatcher
```

### Channel visibility (`is_visible` vs playlist output)

Playlist, preview, EPG, and Xtream routes use **`ChannelQueryService`** with **live filter evaluation**. They do **not** read the cached `Channel.is_visible` column.

| Mechanism | Purpose |
|-----------|---------|
| `FilterService.apply_filters_to_channels` | Live filter + PPV-placeholder evaluation for client output |
| `FilterService.compute_visibility_for_account` | Writes `is_visible` as an **admin/index cache** after filter CRUD |
| `ChannelQueryService.channels_for_account` | Single entry point for playlist-visible channels (live filters + PPV visibility + health auto-disable) |

**Rules for new code:**

- Use `ChannelQueryService.build_preview_channel_query()` / `preview_channels_for_account()` for admin preview endpoints instead of duplicating SQL in routes.

### Playlist config URLs (slug preferred)

Multi-account playlist and EPG config endpoints use slug URLs:

- `/playlist/config/<slug>.m3u`
- `/epg/config/<slug>.xml`

Per-account playlist/EPG endpoints use numeric account IDs:

- `/playlist/<account_id>.m3u`
- `/epg/<account_id>.xml`
- Treat `is_visible` as a filter cache for admin queries only; it may lag until recompute but must not gate playlists.
- Health auto-disable hides channels via `ChannelHealthStatus.auto_disabled_at`; CQS excludes those from output.
- PPV placeholder patterns live in `services/epg/constants.py` (re-exported from `services/ppv/constants.py`); import via `services.ppv.detection.is_ppv_placeholder_name`.

### JSON Field Handling

⚠️ **Important**: Several models store arrays as JSON text fields.

```python
# Always use json.loads()/json.dumps()
import json

# Reading
tags = json.loads(playlist_config.include_tags or '[]')

# Writing  
playlist_config.include_tags = json.dumps(['tag1', 'tag2'])
```

### Error Handling

```python
from error_handling import handle_errors
import logging

logger = logging.getLogger(__name__)

@handle_errors
@my_bp.route('/api/endpoint')
def my_endpoint():
    """Endpoint with consistent error handling."""
    try:
        result = some_operation()
        return jsonify(result)
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return jsonify({"error": "Invalid input"}), 400
```

### Database Transactions

```python
try:
    # Multiple operations
    db.session.add(new_object)
    db.session.flush()  # Get ID without committing
    
    related_object.parent_id = new_object.id
    db.session.add(related_object)
    
    db.session.commit()
except Exception as e:
    db.session.rollback()
    logger.error(f"Transaction failed: {e}")
    raise
```

## EPG Development

### EPG Architecture Overview

EPG generation uses a **database-first architecture**. All EPG program data is synced to the `EpgProgram` table by background jobs before being served to clients.

**Key Benefits:**
- No external API calls during playlist/EPG generation
- Consistent EPG data for all clients
- Works even if external sources are temporarily down
- Simpler code with single generation path

### EPG Data Flow

```
External Sources          Background Sync           Generation
─────────────────         ───────────────           ──────────
                                                    
Schedules Direct  ──┐                              
                    ├──> sync_sd_programs()   ──┐  
XMLTV Sources    ──┘     sync_xmltv()         ├──> EpgProgram ──> generate_epg_for_channels()
                         (Scheduler)          ─┘     (Database)        (No external calls)
```

### Working with EPG Sources

**Add a new Schedules Direct lineup:**
```python
from services.schedules_direct import SchedulesDirectClient

# Authenticate and get lineups
client = SchedulesDirectClient(username, password)
lineups = client.get_lineups()

# Create EPG source
source = EpgSource(
    account_id=account.id,
    name="My SD Lineup",
    source_type="schedules_direct",
    url="",  # Not used for SD
    username=username,
    password=password
)
db.session.add(source)
db.session.commit()

# Scheduler will automatically sync programs
```

**Add an XMLTV source:**
```python
source = EpgSource(
    account_id=account.id,
    name="My XMLTV Source",
    source_type="xmltv",
    url="http://example.com/epg.xml.gz"
)
db.session.add(source)
db.session.commit()

# Scheduler will fetch and parse XMLTV
```

### EPG Program Sync

Program sync happens in background scheduler (`services/scheduler.py`):

**Schedules Direct Sync** (`services/epg/sd_programs.py`):
```python
def sync_sd_programs_for_source(source, sd_client, days_ahead=14):
    """
    Sync programs from Schedules Direct API to database.
    
    1. Get station IDs from EPG channels
    2. Fetch schedules for next N days
    3. Fetch detailed program metadata
    4. Create/update EpgProgram records
    5. Delete old programs
    """
    # Returns stats: added, updated, deleted, channels_processed
```

**XMLTV Sync** (`services/epg_sync_service.py`):
```python
def sync_xmltv_to_database(source):
    """
    Parse XMLTV file and sync programs to database.
    
    1. Download XMLTV (supports gzip)
    2. Parse XML with streaming parser
    3. Match channels to EpgChannel records
    4. Create/update EpgProgram records
    """
```

### EPG Generation

Generation is handled by `services/epg/generation.py`:

```python
def generate_epg_for_channels(
    channels: List[Channel],
    use_channel_links: bool = True,
) -> bytes:
    """
    Generate XMLTV from database-stored programs.

    Resolution order:
    1. ChannelEpgMapping -> EpgProgram (database)
    2. ChannelLink -> inherit from source channel
    3. Synthetic channel (no programmes)
    """
```

**Key helper functions:**
```python
# services/epg/programs.py
get_programs_for_channels(epg_channel_ids, start_time, end_time)
  # Batch fetch programs from database

program_to_xmltv_element(program, channel_id, time_offset)
  # Convert EpgProgram to XMLTV <programme> element

generate_xmltv_from_database(channels, epg_channel_ids, start, end)
  # Core DB-to-XMLTV conversion
```

### Testing EPG Features

**Test program sync:**
```python
def test_sd_program_sync(app, db):
    """Test Schedules Direct program sync."""
    from services.epg.sd_programs import sync_sd_programs_for_source
    
    # Create mock SD source and channels
    source = EpgSource(...)
    db.session.add(source)
    
    # Create mock SD client
    mock_client = MagicMock()
    mock_client.get_schedules.return_value = [...]
    mock_client.get_programs.return_value = [...]
    
    # Run sync
    stats = sync_sd_programs_for_source(source, mock_client)
    
    assert stats["programs_added"] > 0
    assert EpgProgram.query.count() > 0
```

**Test EPG generation:**
```python
def test_epg_generation(app, db):
    """Test database-based EPG generation."""
    from services.epg.generation import generate_epg_for_channels
    
    # Create channel with EPG mapping
    channel = Channel(...)
    epg_channel = EpgChannel(...)
    mapping = ChannelEpgMapping(
        channel_id=channel.id,
        epg_channel_id=epg_channel.id
    )
    
    # Create program in database
    program = EpgProgram(
        epg_channel_id=epg_channel.id,
        start_time=datetime.now(),
        stop_time=datetime.now() + timedelta(hours=1),
        title="Test Program"
    )
    db.session.add_all([channel, epg_channel, mapping, program])
    db.session.commit()
    
    # Generate EPG
    result = generate_epg_for_channels([channel])
    
    # Parse and verify
    root = ET.fromstring(result)
    programmes = root.findall("programme")
    assert len(programmes) == 1
    assert programmes[0].find("title").text == "Test Program"
```

### EPG Debugging

**Check program sync status:**
```python
# Count programs per source
from models import EpgProgram, EpgChannel, EpgSource

stats = db.session.query(
    EpgSource.name,
    db.func.count(EpgProgram.id)
).join(EpgChannel).join(EpgProgram).group_by(EpgSource.id).all()

for source_name, count in stats:
    print(f"{source_name}: {count} programs")
```

**View recent programs:**
```python
from datetime import datetime, timezone
from models import EpgProgram

now = datetime.now(timezone.utc).replace(tzinfo=None)
recent = EpgProgram.query.filter(
    EpgProgram.start_time >= now
).order_by(EpgProgram.start_time).limit(10).all()

for p in recent:
    print(f"{p.start_time} - {p.title}")
```

**Force EPG sync:**
```python
from services.scheduler import run_epg_sync

# Sync specific source
source = EpgSource.query.filter_by(name="My Source").first()
run_epg_sync(source.id)
```

## Contributing Guidelines

**Cursor agents:** Follow `.cursor/rules/git-parallel-pr-workflow.mdc` for parallel PR git safety (isolated clones, worktree limits).

### Code Review Checklist
- [ ] Tests pass (`make test`)
- [ ] Code quality checks pass (`make lint`)
- [ ] New features have tests
- [ ] Documentation updated if needed
- [ ] Database migrations are idempotent
- [ ] Performance considerations addressed

### Commit Messages
```
feat: add new tag extraction rule
fix: resolve memory issue with large channel lists
docs: update API documentation
test: add coverage for playlist generation
refactor: simplify tag service logic
```

### Pull Request Process
1. Fork the repository
2. Create feature branch: `git checkout -b feature/description`
3. Make changes with tests
4. Run quality checks: `make lint && make test`
5. Commit changes with clear messages
6. Push and create pull request
7. Address review feedback
8. Merge after approval

### Issue Reporting
- Use GitHub issues for bugs and features
- Provide reproduction steps for bugs
- Include logs and environment details
- Tag issues appropriately (bug, enhancement, documentation)

## Troubleshooting

### Common Issues

**Tests failing with database errors**:
```bash
# Clear stale test databases (also run automatically before make test)
make test-clean
pytest tests/ -v
```

If you see `malformed database schema`, leftover SQLite files (including `-wal`/`-shm` sidecars) from a prior run are the usual cause. `make test-clean` removes serial (`pytest.db`) and xdist worker files (`pytest_gw*.db`).

**Parallel vs serial:** Default `make test` / `make test-fast` use `-n auto`. For a serial baseline or bisecting a flake, run `venv/bin/pytest tests/ -q --no-cov` after `make test-clean`.

**Order-dependent flakes:** If a test passes alone but fails in the full suite, copy `--randomly-seed` from the failure banner and rerun with the same seed (see **pytest-randomly** above). Fix shared fixtures, module-level state, or DB cleanup rather than relying on discovery order.

**Import errors in tests**:
```bash
# Make sure you're in virtual environment
source venv/bin/activate
pip install -r requirements-dev.txt
```

**Pre-commit passes but `git commit -am` fails with `invalid object` / `Error building trees`**:

This was caused by `make lint-py` depending on `make install`, which re-ran `pip install` (cloning sportsipy from git) and `pre-commit install` inside the commit hook while git held a locked index. Fixed in [TODO 104](./todos/104-fix-pre-commit-lint-hook-install-cycle.md): hooks now call `make lint-py`, which only uses the existing venv.

If you still see the error on an older branch, run `make install` once, then prefer `git add … && git commit` over `git commit -am`, or upgrade to a branch that includes the Makefile fix.

**Pre-commit / lint: command not found or missing tools**:
```bash
make install   # one-time: venv + deps + hooks
make lint-py   # verify linters run without reinstalling deps
```

**Docker container won't start**:
```bash
# Check logs
docker-compose logs iptv-proxy-v2

# Rebuild container
docker-compose build --no-cache
```

### Debug Mode

```bash
# Enable debug logging
export DEBUG=True
export LOG_LEVEL=DEBUG
python app.py
```

### Database Debugging

```python
# Enable SQLAlchemy query logging
import logging
logging.basicConfig()
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```
