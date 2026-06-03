# PostgreSQL migration — raw `sqlite3` audit

**Wave 11 / TODO 111** — inventory of remaining raw `sqlite3` usage after
`services/fcc_pattern_reset.py` was migrated to SQLAlchemy (June 2026).

## Resolved in TODO 111

| File | Change |
|------|--------|
| `services/fcc_pattern_reset.py` | Replaced `sqlite3.connect` + `DROP TABLE` with `sqlalchemy.text()` via `db.engine.begin()`; seed via `services/fcc_seed_data.py` ORM loader |
| `services/fcc_seed_data.py` | New shared default seed module (used by reset CLI; legacy migration unchanged until TODO 113) |

## Remaining blockers (TODO 113 — Alembic migration system)

### Migration runner

| File | Usage | PG blocker |
|------|-------|------------|
| `run_migrations.py` | `sqlite3.connect`, `PRAGMA foreign_keys`, `INSERT OR IGNORE`, `sqlite_master` introspection | Hard — runner is SQLite-only |

### Migration modules (~31 files)

All files under `migrations/*.py` (except `__init__.py`) import `sqlite3` and call
`sqlite3.connect(db_path)` directly. Common SQLite-only patterns:

- `SELECT name FROM sqlite_master WHERE type='table'`
- `PRAGMA table_info(...)`
- `INTEGER PRIMARY KEY AUTOINCREMENT`
- `INSERT OR IGNORE`
- `ALTER TABLE ...` rebuild patterns

Representative files:

| File | Notable SQLite-only usage |
|------|---------------------------|
| `migrations/2024_01_add_indexes.py` | `sqlite_master` index introspection |
| `migrations/2024_03_add_channels_categories.py` | `AUTOINCREMENT` DDL |
| `migrations/2024_04_add_channel_tag_updated_at.py` | `PRAGMA table_info` |
| `migrations/2024_24_add_fcc_match_patterns.py` | Full DDL + seed (superseded for reset by `fcc_seed_data.py`) |
| `migrations/_sqlite_fk_repair.py` | `PRAGMA writable_schema=ON`, `UPDATE sqlite_master` — **impossible on PG** |
| `migrations/2026_05_30_fix_stale_foreign_key_references.py` | Imports `_sqlite_fk_repair` — historical SQLite repair, no-op on PG |

### Tests

| File | Usage | Action in 113/114 |
|------|-------|-------------------|
| `tests/test_migrations.py` | `sqlite3.connect`, `PRAGMA foreign_key_check`, `sqlite_master` | Gate SQLite-only assertions; add SQLAlchemy reflection for PG matrix (TODO 114) |
| `tests/test_epg_sync_api.py` | Inline `sqlite3` for migration smoke | Same |
| `tests/test_event_composite_unique_migration.py` | Raw sqlite for migration verify | Same |
| `tests/test_schema_parity.py` | Raw sqlite introspection | Same |
| `tests/ppv/test_orchestrator.py` | Raw sqlite setup | Same |

### Scripts (non-production, lower priority)

| File | Notes |
|------|-------|
| `scripts/cleanup_corrupt_ppv_data.py` | Direct sqlite3 |
| `scripts/cleanup_low_confidence_matches.py` | Direct sqlite3 |

## Recommended TODO 113 sequence

1. Add Alembic + `alembic/versions/` baseline from current ORM models.
2. Archive `migrations/` and `run_migrations.py` (keep read-only for reference).
3. Port `_sqlite_fk_repair` migration as **skipped/no-op** in Alembic history.
4. Wire Docker/CI entrypoint to `alembic upgrade head` (TODO 115).
5. Gate or rewrite `tests/test_migrations.py` (TODO 114).

## Out of scope (Series B)

- Data export/import tooling (TODO 116–117)
- Production cutover (TODO 118)
- Post-cutover cleanup (TODO 119)
