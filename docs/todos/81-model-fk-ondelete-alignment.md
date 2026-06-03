# Model FK ondelete alignment and schema hardening

**Status:** ⬜ Not started  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

Referential integrity is partial and inconsistent between models and migration DDL:

- Many FKs omit `ondelete` in models while migrations specify `ON DELETE CASCADE` (e.g. `active_streams.credential_id`)
- `channel_tags` keys `(account_id, stream_id, tag_id)` without FK to `channels.id` — denormalized; stale rows possible
- `channels.category_id` has no `ondelete`; `categories.parent_id` has no FK
- `XtreamCredential` nullable `account_id`/`playlist_config_id` with no XOR constraint
- Migrations run with `PRAGMA foreign_keys=OFF` (raw sqlite3)
- App uses `PRAGMA foreign_keys=ON` — behavior differs between migration and runtime

`AccountDeleteService` handles account-scoped cleanup explicitly; global tables (events, rulesets) preserved by design.

## Affected files

- `models/channel.py`, `models/account.py`, `models/epg_match.py`, `models/health.py`
- `migrations/` — alignment migrations as needed
- `run_migrations.py`
- `services/account_delete_service.py`

## Proposed solution

1. Audit each FK: document intended `CASCADE` / `SET NULL` / app-level delete
2. Align model `ForeignKey(..., ondelete=...)` with migrations
3. Enable `PRAGMA foreign_keys=ON` in migration runner
4. Document denormalized `channel_tags` invariant or add optional `channel_id` FK
5. Add `PRAGMA foreign_key_check` to CI migration chain test

## Acceptance criteria

- [ ] Model metadata matches migration DDL for ondelete semantics
- [ ] Migration runner enables foreign keys
- [ ] Account delete tests still pass

## Test plan

- Expand schema parity tests with `foreign_key_list` checks
- Account delete integration test unchanged

## Dependencies

- TODO 80 (schema test infrastructure)
