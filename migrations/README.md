# Database Migrations

Schema changes are managed by **Alembic** via **Flask-Migrate**.

## Quick reference

```bash
# Apply all pending migrations (local or Docker)
flask db upgrade

# Roll back one revision
flask db downgrade

# Generate a new migration after model changes
flask db revision --autogenerate -m "describe_change"

# Existing DB already at current schema — stamp without DDL (one-time ops only)
alembic stamp head
```

Configuration: [`alembic.ini`](../alembic.ini), [`alembic_migrations/`](../alembic_migrations/).

## Boot (Docker)

[`entrypoint.sh`](../entrypoint.sh) runs **`flask db upgrade` only** on container start.

**Every model change must have an Alembic revision.** Adding DDL only under `legacy_sqlite/` will not run in production and causes `no such column` errors at runtime.

## Legacy system

Pre-Alembic SQLite migrations are archived in [`legacy_sqlite/`](legacy_sqlite/) for **reference only**. Do not add new executable migrations there.

Databases upgraded by the legacy runner keep a `schema_migrations` table (historical). Alembic tracks applied work in `alembic_version`. Post-baseline Alembic revisions use idempotent column checks so manually legacy-patched DBs still upgrade.

## Adding a schema change

1. Update SQLAlchemy models in `models/`
2. `flask db revision --autogenerate -m "description"` (or hand-write incremental revision after baseline)
3. Review the generated file in `alembic_migrations/versions/` — verify `down_revision` chain
4. `flask db upgrade` locally
5. Extend `tests/test_migrations.py` / `tests/test_schema_parity.py`

See [DEVELOPER_GUIDE.md](../docs/DEVELOPER_GUIDE.md) for full workflow.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `no such column` after image deploy | Model/revision mismatch; DDL only in `legacy_sqlite/` | Add Alembic revision; run `flask db upgrade` |
| Alembic at head but columns missing | DB stamped without post-baseline revisions | `flask db upgrade` (idempotent revisions apply missing columns) |
| Fresh DB missing columns | Baseline predates column; no incremental revision | Ensure revision chain reaches `head` |
