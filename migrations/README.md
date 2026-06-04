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

# Existing DB already at current schema (legacy runner) — stamp without DDL
alembic stamp head
```

Configuration: [`alembic.ini`](../alembic.ini), [`alembic_migrations/`](../alembic_migrations/).

## Boot (Docker)

[`entrypoint.sh`](../entrypoint.sh) runs `flask db upgrade` on container start.

## Legacy system

Pre-Alembic SQLite migrations are archived in [`legacy_sqlite/`](legacy_sqlite/) for reference only.

## Adding a schema change

1. Update SQLAlchemy models in `models/`
2. `flask db revision --autogenerate -m "description"`
3. Review the generated file in `alembic_migrations/versions/`
4. `flask db upgrade` locally
5. Extend `tests/test_migrations.py` / `tests/test_schema_parity.py` if needed

See [DEVELOPER_GUIDE.md](../docs/DEVELOPER_GUIDE.md) for full workflow.
