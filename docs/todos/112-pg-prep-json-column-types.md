# Replace `db.Text`-as-JSON columns with `db.JSON` / `JSONB`-compatible types

**Status:** ✅ Complete (PR #66)  
**Priority:** P2  
**Track:** Database Migration — Series A (Preparation)

## Problem

The codebase stores JSON in `db.Text` columns and performs manual `json.dumps()` / `json.loads()` at the Python layer. This pattern was chosen because SQLite's `JSON1` extension (available since SQLite 3.9.0 / ~2015) provides `json_extract()` and `json_each()` helpers, but SQLAlchemy's `db.JSON` type on older SQLite shipped as `Text` anyway, and the application never queries JSON fields at the SQL level.

On PostgreSQL, these fields should be `JSONB` to:
- Enable native GIN index support for future JSON queries
- Make column intent clear to tooling, ORMs, and observability
- Allow PostgreSQL to validate JSON on INSERT (no silent corruption)

The current pattern also means any place the application forgets to call `json.loads()` silently returns a raw JSON string instead of a Python object — a class of bug that `db.JSON` prevents.

## Current state

### Columns using `db.Text` to store JSON

| Model | Column | Comments in code |
|-------|--------|-----------------|
| `EpgSource` | `xmltv_extra_args` | "JSON array of extra arguments" |
| `EpgSource` | `sync_progress` | "JSON counters and status message" |
| `EpgChannel` | `display_names_json` | "JSON array of all display names" |
| `EpgChannel` | `matched_channels_json` | "Stores JSON of potential matches" |
| `EpgProgram` | `categories` | "JSON array of category strings" — has `get_categories()`/`set_categories()` ORM helpers |
| `SdStation` | `broadcast_language` | "JSON array as string" |

There are also `db.Text` columns storing structured-but-not-JSON data (e.g. `last_sync_message`, `description`) — those are legitimately `Text` and should not be changed.

### Manual JSON handling locations

`EpgProgram` has explicit property helpers that call `json.loads()`/`json.dumps()`:

```python
@property
def get_categories(self):
    ...
    return json.loads(self.categories)

def set_categories(self, categories):
    self.categories = json.dumps(categories) if categories else None
```

Callers across `services/epg/` use `get_categories` / `set_categories` instead of accessing the column directly. With `db.JSON`, these helpers become unnecessary boilerplate (SQLAlchemy handles the round-trip automatically).

## Proposed solution

### 1 — Change column type in models

Switch the identified columns from `db.Text` to `db.JSON`:

```python
# Before
xmltv_extra_args = db.Column(db.Text)  # JSON array of extra arguments

# After
xmltv_extra_args = db.Column(db.JSON, nullable=True)
```

`db.JSON` maps to:
- `TEXT` on SQLite (identical to current, with SQLAlchemy handling `json.dumps`/`json.loads` automatically)
- `JSON` or `JSONB` on PostgreSQL (prefer `JSONB` via `db.Column(postgresql.JSONB)` or dialect-aware column)

For portable code, use `db.JSON` in the model and override with `JSONB` in the PostgreSQL Alembic migration (TODO 117). Do not use `sqlalchemy.dialects.postgresql.JSONB` directly in model definitions — keep models dialect-agnostic.

### 2 — Remove manual json.dumps / json.loads wrappers

Once SQLAlchemy manages JSON serialization:
- Remove `get_categories()` and `set_categories()` from `EpgProgram` (or keep as read-through properties that return `self.categories` directly after migration).
- Update all call sites that reference `get_categories()` to access `epg_program.categories` directly.
- Grep for `json.loads(.*_json)` and `json.dumps(.*_json)` patterns across `services/` and remove them.

### 3 — Data migration for existing SQLite database

No schema change is required for SQLite (both `TEXT` and `JSON` map to `TEXT` at the storage level). Existing data remains valid as-is. SQLAlchemy will start calling `json.loads()` automatically on read instead of requiring the caller to do it — verify that no code path double-deserializes (i.e., calls `json.loads(column_value)` on a value that SQLAlchemy already deserialized).

For PostgreSQL, the Alembic migration (TODO 117) will define these as `JSONB` from scratch — no data conversion needed since the database is new.

### 4 — Null/default handling

`db.JSON` on SQLite will store `None` as SQL NULL (same as `db.Text`). Verify that model defaults (`nullable=True, default=None`) are consistent with how callers use the field. Any column where an empty array `[]` is semantically different from NULL should have `default=[]` or the application should handle both.

## Acceptance criteria

- [ ] All six `db.Text`-as-JSON columns are changed to `db.JSON` in their model definitions
- [ ] `EpgProgram.get_categories` / `set_categories` ORM helpers removed or updated to remove double-serialization
- [ ] `grep -rn "json.loads\|json.dumps" services/` shows no instances that read/write the JSON model columns identified above
- [ ] All existing tests pass with SQLite (no double-serialization regressions)
- [ ] New test: `EpgProgram.categories` round-trips a list through a DB write and read without manual `json.loads()`
- [ ] Model column comments updated to remove "JSON array as string" / "as string" qualifiers (the column is now properly typed)

## Test plan

```bash
# Full test suite (SQLite) — catch any double-serialization regressions
pytest tests/ -x -v

# Specific regression: categories round-trip
pytest tests/ -k epg_program -v

# Manual: create an EpgProgram with categories, commit, re-read, verify list type
# (not str) without json.loads()
```

## Affected files

- `models/epg.py` — `EpgSource.xmltv_extra_args`, `EpgSource.sync_progress`, `EpgChannel.display_names_json`, `EpgChannel.matched_channels_json`, `EpgProgram.categories`, `SdStation.broadcast_language`; remove `get_categories`/`set_categories`
- `services/epg/` — callers of `get_categories()`, `set_categories()`, manual `json.loads`/`json.dumps` on the listed columns
- `services/sync_service.py`, `services/epg/match_rules/patterns.py` — any EPG channel display_names_json access
- `tests/` — update fixtures that construct these objects with string values if they need to become Python dicts/lists

## Dependencies

- Can be done in parallel with [TODO 111](./111-pg-prep-raw-sqlite3-audit.md).
- Should be complete before [TODO 113](./113-pg-prep-alembic-migration-system.md) so the Alembic models are the final source of truth.
- The PostgreSQL-side `JSONB` promotion is handled in [TODO 117](./117-pg-migration-schema-creation.md) (Alembic migration from scratch).

## Risks

- **Double-deserialization**: If any service calls `json.loads(epg_program.categories)` and `EpgProgram.categories` is now a `db.JSON` column that SQLAlchemy already deserialized, the call raises `TypeError: the JSON object must be str, bytes or bytearray, not list`. A comprehensive `grep` pass before changing the model is essential.
- **`None` vs `[]`**: Some callers may rely on `categories` being a JSON-encoded string `"null"` or `"[]"` rather than Python `None`/`[]`. Audit return paths in serializers and API routes.
- **SQLite test suite timing**: `db.JSON` on SQLite does not validate JSON on INSERT (it's still TEXT). PostgreSQL `JSONB` rejects malformed JSON at the DB level. Tests that insert bad JSON strings directly will fail only against PostgreSQL — flag them during TODO 114 (test hardening).
