# Model FK ondelete alignment and schema hardening

**Status:** ✅ Done (Wave 5 PR Q)  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Solution (implemented)

1. Aligned model `ForeignKey(..., ondelete=...)` with migrations for hot-path FKs:
   - `ActiveStream.credential_id` → CASCADE
   - `Channel.category_id` → SET NULL
   - `ChannelTag.tag_id` → CASCADE
   - `EpgMatchRule.ruleset_id` → CASCADE
2. `run_migrations.sqlite_connect()` enables `PRAGMA foreign_keys=ON` for tracking-table I/O
3. Documented denormalized `channel_tags` invariant on `ChannelTag` model
4. `test_migrations.py`: `foreign_key_check` after full migration chain; `test_schema_parity.py`: FK ondelete spot checks

**Not changed:** per-file migration modules still open their own connections (legacy). No new alignment migration — model + `create_all()` path is source of truth for new DBs.

## Acceptance criteria

- [x] Model metadata matches migration DDL for ondelete semantics (spot-checked tables)
- [x] Migration runner enables foreign keys (`sqlite_connect`)
- [x] Account delete tests still pass
