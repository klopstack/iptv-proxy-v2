# Input Validation Implementation

**Status:** ✅ Complete  
**Test Coverage:** 19 tests, all passing

## Overview

Implemented comprehensive input validation using Marshmallow schemas to prevent malformed data, database corruption, and improve error handling across all API endpoints.

## What Changed

### New Files

- **[schemas.py](schemas.py)** - Marshmallow validation schemas
  - AccountCreateSchema, AccountUpdateSchema
  - FilterCreateSchema, FilterUpdateSchema  
  - RuleSetCreateSchema, RuleSetUpdateSchema
  - TagRuleCreateSchema, TagRuleUpdateSchema
  - AccountRuleSetAssignSchema
  - PlaylistConfigCreateSchema, PlaylistConfigUpdateSchema
  - `@validate_request_data` decorator for easy application

- **[tests/test_validation.py](tests/test_validation.py)** - Validation test suite
  - 19 comprehensive tests covering all validation scenarios
  - Tests for valid data acceptance
  - Tests for invalid data rejection
  - Tests for clear error messages

### Modified Files

- **[app.py](app.py)** - Applied validation to 11 endpoints
  - POST /api/accounts
  - PUT /api/accounts/<id>
  - POST /api/filters
  - PUT /api/filters/<id>
  - POST /api/rulesets
  - PUT /api/rulesets/<id>
  - POST /api/accounts/<id>/rulesets
  - POST /api/tag-rules
  - PUT /api/tag-rules/<id>
  - POST /api/playlist-configs

- **[requirements.txt](requirements.txt)** - Added marshmallow==3.20.1

## Validation Rules

### Account
- `name`: 1-200 characters, required on create
- `server`: 1-255 characters, valid domain/IP format, required on create
- `username`: 1-100 characters, required on create
- `password`: 1-100 characters, required on create
- `enabled`: boolean, optional (defaults to True)

### Filter
- `account_id`: positive integer, required on create
- `name`: 1-100 characters, required on create
- `filter_type`: enum (category_whitelist, category_blacklist, channel_name, regex, tag_include, tag_exclude), required
- `filter_action`: enum (include, exclude), required
- `filter_value`: non-empty string (no whitespace-only), required
- `enabled`: boolean, optional (defaults to True)

### RuleSet
- `name`: 1-200 characters, required on create
- `description`: 0-500 characters, optional
- `is_default`: boolean, optional (defaults to False)

### TagRule
- `ruleset_id`: positive integer, required on create
- `name`: 1-200 characters, required on create
- `pattern`: 1-200 characters, non-whitespace, required on create
- `pattern_type`: enum (prefix, suffix, contains, regex), required
- `tag_name`: 1-100 characters, special tag format validation, required
  - Special tags must start AND end with `__` (e.g., `__CLEANUP__`)
- `source`: enum (channel_name, category_name, both), required
- `remove_from_name`: boolean, optional (defaults to True)
- `priority`: 1-1000, optional (defaults to 100)
- `enabled`: boolean, optional (defaults to True)

### PlaylistConfig
- `name`: 1-200 characters, required on create
- `include_accounts`: list of positive integers, optional
- `exclude_accounts`: list of positive integers, optional
  - ⚠️ Validation ensures no overlap between include/exclude
- `include_tags`: list of strings (1-100 chars each), optional
- `exclude_tags`: list of strings (1-100 chars each), optional
  - ⚠️ Validation ensures no overlap between include/exclude

## Error Responses

All validation failures return **400 Bad Request** with structured errors:

```json
{
  "error": "Validation failed",
  "validation_errors": {
    "field_name": ["Error message 1", "Error message 2"],
    "another_field": ["Error message"]
  }
}
```

### Examples

**Missing required fields:**
```json
{
  "error": "Validation failed",
  "validation_errors": {
    "server": ["Missing data for required field."],
    "username": ["Missing data for required field."],
    "password": ["Missing data for required field."]
  }
}
```

**Invalid field value:**
```json
{
  "error": "Validation failed",
  "validation_errors": {
    "filter_type": ["Must be one of: category_whitelist, category_blacklist, channel_name, regex, tag_include, tag_exclude."]
  }
}
```

**Custom validation:**
```json
{
  "error": "Validation failed",
  "validation_errors": {
    "include_accounts": ["Accounts cannot be in both include and exclude: {2}"]
  }
}
```

## Usage

### Applying Validation to Endpoints

Use the `@validate_request_data` decorator:

```python
from schemas import AccountCreateSchema, validate_request_data

@app.route("/api/accounts", methods=["POST"])
@validate_request_data(AccountCreateSchema)
def create_account():
    # Access validated data via request.validated_data
    data = request.validated_data
    
    account = Account(
        name=data["name"],
        server=data["server"],
        username=data["username"],
        password=data["password"],
        enabled=data.get("enabled", True)
    )
    # ... rest of handler
```

### Creating New Schemas

```python
from marshmallow import Schema, fields, validates, ValidationError

class MyResourceSchema(Schema):
    """Schema for my resource"""
    name = fields.Str(required=True, validate=lambda x: 1 <= len(x) <= 100)
    value = fields.Int(validate=lambda x: x > 0)
    enabled = fields.Bool(load_default=True)
    
    @validates('name')
    def validate_name(self, value):
        if not value.strip():
            raise ValidationError("Name cannot be empty")
```

## Testing

Run validation tests:

```bash
pytest tests/test_validation.py -v
```

Expected output:
```
19 passed in 0.21s
```

## Impact

### Security Improvements
- ✅ Prevents SQL injection through type validation
- ✅ Prevents invalid data in database
- ✅ Protects against malformed requests causing 500 errors
- ✅ Validates foreign key references exist

### User Experience Improvements
- ✅ Clear, actionable error messages
- ✅ Field-specific validation errors
- ✅ Consistent error response format
- ✅ Immediate feedback on invalid input

### Developer Experience Improvements
- ✅ Centralized validation logic in schemas
- ✅ Self-documenting API requirements
- ✅ Easy to add validation to new endpoints
- ✅ Type hints and validation in one place

## What's NOT Validated

The following endpoints do NOT have input validation yet:
- GET endpoints (query parameters)
- DELETE endpoints (no request body)
- POST /api/accounts/<id>/test (authentication test)
- POST /api/accounts/<id>/process-tags (no input)
- POST /api/accounts/<id>/sync (no input)
- POST /api/sync/all (no input)
- PUT /api/playlist-configs/<id> (would need PlaylistConfigUpdateSchema)

## Future Enhancements

1. **Query Parameter Validation**
   - Validate pagination parameters (limit, offset)
   - Validate filter/search parameters

2. **Additional Schema Features**
   - Custom error messages for each field
   - Conditional validation (e.g., regex validation for regex filter type)
   - Cross-field validation (e.g., end_date > start_date)

3. **API Documentation**
   - Generate OpenAPI/Swagger docs from schemas
   - Auto-generate API documentation

4. **Response Validation**
   - Use schemas to validate outgoing responses
   - Ensure consistent API response format

## Related Documentation

- [ANTIPATTERNS_REVIEW.md](ANTIPATTERNS_REVIEW.md) - Identified validation as critical priority
- [TESTING.md](TESTING.md) - General testing guide
- [Marshmallow Documentation](https://marshmallow.readthedocs.io/) - Schema library
