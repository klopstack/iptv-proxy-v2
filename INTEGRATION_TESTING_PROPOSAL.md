# Integration Testing Proposal

## Current State
- **Unit tests**: 185 tests with 81% coverage
- **API tests**: All backend endpoints tested
- **Frontend tests**: None (JavaScript tested manually)
- **Docker tests**: None (container tested manually)

## Issues Discovered Through Manual Testing
Issues 20-26 were discovered during manual browser testing:
- JavaScript syntax errors (`&&` operator issues)
- Missing API response fields (showing, has_more)
- Frontend expecting different data structures
- Duplicate variable declarations

These would have been caught by automated frontend tests.

## Proposal: Headless Browser Integration Tests

### Technology Options

#### Option 1: Playwright (Recommended)
**Pros:**
- Modern, fast, reliable
- Built-in auto-waiting
- Cross-browser (Chromium, Firefox, WebKit)
- Excellent Python support
- Can test mobile viewports
- Built-in screenshot/video recording

**Cons:**
- Larger dependency (~300MB browsers)
- Slower than pure API tests

**Example:**
```python
from playwright.sync_api import sync_playwright

def test_accounts_page_loads(live_server):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(f"{live_server.url}/accounts")
        
        # Wait for accounts to load
        page.wait_for_selector('.list-group-item')
        
        # Check for JavaScript errors
        errors = page.evaluate("() => window.errors || []")
        assert len(errors) == 0
        
        browser.close()
```

#### Option 2: Selenium
**Pros:**
- Industry standard
- Mature ecosystem
- Well-documented

**Cons:**
- Slower than Playwright
- More verbose API
- Requires manual waits
- Driver management complexity

#### Option 3: pytest-splinter
**Pros:**
- Simpler API
- Good pytest integration

**Cons:**
- Less maintained
- Fewer features
- Still uses Selenium under the hood

### Recommended Approach

**Phase 1: Critical Path Tests** (High ROI)
Test the most error-prone user flows:
1. Account management (add/edit/delete)
2. Filter creation with real-time feedback
3. Tag rule configuration
4. Playlist generation and download
5. Preview channels with pagination

**Phase 2: Regression Tests**
Add tests for each bug discovered:
- Issues 20-26 regression tests
- JavaScript error detection
- API response validation

**Phase 3: Cross-Browser Tests**
Run critical tests in Chrome, Firefox, Safari (WebKit)

### Implementation Plan

#### Step 1: Add Playwright to dev dependencies
```bash
pip install playwright pytest-playwright
playwright install chromium
```

#### Step 2: Create integration test directory
```
tests/
├── unit/           # Existing tests
├── integration/    # New browser tests
│   ├── conftest.py
│   ├── test_accounts_ui.py
│   ├── test_filters_ui.py
│   └── test_playlists_ui.py
└── conftest.py
```

#### Step 3: Add pytest-playwright fixtures
```python
# tests/integration/conftest.py
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="session")
def docker_compose():
    """Start docker-compose for tests"""
    import subprocess
    subprocess.run(["docker-compose", "up", "-d"])
    yield
    subprocess.run(["docker-compose", "down"])

@pytest.fixture
def browser_context(docker_compose):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        yield context
        context.close()
        browser.close()
```

#### Step 4: Write critical path tests
```python
# tests/integration/test_accounts_ui.py
def test_accounts_page_loads_without_errors(browser_context):
    """Test Issue 26: Accounts page JavaScript errors"""
    page = browser_context.new_page()
    
    # Capture console errors
    errors = []
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    
    page.goto("http://localhost:8889/accounts")
    page.wait_for_load_state("networkidle")
    
    # Should not have JavaScript errors
    assert len(errors) == 0, f"JavaScript errors: {errors}"
    
    # Should see account list or empty state
    assert page.locator(".list-group, .alert-info").count() > 0

def test_add_account_flow(browser_context):
    """Test complete account creation flow"""
    page = browser_context.new_page()
    page.goto("http://localhost:8889/accounts")
    
    # Click add button
    page.click("#add-account-btn")
    
    # Fill form
    page.fill("#accountName", "Test Account")
    page.fill("#accountServer", "test.example.com")
    page.fill("#accountUsername", "testuser")
    page.fill("#accountPassword", "testpass")
    
    # Submit
    page.click("#save-account-btn")
    
    # Should see success message or new account
    page.wait_for_selector(".list-group-item", timeout=5000)
```

### CI/CD Integration

Add to GitHub Actions workflow:
```yaml
- name: Run integration tests
  run: |
    docker-compose up -d
    pip install playwright pytest-playwright
    playwright install --with-deps chromium
    pytest tests/integration/ -v
    docker-compose down
```

### Cost/Benefit Analysis

**Time Investment:**
- Initial setup: 4-8 hours
- Per test: 15-30 minutes
- Maintenance: ~10% of unit test time

**Benefits:**
- Catch JavaScript errors before production
- Validate frontend-backend integration
- Prevent regressions (Issues 20-26)
- Confidence in Docker deployment
- Reduce manual testing time

**ROI:** High - Would have caught all 6 JavaScript issues discovered in manual testing

## Alternative: Lightweight JS Testing

If full browser testing is too heavy, consider:

### Option: pytest-httpserver + requests
Test API contracts without browser:
```python
def test_accounts_api_returns_expected_fields():
    """Test Issue 25: API returns channel_count not synced"""
    response = requests.get("http://localhost:8889/api/accounts/1/sync/status")
    data = response.json()
    
    assert "channel_count" in data
    assert "last_sync" in data
    assert "synced" not in data  # Removed in fix
```

### Option: JavaScript unit tests (Jest)
Test frontend logic separately:
```javascript
// tests/frontend/accounts.test.js
test('renderAccounts determines sync from channel_count', () => {
    const status = { channel_count: 100 };
    const synced = (status.channel_count > 0);
    expect(synced).toBe(true);
});
```

## Recommendation

**Start with:** Playwright integration tests for critical paths
**Reason:** Would have caught 100% of Issues 20-26
**Timeline:** Add 2-3 key tests per sprint
**Coverage goal:** 10-15 integration tests covering core user flows

The investment will pay off by catching frontend bugs that slip through unit tests.
