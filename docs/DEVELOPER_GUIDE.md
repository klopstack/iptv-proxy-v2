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
