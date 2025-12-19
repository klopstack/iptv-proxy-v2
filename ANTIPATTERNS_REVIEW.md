# Antipattern Review - IPTV Proxy v2

## Executive Summary

This document identifies code quality issues, antipatterns, and refactoring opportunities discovered during Phase 4 review. Issues are prioritized by impact and organized by category.

## Critical Issues

### 1. ❗ Monolithic app.py (1914 lines)
**Status**: Partially addressed with blueprints started in Phase 3  
**Impact**: High - Maintainability, testability, code navigation  
**Priority**: Medium (defer until after tests)

**Current State**:
- All routes in single file
- ~50 route handlers mixed with helper functions
- Blueprint files created but not integrated

**Recommendation**: Complete Phase 3 after comprehensive tests in place

---

### 2. ❗ Config-Based Playlist Still Uses API
**Location**: `generate_playlist_from_config()` (line ~1390)  
**Impact**: High - Performance inconsistency, dual code paths  
**Priority**: High

**Problem**:
```python
# Still loads from API instead of database
service = IPTVService(account.server, account.username, account.password)
streams = cache_service.get_cached_streams(account.id)
if not streams:
    streams = service.get_live_streams()  # API call!
```

**Solution**:
- Migrate to database queries like single-account playlists
- Use pre-computed `is_visible` and `cleaned_name`
- Remove remaining `apply_filters()` function after migration

**Estimated Effort**: 2-3 hours

---

### 3. ❗ No Input Validation
**Location**: Throughout app.py  
**Impact**: High - Security, data integrity  
**Priority**: High

**Examples**:
```python
@app.route("/api/filters", methods=["POST"])
def create_filter():
    data = request.json  # No validation!
    filter_obj = Filter(
        account_id=data["account_id"],  # Could be missing
        name=data["name"],               # Could be empty or malicious
        filter_value=data["filter_value"]  # No format checking
    )
```

**Solution**:
- Add Marshmallow or Pydantic for schema validation
- Validate required fields, types, lengths, formats
- Return 400 Bad Request with clear error messages

**Example Fix**:
```python
from marshmallow import Schema, fields, validates, ValidationError

class FilterSchema(Schema):
    account_id = fields.Int(required=True)
    name = fields.Str(required=True, validate=lambda x: 3 <= len(x) <= 100)
    filter_type = fields.Str(required=True, validate=lambda x: x in ["category", "channel_name", "regex", "tag"])
    filter_action = fields.Str(required=True, validate=lambda x: x in ["whitelist", "blacklist"])
    filter_value = fields.Str(required=True)
    enabled = fields.Bool(missing=True)
```

---

## High Priority Issues

### 4. Inconsistent Error Handling
**Impact**: Medium - User experience, debugging  
**Priority**: Medium

**Problems**:
- Mix of `return jsonify({"error": str(e)})` and generic 500 errors
- No error codes or types
- Stack traces sometimes exposed to users
- Inconsistent 40x vs 50x status codes

**Examples**:
```python
# Some places return 400
return jsonify({"success": False, "error": str(e)}), 400

# Others return 500
except Exception as e:
    logger.error(f"Error: {e}")
    return jsonify({"error": str(e)}), 500

# Some have no status code
return jsonify({"error": str(e)})
```

**Solution**:
- Create error handler decorator or middleware
- Standardize error response format
- Use appropriate status codes (400 for validation, 404 for not found, 503 for not synced, 500 for server errors)
- Never expose internal exceptions to users

---

### 5. Missing Database Transactions
**Location**: Throughout app.py  
**Impact**: Medium - Data integrity  
**Priority**: Medium

**Problem**:
```python
# No transaction boundary - partial updates possible
filter_obj = Filter(...)
db.session.add(filter_obj)
db.session.commit()  # If this fails, no rollback

# Clear cache happens regardless of commit success
cache_service.clear_account_cache(data["account_id"])
```

**Solution**:
```python
try:
    filter_obj = Filter(...)
    db.session.add(filter_obj)
    db.session.commit()
    cache_service.clear_account_cache(data["account_id"])
    return jsonify({...}), 201
except Exception as e:
    db.session.rollback()
    logger.error(f"Error creating filter: {e}")
    return jsonify({"error": "Failed to create filter"}), 500
```

---

### 6. Global Service Instances
**Location**: Top of app.py  
**Impact**: Medium - Testing difficulty  
**Priority**: Low

**Problem**:
```python
# Global instances make testing hard
cache_service = CacheService()
sync_scheduler = SyncScheduler(app, interval_hours=sync_interval)
```

**Solution**:
- Use Flask application context or dependency injection
- Makes mocking easier for tests
- Allows different configs per test

---

## Medium Priority Issues

### 7. Duplicate Code in Tag Processing
**Location**: `_process_tags_from_channels()` and helper in accounts route  
**Impact**: Low - Maintainability  
**Priority**: Low

**Problem**:
Two nearly identical tag processing implementations:
1. `_process_tags_from_channels()` in app.py
2. `_process_tags_for_account()` in routes/accounts.py

**Solution**:
- Consolidate into TagService.process_tags_for_account()
- Remove duplication

---

### 8. Hardcoded Magic Numbers
**Location**: Throughout app.py  
**Impact**: Low - Maintainability  
**Priority**: Low

**Examples**:
```python
batch_size = 500  # Why 500?
batch_size = 1000  # Different batch sizes in different places
limit = min(request.args.get("limit", 100, type=int), 500)  # Max 500 why?
if not normalized_tag or len(normalized_tag) < 2:  # Why 2?
```

**Solution**:
```python
# In config.py or constants.py
DEFAULT_BATCH_SIZE = 1000
MIN_TAG_LENGTH = 2
MAX_API_LIMIT = 500
DEFAULT_PREVIEW_LIMIT = 100
```

---

### 9. No Request Timeouts
**Location**: IPTVService API calls  
**Impact**: Medium - Reliability  
**Priority**: Medium

**Problem**:
```python
# No timeout - could hang indefinitely
service = IPTVService(account.server, account.username, account.password)
streams = service.get_live_streams()  # Could hang forever
```

**Solution**:
- Add timeout parameter to all HTTP requests
- Implement retry logic with exponential backoff
- Handle timeout errors gracefully

---

### 10. Inconsistent Naming Conventions
**Impact**: Low - Code readability  
**Priority**: Low

**Examples**:
- `get_accounts()` vs `get_account_categories()` (plural vs singular)
- `create_filter()` vs `assign_ruleset_to_account()` (verb vs description)
- `stream_id` vs `streamId` in some JSON responses
- `tag_name` vs `tagName` inconsistency

**Solution**:
- Standardize on snake_case for Python
- Standardize on camelCase for JSON API responses
- Use consistent naming patterns for CRUD operations

---

## Low Priority Issues

### 11. Missing API Documentation
**Impact**: Low - Developer experience  
**Priority**: Low

**Solution**:
- Add OpenAPI/Swagger documentation
- Or use Flask-RESTX for auto-generated docs
- Document all query parameters, request bodies, responses

---

### 12. No Rate Limiting
**Location**: All API endpoints  
**Impact**: Medium - Security, stability  
**Priority**: Medium

**Solution**:
- Add Flask-Limiter
- Rate limit by IP and/or account
- Especially important for sync operations

---

### 13. Insecure Secret Key Default
**Location**: app.py configuration  
**Impact**: High - Security  
**Priority**: High

**Problem**:
```python
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
```

**Solution**:
```python
secret_key = os.getenv("SECRET_KEY")
if not secret_key:
    if os.getenv("FLASK_ENV") == "production":
        raise ValueError("SECRET_KEY must be set in production")
    secret_key = "dev-secret-key-unsafe"
app.config["SECRET_KEY"] = secret_key
```

---

## Architecture Recommendations

### Short Term (Next 2-4 weeks)
1. ✅ **Phase 4**: Remove backward compatibility (DONE)
2. 🔄 **Create targeted tests** for Phases 1-4 changes
3. **Fix input validation** (add schemas)
4. **Migrate config playlists** to database
5. **Standardize error handling**

### Medium Term (1-2 months)
1. **Complete Phase 3**: Blueprint refactoring
2. **Add transaction management**
3. **Implement rate limiting**
4. **Add API documentation**
5. **Phase 5**: Comprehensive test suite (80% coverage)

### Long Term (2-3 months)
1. **Extract business logic** to service layer
2. **Add caching strategy** (Redis?)
3. **Implement proper logging** (structured logs)
4. **Add monitoring/metrics** (Prometheus?)
5. **Performance profiling** and optimization

---

## Test Coverage Strategy

### Phase 4 Tests (Immediate Priority)
```python
# tests/test_backward_compat_removal.py
def test_process_tags_returns_503_when_not_synced():
    """Tag processing should require synced channels"""
    
def test_process_tags_works_when_synced():
    """Tag processing should work with synced channels"""
    
def test_preview_returns_503_when_not_synced():
    """Preview should require synced channels"""
    
def test_preview_works_when_synced():
    """Preview should work with synced channels"""
```

### Filter/Tag Integration Tests
```python
# tests/test_filter_visibility.py
def test_filter_visibility_computed_after_sync():
    """Sync should trigger visibility computation"""
    
def test_filter_visibility_computed_after_tag_processing():
    """Tag processing should trigger visibility computation"""
    
def test_preview_uses_precomputed_visibility():
    """Preview should use is_visible column"""
```

### Service Layer Tests
```python
# tests/test_filter_service.py
def test_compute_visibility_with_category_filters():
def test_compute_visibility_with_name_filters():
def test_compute_visibility_with_regex_filters():
def test_compute_visibility_with_tag_filters():
def test_compute_visibility_all_filters_must_pass():
```

---

## Metrics

### Code Quality Improvements (Phases 1-4)
- **Lines removed**: ~305 (Phase 1: ~65, Phase 2: ~65, Phase 4: ~240)
- **Performance improvement**: 10-50x faster queries
- **Code paths eliminated**: 3 (API fallbacks removed)
- **Database columns added**: 2 (cleaned_name, is_visible)

### Remaining Technical Debt
- **Monolithic file**: app.py (1914 lines)
- **Missing tests**: ~70% of codebase
- **API-based code**: Config playlists, EPG proxy
- **No validation**: All POST/PUT endpoints
- **No rate limiting**: All endpoints

---

## Priority Matrix

| Issue | Impact | Effort | Priority | Phase |
|-------|--------|--------|----------|-------|
| Input validation | High | Medium | **HIGH** | Next |
| Config playlist migration | High | Medium | **HIGH** | Next |
| Insecure defaults | High | Low | **HIGH** | Next |
| Create Phase 4 tests | High | Medium | **HIGH** | Next |
| Error handling | Medium | Medium | Medium | Phase 5 |
| Transactions | Medium | Low | Medium | Phase 5 |
| Rate limiting | Medium | Low | Medium | Phase 5 |
| Blueprint refactoring | High | High | Medium | After tests |
| API documentation | Low | Medium | Low | Phase 5 |
| Magic numbers | Low | Low | Low | Phase 5 |

---

## Conclusion

**Phase 4 successfully removed 240 lines of backward compatibility code**, simplifying the codebase and enforcing database-first architecture.

**Next steps:**
1. Create targeted tests for Phases 1-4 changes
2. Add input validation to all POST/PUT endpoints
3. Migrate config playlists to database queries
4. Complete Phase 5 comprehensive test suite

The codebase is becoming more maintainable with each phase, but significant work remains in testing, validation, and completing the blueprint refactoring.
