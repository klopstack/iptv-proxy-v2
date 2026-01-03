# Streams.py Testing - Quick Reference

## Test Execution

```bash
# Run all stream tests
pytest tests/test_streams_routes.py -v

# Run specific test class
pytest tests/test_streams_routes.py::TestErrorClassification -v

# Run single test
pytest tests/test_streams_routes.py::TestErrorClassification::test_classify_timeout_error -v

# Run with coverage report
pytest tests/test_streams_routes.py --cov=routes.streams --cov=services.stream_test_helpers

# Quick run (no coverage)
make test-fast
```

## Test Organization

| Class | Tests | Focus |
|-------|-------|-------|
| `TestErrorClassification` | 9 | Error classification logic from _proxy_stream |
| `TestStreamStatus` | 3 | Stream status endpoint |
| `TestActiveStreams` | 3 | Active streams listing endpoint |
| `TestReleaseStream` | 3 | Stream release endpoint |
| `TestCleanupStreams` | 4 | Stream cleanup endpoint |
| `TestStreamPlayer` | 3 | HTML player endpoint |
| `TestProxyStream` | 3 | Proxy stream endpoints (.ts, .m3u8) |
| `TestStreamConnectivityTest` | 7 | Connectivity testing endpoint |
| `TestMultiplexerStats` | 2 | Multiplexer statistics endpoints |
| **Total** | **36** | **100% passing** |

## Key Testing Approaches

### 1. Pure Function Testing (TestErrorClassification)
Tests functions extracted from route handlers:
```python
from services.stream_test_helpers import classify_error_and_get_status

# No Flask context needed
status, msg = classify_error_and_get_status("Connection timeout")
assert status == 504
```

### 2. Route Integration Testing
Uses Flask test client for realistic HTTP testing:
```python
response = client.get("/stream/123/stream.ts")
assert response.status_code == 404
```

### 3. Mock-based HTTP Testing
Mocks external HTTP requests:
```python
@patch("routes.streams.requests.head")
def test_test_stream_upstream_success(self, mock_head, app, client, test_account):
    mock_response = Mock()
    mock_response.status_code = 200
    mock_head.return_value = mock_response
    # Test upstream connectivity
```

### 4. Database Integration Testing
Uses real database transactions:
```python
with app.app_context():
    account = db.session.get(Account, test_account)
    account.enabled = False
    db.session.commit()
```

## Files Overview

### [tests/test_streams_routes.py](../tests/test_streams_routes.py)
- 36 comprehensive tests
- 9 test classes
- ~500 lines of test code
- 100% passing

### [services/stream_test_helpers.py](../services/stream_test_helpers.py)
- 5 extracted helper functions
- Independently testable
- Used by test_streams_routes.py
- Pure functions (no side effects)

## Helper Functions

All helpers in `services/stream_test_helpers.py`:

### `classify_error_and_get_status(error_msg: str) -> Tuple[int, str]`
Classifies error messages to HTTP status codes:
- "timeout" → 504
- "connection" → 502
- "404" or "not found" → 404
- "401", "403", or "auth" → 403
- Other → 502

### `build_upstream_url(server, username, password, stream_id, format) -> str`
Builds full upstream URL for stream requests.

### `build_safe_url(server, username, stream_id, format) -> str`
Builds URL for logging with masked credentials.

### `validate_account_prerequisites(account) -> Tuple[bool, str]`
Checks if account exists and is enabled.

### `validate_credential_prerequisites(credential) -> Tuple[bool, str]`
Checks if credential is available.

## Common Test Patterns

### Testing Missing Resources
```python
def test_proxy_stream_account_not_found(self, app, client):
    response = client.get("/stream/999/12345.ts")
    assert response.status_code == 404
```

### Testing with Fixtures
```python
def test_stream_status_success(self, app, client, test_account):
    response = client.get(f"/stream/{test_account}/status")
    assert response.status_code == 200
```

### Testing Error Handling
```python
@patch("routes.streams.requests.head")
def test_test_stream_upstream_timeout(self, mock_head, app, client, test_account):
    import requests
    mock_head.side_effect = requests.exceptions.Timeout("timeout")
    response = client.get(f"/stream/{test_account}/test123/test")
    data = response.json
    assert data["success"] is False
```

## Linting & Code Quality

```bash
# Format code
black tests/test_streams_routes.py services/stream_test_helpers.py

# Check linting
flake8 tests/test_streams_routes.py services/stream_test_helpers.py

# Type check
mypy tests/test_streams_routes.py services/stream_test_helpers.py
```

## Coverage Report

View HTML coverage report after running tests:
```bash
pytest tests/test_streams_routes.py --cov
# Open htmlcov/index.html in browser
```

## Debugging Tests

### Run with verbose output
```bash
pytest tests/test_streams_routes.py -vv -s
```

### Run single test with full traceback
```bash
pytest tests/test_streams_routes.py::TestErrorClassification::test_classify_timeout_error -vvv
```

### Show which tests collect
```bash
pytest tests/test_streams_routes.py --collect-only
```

## Best Practices Used

✅ **Isolation** - Each test is independent  
✅ **Clarity** - Descriptive test names  
✅ **Fixtures** - DRY setup with pytest fixtures  
✅ **Mocking** - External dependencies mocked  
✅ **Error Coverage** - Both success and failure paths tested  
✅ **Comments** - Clear documentation in docstrings  
✅ **Organization** - Tests grouped by functionality  
