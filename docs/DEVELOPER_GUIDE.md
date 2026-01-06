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
- Python 3.9+
- SQLite 3
- Docker (optional)

### Local Setup

```bash
# Clone the repository
git clone https://github.com/klopstack/iptv-proxy-v2.git
cd iptv-proxy-v2

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set environment variables
export DATABASE_URL="sqlite:///$(pwd)/data/iptv_proxy.db"
export SECRET_KEY="dev-secret-key"

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

### Test Requirements
- **Minimum 75% code coverage** (enforced in CI)
- All tests must pass before merging
- Write tests for new features

### Test Commands

```bash
# Run all tests with coverage
make test

# Run tests without coverage (faster)
make test-fast

# Run specific test file
pytest tests/test_tag_service.py -v

# Run specific test
pytest tests/test_app.py::test_playlist_generation -v

# Generate HTML coverage report
make test  # Creates htmlcov/ directory
```

### Test Structure

- **`tests/test_app.py`**: API endpoints, filter logic, playlist generation
- **`tests/test_tag_service.py`**: Tag extraction, pattern matching, ruleset logic
- **`tests/test_rulesets_api.py`**: Ruleset and TagRule CRUD operations
- **`test_tags.py`**: Standalone tag extraction validation (uses mock objects)

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

⚠️ **ALWAYS run these commands before committing**:

```bash
make lint    # Check code quality and formatting
make test    # Run full test suite with coverage
```

Both commands must pass before considering changes complete.

### Individual Quality Tools

```bash
# Auto-format code
make format

# Individual tools
black --check .          # Code formatting
flake8 .                 # Style checking
isort --check-only .     # Import sorting
mypy app.py models.py services/  # Type checking
```

### Code Style Guidelines

- Follow PEP 8
- Use type hints for function parameters and returns
- Maximum line length: 88 characters (black default)
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and single-purpose

## Database Migrations

Migrations live in `migrations/` and are named with date prefix (e.g., `2024_01_19_add_tag_rule_replacement.py`).

### Creating a Migration

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

### Migration Guidelines

- **Always make migrations idempotent** (safe to run multiple times)
- Check if changes exist before applying
- Use raw sqlite3, not SQLAlchemy (migrations receive db_path string)
- Return `(True, "message")` for success, `(False, "error")` for failure

### Running Migrations

```bash
# Local
python run_migrations.py

# Docker
docker exec -it iptv-proxy-v2 python run_migrations.py
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
    account_xml_cache: Optional[Dict[int, bytes]] = None,  # Deprecated
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
# Clear any existing test databases
rm -f test_*.db
pytest tests/ -v
```

**Import errors in tests**:
```bash
# Make sure you're in virtual environment
source .venv/bin/activate
pip install -r requirements-dev.txt
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
