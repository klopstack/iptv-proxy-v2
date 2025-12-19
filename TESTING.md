# Testing Guide

This project uses pytest with comprehensive test coverage and linting requirements.

## Quick Start

```bash
# Install dev dependencies
make install

# Run all tests with coverage
make test

# Run tests without coverage (faster)
make test-fast

# Check code quality
make lint

# Auto-format code
make format
```

## Test Structure

### Test Files

- **`tests/test_app.py`**: API endpoints, filter logic, core functionality
- **`tests/test_tag_service.py`**: Tag extraction, pattern matching, ruleset retrieval
- **`tests/test_rulesets_api.py`**: Ruleset and TagRule CRUD operations
- **`test_tags.py`**: Standalone validation script (uses mock objects)

### Running Specific Tests

```bash
# Run single test file
pytest tests/test_tag_service.py -v

# Run specific test class
pytest tests/test_tag_service.py::TestTagExtraction -v

# Run specific test method
pytest tests/test_tag_service.py::TestTagExtraction::test_extract_tags_with_prefix -v

# Run tests matching pattern
pytest -k "tag" -v
```

## Coverage Requirements

- **Minimum coverage**: 70%
- **Coverage report**: Generated in `htmlcov/` directory
- **View coverage**: Open `htmlcov/index.html` in browser

```bash
# Generate coverage report
pytest --cov=. --cov-report=html

# View coverage in terminal
pytest --cov=. --cov-report=term-missing
```

## Linting Tools

### Flake8 (Style Checking)
```bash
# Check for syntax errors
flake8 . --count --select=E9,F63,F7,F82 --show-source

# Full style check
flake8 .
```

Configuration in `.flake8`:
- Max line length: 120
- Ignores: E203, E501, W503 (compatible with black)

### Black (Code Formatting)
```bash
# Check formatting
black --check .

# Auto-format code
black .
```

Configuration in `pyproject.toml`:
- Line length: 120
- Target: Python 3.8+

### isort (Import Sorting)
```bash
# Check import order
isort --check-only .

# Auto-sort imports
isort .
```

Configuration in `pyproject.toml`:
- Profile: black (compatible)
- Line length: 120

### mypy (Type Checking)
```bash
# Type check main files
mypy app.py models.py services/
```

Configuration in `pyproject.toml`:
- Ignore missing imports
- Warn on return types
- Not enforced for tests

## Writing Tests

### Test Fixtures

```python
@pytest.fixture
def client():
    """Test client with in-memory database"""
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client
        with app.app_context():
            db.drop_all()
```

### Example Test

```python
def test_create_account(client):
    """Test creating an account"""
    response = client.post('/api/accounts',
        json={
            'name': 'My IPTV',
            'server': 'example.com',
            'username': 'user123',
            'password': 'pass123'
        }
    )
    
    assert response.status_code == 201
    data = response.json
    assert data['name'] == 'My IPTV'
```

### Testing Service Methods

```python
def test_get_rules_for_account(test_app, sample_account, sample_ruleset):
    """Test getting rules for account with assigned ruleset"""
    with app.app_context():
        account = Account.query.get(sample_account.id)
        rules = TagService.get_rules_for_account(account)
        
        assert len(rules) > 0
        assert all(isinstance(rule, TagRule) for rule in rules)
```

## Continuous Integration

GitHub Actions automatically runs on:
- Push to `main` or `develop`
- Pull requests to `main` or `develop`

### CI Checks

1. **Linting** (single Python version)
   - flake8 syntax check
   - flake8 style check
   - black formatting check
   - isort import order check
   - mypy type check (non-blocking)

2. **Testing** (Python 3.9, 3.10, 3.11)
   - pytest with coverage
   - Minimum 70% coverage required
   - Coverage report uploaded to Codecov

### Viewing CI Results

Check the Actions tab in GitHub for:
- ✅ Passing tests
- ❌ Failed tests with details
- 📊 Coverage reports

## Common Issues

### Import Errors in Tests

Make sure you're importing from the correct modules:
```python
from app import app, db
from models import Account, RuleSet
from services.tag_service import TagService
```

### Database State Issues

Each test should be isolated. Use fixtures properly:
```python
@pytest.fixture
def sample_account(client):
    """Creates and returns an account for testing"""
    response = client.post('/api/accounts', json={...})
    return response.json
```

### Coverage Not Meeting Minimum

- Check which lines are missing coverage: `pytest --cov=. --cov-report=term-missing`
- Add tests for uncovered code paths
- Use `pragma: no cover` for truly untestable code (sparingly)

### Linting Failures

```bash
# Auto-fix most issues
make format

# Check what needs fixing
make lint
```

## Best Practices

1. **Test Naming**: Use descriptive names starting with `test_`
2. **One Assertion Per Test**: Keep tests focused
3. **Use Fixtures**: Don't repeat setup code
4. **Test Edge Cases**: Empty inputs, missing data, invalid types
5. **Mock External Services**: Don't call real IPTV APIs in tests
6. **Commit Formatted Code**: Run `make format` before committing
7. **Check Coverage**: Aim for >70%, but prioritize meaningful tests over percentage

## Resources

- [pytest documentation](https://docs.pytest.org/)
- [Coverage.py documentation](https://coverage.readthedocs.io/)
- [Flake8 documentation](https://flake8.pycqa.org/)
- [Black documentation](https://black.readthedocs.io/)
- [mypy documentation](https://mypy.readthedocs.io/)
