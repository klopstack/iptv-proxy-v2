# Schema Lifecycle and Test Parity

**Audit:** Application-wide audit, June 2026  
**Status:** Current (Wave 5 PR Q — TODOs 80, 81)

## Production boot path

```
entrypoint.sh:
  1. flask db upgrade — Alembic applies pending revisions (alembic_version)
  2. App starts with PRAGMA foreign_keys=ON
```

Documented in `migrations/README.md` and `DEVELOPER_GUIDE.md`.

**Rule:** every schema change needs **both** model update and an **Alembic revision**. Do not add executable DDL only under `migrations/legacy_sqlite/` — boot does not run that runner.

**Legacy gap (June 2026):** Post-baseline model columns shipped with only `legacy_sqlite/` migrations caused staging `no such column` errors until Alembic revisions `7f8e9d0c1b2a` and `6e7d8c9b0a1f` were added. Post-baseline revisions use idempotent column checks for DBs already patched manually.

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

## schema_migrations table (legacy, historical)

Pre-Alembic tracking in `migrations/legacy_sqlite/run_migrations.py` — not an ORM model. Existing production DBs may still have this table; Alembic uses `alembic_version` going forward. Do not add new migrations to the legacy runner.

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
