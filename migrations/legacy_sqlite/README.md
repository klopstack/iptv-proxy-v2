# Legacy SQLite migration artifacts (archived)

These files are **inert historical artifacts** from the pre-Alembic migration system (TODO 113). They are kept for forensic reference only — do not run them in production or CI.

## What replaced this

- **Alembic** + **Flask-Migrate** in [`alembic_migrations/`](../../alembic_migrations/)
- Root [`alembic.ini`](../../alembic.ini) for the `alembic` CLI
- Apply schema: `flask db upgrade` or `alembic upgrade head`
- Track revisions in `alembic_version` (not `schema_migrations`)

## Contents

| File | Purpose |
|------|---------|
| `run_migrations.py` | Legacy runner — discovered `*.py` files here alphabetically |
| `2024_*.py` … `2026_*.py` | Idempotent SQLite-only DDL patches |
| `_sqlite_fk_repair.py` | SQLite `sqlite_master` FK repair helper |

## Existing SQLite deployments

If your database was fully migrated by the legacy runner (has `schema_migrations` rows), **stamp** Alembic instead of re-running DDL:

```bash
DATABASE_URL=sqlite:///data/iptv_proxy.db alembic stamp head
```

Then future upgrades use `flask db upgrade` normally. Leave the legacy `schema_migrations` table in place.

## Deletion policy

Do not delete until PostgreSQL production cutover (TODO 118) is verified. See TODO 119 for final cleanup.
