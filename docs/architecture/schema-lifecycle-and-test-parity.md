# Schema Lifecycle and Test Parity

**Audit:** Application-wide audit, June 2026  
**Status:** Current (Wave 5 PR Q — TODOs 80, 81)

## Production boot path

```
entrypoint.sh:
  1. create_all()     — ORM creates tables from models
  2. run_migrations() — idempotent DDL patches + schema_migrations tracking
  3. App starts with PRAGMA foreign_keys=ON
```

Documented in `migrations/README.md` and `DEVELOPER_GUIDE.md`.

**Rule:** every schema change needs **both** model update and idempotent migration.

## Test path divergence

| Environment | create_all | migrations | Indexes |
|-------------|------------|------------|---------|
| Docker production | ✅ | ✅ | Full |
| pytest default fixture | ✅ | ❌ | Model only |
| test_migrations.py | ✅ | ✅ | Full |
| flask init-db | ✅ | ❌ | Model only |

**Resolved (TODO 80):** `ix_channel_ppv_queue` is defined on `Channel.__table_args__` so `create_all()` matches post-migration production.

## High-risk schema items

| Item | Severity | Tracking |
|------|----------|----------|
| `Event.external_id` global UNIQUE vs multi-source | High | TODO 55 |
| FK ondelete model/migration drift | Medium | TODO 81 — aligned for hot-path FKs; denormalized `channel_tags` documented |
| SQLite table-rebuild migrations | Medium | Document fragility |
| `channel_tags` without channel FK | Medium | Denormalized by design — see `ChannelTag` docstring; cleaned by AccountDeleteService / retention |

## schema_migrations table

Raw SQL tracking in `run_migrations.py` — not an ORM model. ~55 executable migrations, lexicographic ordering by filename.

**Edge case:** `run_migrations()` succeeds when DB file missing (no-op) — can leave ops confused.

## Test coverage

| Covered | Gaps |
|---------|------|
| Full migration chain (test_migrations.py) | Default conftest path |
| Critical tables + indexes (test_schema_parity.py) | PPV queue index, FK ondelete spot checks |
| FK=ON via app connection | FK=ON in `run_migrations.sqlite_connect`; `foreign_key_check` in test_migrations |
| EPG/health retention (test_data_retention.py) | Events, image cache |

## README doc drift

TODOs 35–39 marked ✅ in README but files missing — claimed work (FK alignment, schema parity, retention docs) hard to verify.

## Recommendations

1. Add migration-only indexes to models OR run migrations in conftest (TODO 80)
2. Expand schema parity suite (TODO 80, 81)
3. `PRAGMA foreign_keys=ON` in migration runner
4. Restore or archive missing P4 todo docs (TODO 87)
5. Scheduled retention for events/images (TODO 82)

## Related TODOs

- **55**, **80**, **81**, **82**, **87**
