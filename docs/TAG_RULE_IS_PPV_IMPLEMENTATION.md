# Tag Rule is_ppv Field Implementation

## Overview

Added a new `set_is_ppv` field to TagRule model that allows users to control the `is_ppv` flag on channels matching specific tag patterns. This solves issues where category-based PPV detection incorrectly marks channels (e.g., Bally Sports/FanDuel Sports Network channels in a "PPV" category that aren't actually PPV events).

## Use Case

**Problem:** Bally Sports (now FanDuel Sports Network) has a category called "PPV" in some Xtream Codes feeds, but the channels within this category are regular regional sports channels, not pay-per-view events. The current system marks all channels in a PPV category as `is_ppv=True`, which incorrectly excludes them from normal playlists.

**Solution:** Tag rules can now override the category-based PPV detection by setting `set_is_ppv` to one of three values:
- `keep` (default): Don't modify the channel's is_ppv value
- `set_true`: Force is_ppv=True for matching channels
- `set_false`: Force is_ppv=False for matching channels

## Implementation Details

### Database Changes

**Migration:** `migrations/2026_01_06_add_set_is_ppv_to_tag_rules.py`

Added `set_is_ppv` column to `tag_rules` table:
```sql
ALTER TABLE tag_rules ADD COLUMN set_is_ppv VARCHAR(20) NOT NULL DEFAULT 'keep'
```

**Model Constants:** Added to `models.py`:
```python
class TagRule(db.Model):
    # Constants for set_is_ppv field
    PPV_KEEP = "keep"
    PPV_SET_TRUE = "set_true"
    PPV_SET_FALSE = "set_false"
    
    set_is_ppv = db.Column(db.String(20), default=PPV_KEEP, nullable=False)
```

### Schema Validation

Updated `schemas.py` to validate the new field:
```python
class TagRuleCreateSchema(Schema):
    set_is_ppv = fields.String(
        load_default="keep",
        validate=validate.OneOf(["keep", "set_true", "set_false"]),
    )

class TagRuleUpdateSchema(Schema):
    set_is_ppv = fields.String(
        validate=validate.OneOf(["keep", "set_true", "set_false"]),
    )
```

### Tag Extraction Logic

**Updated `services/tag_service.py`:**

1. **extract_tags() signature changed:**
   ```python
   # Old:
   def extract_tags(...) -> Tuple[Set[str], str, str]:
   
   # New:
   def extract_tags(...) -> Tuple[Set[str], str, str, str]:
       # Returns (tags, cleaned_channel_name, cleaned_category_name, is_ppv_directive)
   ```

2. **Priority-based directive resolution:**
   - Rules are processed in priority order (lower numbers first)
   - First matching rule with `set_true` or `set_false` wins
   - Subsequent matching rules with `keep` don't override

3. **process_account_tags() applies directives:**
   ```python
   # Apply is_ppv directive
   if is_ppv_directive == "set_true" and not channel.is_ppv:
       channel.is_ppv = True
       is_ppv_changed += 1
   elif is_ppv_directive == "set_false" and channel.is_ppv:
       channel.is_ppv = False
       is_ppv_changed += 1
   ```

### Backward Compatibility

All existing calls to `extract_tags()` were updated to handle the 4-tuple return value:
- `routes/accounts.py`
- `routes/playlists.py`
- `services/sync_service.py`
- All test files (`tests/test_*.py`)

Pattern used: `tags, cleaned_name, _, _ = TagService.extract_tags(...)`
(The 4th value is only used by `process_account_tags()`)

## Usage Example

**Scenario:** Bally Sports PPV category has regular channels that shouldn't be marked as PPV

**Tag Rule Configuration:**
```python
{
    "name": "Bally Sports Not PPV",
    "pattern": "Bally Sports|FanDuel Sports",
    "pattern_type": "regex",
    "tag_name": "REGIONAL",
    "source": "category_name",
    "remove_from_name": False,
    "priority": 10,
    "set_is_ppv": "set_false"  # Override category-based PPV detection
}
```

**Result:** Channels matching this rule will have `is_ppv=False` even if their category has `is_ppv=True`.

## Testing

Created comprehensive test suite in `tests/test_tag_rule_is_ppv.py`:

1. ✅ `test_extract_tags_set_is_ppv_keep` - Default behavior
2. ✅ `test_extract_tags_set_is_ppv_true` - Force PPV true
3. ✅ `test_extract_tags_set_is_ppv_false` - Force PPV false
4. ✅ `test_extract_tags_first_match_wins` - Priority resolution
5. ✅ `test_process_account_tags_sets_is_ppv_true` - Database update true
6. ✅ `test_process_account_tags_sets_is_ppv_false` - Database update false
7. ✅ `test_process_account_tags_keep_doesnt_change` - Keep behavior
8. ✅ `test_process_account_tags_no_change_if_already_correct` - Idempotent

**All tests pass:** 8/8 green
**Existing tests:** 120/120 still passing (tag_service + additional_coverage)
**Code quality:** All lint checks pass (black, flake8, isort, mypy)

## API Changes

No breaking changes to existing APIs. The new field is optional with a sensible default ("keep").

**Routes that need UI updates:**
- `/rulesets/<int:id>/rules` (tag rule create/edit) - need dropdown for set_is_ppv

## Future Enhancements

1. **UI Implementation:** Add dropdown in tag rule forms to select set_is_ppv value
2. **Bulk Operations:** Consider adding endpoint to apply is_ppv directives across all channels at once
3. **Reporting:** Add is_ppv_changed count to tag processing stats display

## Files Modified

- `models.py` - Added set_is_ppv field and constants
- `schemas.py` - Added validation for set_is_ppv
- `services/tag_service.py` - Extract and apply is_ppv directives
- `services/sync_service.py` - Updated extract_tags calls
- `routes/accounts.py` - Updated extract_tags calls
- `routes/playlists.py` - Updated extract_tags calls
- `tests/test_tag_service.py` - Updated extract_tags calls
- `tests/test_additional_coverage.py` - Updated extract_tags calls
- `tests/test_phase1_cleaned_names.py` - Updated extract_tags calls
- `tests/test_tag_rule_is_ppv.py` - New comprehensive test suite
- `migrations/2026_01_06_add_set_is_ppv_to_tag_rules.py` - Database migration

## Rollout Checklist

- [x] Database migration created and tested
- [x] Model updated with new field
- [x] Schema validation added
- [x] Tag extraction logic updated
- [x] Tag processing logic updated
- [x] All extract_tags callers updated
- [x] Comprehensive tests written
- [x] All existing tests passing
- [x] Code formatted and linted
- [ ] UI forms updated (pending)
- [ ] API documentation updated (pending)
- [ ] User documentation updated (pending)

## Migration Instructions

1. Run migration: `python run_migrations.py`
2. Restart application to load new model definition
3. Existing tag rules will default to `set_is_ppv="keep"` (no behavior change)
4. Create new rules or update existing ones with `set_is_ppv="set_false"` for Bally Sports case
5. Run tag reprocessing: Navigate to account settings → "Reprocess Tags"

## Performance Notes

- No additional database queries added
- is_ppv changes only tracked when value actually changes (not on every tag processing run)
- Directive resolution happens during tag extraction (already optimized)
- Minimal memory impact (single string field per rule)
