# PostgreSQL migration guide

Operator guide for moving IPTV Proxy v2 from SQLite to PostgreSQL. Part of **Wave 11** (TODOs 111–119); see [ROADMAP-active.md](../todos/ROADMAP-active.md#wave-11--postgresql-migration-track).

## Overview

**Goal:** Replace the default SQLite file (`/app/data/iptv_proxy.db`) with PostgreSQL as the production database backend.

| Series | TODOs | Scope | Status (June 2026) |
|--------|-------|-------|---------------------|
| **A — Preparation** | 111–115 | SQLite-safe prep: remove raw sqlite3, JSON columns, Alembic, CI/Docker PG | #65–#67, PG-A3 merged |
| **B — Switchover** | 116–119 | PG schema, data export/import, cutover, cleanup | Blocked on Series A |

Series A keeps existing SQLite deployments working. Series B moves production data and flips `DATABASE_URL` to PostgreSQL.

**Prerequisite:** Merge [PR #67 — Alembic migration system (TODO 113)](https://github.com/klopstack/iptv-proxy-v2/pull/67) before following stamp/upgrade steps below. Until then, containers still use `run_migrations.py` on startup (see [entrypoint.sh](../../entrypoint.sh) on `main`).

## Current state

### After PR #67 (Alembic)

| Component | Location | Notes |
|-----------|----------|-------|
| Alembic + Flask-Migrate | `alembic_migrations/` | Baseline revision `40ca71c79446` from current SQLAlchemy models (~35 tables) |
| Alembic config | `alembic.ini`, `alembic_migrations/env.py` | Reads `DATABASE_URL`; batch mode for SQLite |
| Container startup | `entrypoint.sh` | Runs `flask db upgrade` (replaces `create_all` + `run_migrations.py`) |
| Legacy runner | `migrations/legacy_sqlite/` | Archived sqlite3 migrations + `run_migrations.py`; inert, kept for forensic reference |
| Tracking table | `alembic_version` (PG/SQLite) | Replaces `schema_migrations` for new deployments |

Merged Wave 11 prep (already on `main`):

- [#65](https://github.com/klopstack/iptv-proxy-v2/pull/65) — remove raw sqlite3 from FCC pattern reset (TODO 111)
- [#66](https://github.com/klopstack/iptv-proxy-v2/pull/66) — EPG JSON columns use `db.JSON` (TODO 112)

Open / upcoming:

- Series B (TODOs 116–119) — schema parity, data export, cutover, cleanup

## Existing SQLite deployments

For production databases already fully migrated by the **legacy** `run_migrations.py` system (rows in `schema_migrations`, empty or missing `alembic_version`):

**Symptom:** First boot on an Alembic image fails with errors like `table accounts already exists` — the baseline migration tried to recreate tables that legacy migrations already applied. **Fix:** stamp before upgrade (see below).

### 1. Backup

```bash
# On the host — adjust path to your data volume
DATA_DIR="${FOLDER_FOR_DATA}/iptv-proxy-v2"   # klopstack default
cp -a "${DATA_DIR}/iptv_proxy.db" "${DATA_DIR}/iptv_proxy.db.bak.$(date +%Y%m%d)"
```

Optional integrity check:

```bash
sqlite3 "${DATA_DIR}/iptv_proxy.db" "PRAGMA integrity_check;"
```

### 2. Stamp Alembic (before first boot on Alembic image)

**Stop** the `iptv-proxy-v2` container, then stamp the existing schema at head **without running DDL**.

Use **`flask db stamp head`**, not bare `alembic stamp head` — Alembic needs Flask app context (`alembic_migrations/env.py` imports the app). A one-off `docker run … alembic stamp head` also fails because the default entrypoint runs `flask db upgrade` first (permission errors on the data volume, or DDL conflicts on legacy DBs).

**Preferred** (when the container can start and is not in a crash loop):

```bash
docker exec iptv-proxy-v2 flask db stamp head
```

If the container cannot stay up (e.g. crash loop from missing stamp), use a one-off container with the entrypoint overridden (verified on staging, docker.klopnet.com, June 2026):

```bash
docker stop iptv-proxy-v2
cp -a "${DATA_DIR}/iptv_proxy.db" "${DATA_DIR}/iptv_proxy.db.bak.$(date +%Y%m%d%H%M%S)"

docker run --rm --user 33:33 \
  --entrypoint flask \
  -v "${DATA_DIR}:/app/data" \
  -e DATABASE_URL=sqlite:////app/data/iptv_proxy.db \
  -e FLASK_APP=app.py \
  -w /app \
  ghcr.io/klopstack/iptv-proxy-v2:latest \
  db stamp head

docker start iptv-proxy-v2
```

Adjust `--user 33:33` if your data volume is owned by a different UID/GID (match `docker inspect iptv-proxy-v2 --format '{{.Config.User}}'` or the host owner of `${DATA_DIR}`).

From the host with a local checkout/venv:

```bash
DATABASE_URL="sqlite:///${DATA_DIR}/iptv_proxy.db" FLASK_APP=app.py flask db stamp head
```

### 3. Deploy new image

Pull the image that includes PR #67 and restart. The entrypoint runs `flask db upgrade`, which applies only **new** revisions after the stamped baseline.

### 4. Keep the data volume

Continue mounting `${FOLDER_FOR_DATA}/iptv-proxy-v2:/app/data` even when using PostgreSQL later — the SQLite file remains the rollback backup and is used for export tooling (TODO 116).

**Do not** run `flask db upgrade` on a fully-migrated legacy database **without** stamping first — the baseline migration would attempt to recreate existing tables.

## Fresh PostgreSQL deployments

For a new install with no existing SQLite data:

### 1. Provision database

On **klopstack** (shared `postgresql` service), run once:

```bash
./create_iptv_proxy_database.sh
```

See [klopstack / docker.klopnet.com](#klopstack--dockerklopnetcom) below.

### 2. Set `DATABASE_URL`

```bash
DATABASE_URL=postgresql://USER:PASSWORD@postgresql:5432/iptv_proxy
```

In klopstack, set `IPTV_PROXY_USE_POSTGRES=true` and `IPTV_PROXY_DATABASE_URL` in `.env` (see klopstack README).

### 3. Start container

The entrypoint runs:

```bash
flask db upgrade
```

This creates all tables on the empty PostgreSQL database. Verify:

```bash
docker exec -it iptv-proxy-v2 alembic current   # should show head revision
docker exec -it iptv-proxy-v2 python -c "import requests; print(requests.get('http://localhost:8000/api/accounts', timeout=5).status_code)"
```

## SQLite → PostgreSQL data migration

**Full data cutover is not automated yet.** See [TODO 116 — data export/import tooling](../todos/116-pg-migration-data-export-tooling.md) and [TODO 118 — cutover procedure](../todos/118-pg-migration-cutover-procedure.md).

### Interim options (until TODO 116 lands)

| Approach | When to use | Data |
|----------|-------------|------|
| **Stamp + new empty PG** | Testing PG schema/app paths; parallel non-prod stack | Empty — reconfigure accounts manually |
| **Stay on SQLite** | Production until export tooling is ready | Unchanged |
| **Future cutover** | After TODO 116 + 118 | pgloader or SQLAlchemy dump/load from `.db` backup |

Recommended interim path for klopstack operators:

1. Keep production on SQLite (`IPTV_PROXY_USE_POSTGRES=false`).
2. Create PG database with `create_iptv_proxy_database.sh`.
3. On a staging container, set `DATABASE_URL` to PostgreSQL, run `flask db upgrade`, smoke-test admin API.
4. When TODO 116 tooling exists, export from backed-up `iptv_proxy.db`, import into PG, then flip `IPTV_PROXY_USE_POSTGRES=true`.

Schema creation details: [TODO 117](../todos/117-pg-migration-schema-creation.md).

## klopstack / docker.klopnet.com

Production IPTV Proxy v2 runs in the **[klopstack](https://github.com/klopstack/klopstack)** MediaStack (`docker.klopnet.com` reference deployment).

| Item | Location |
|------|----------|
| Compose service | `iptvproxy` (`container_name: iptv-proxy-v2`) |
| SQLite data volume | `${FOLDER_FOR_DATA}/iptv-proxy-v2:/app/data` |
| Shared PostgreSQL | `postgresql` service (Authentik, Guacamole, IPTV Proxy) |
| DB bootstrap script | `create_iptv_proxy_database.sh` |
| Env vars | `IPTV_PROXY_DATABASE`, `IPTV_PROXY_DATABASE_URL`, `IPTV_PROXY_USE_POSTGRES` |

Operator steps in klopstack README (PostgreSQL section). Stack wiring does **not** enable PostgreSQL by default — SQLite remains the default until you opt in.

App deployment docs: [DEPLOYMENT.md](../DEPLOYMENT.md).

## Rollback

To revert from PostgreSQL to SQLite:

1. **Stop** the container.
2. **Unset** PostgreSQL env vars (or set `IPTV_PROXY_USE_POSTGRES=false` in klopstack).
3. **Restore** the SQLite backup if the `.db` file was removed or corrupted:

   ```bash
   cp -a "${DATA_DIR}/iptv_proxy.db.bak.YYYYMMDD" "${DATA_DIR}/iptv_proxy.db"
   ```

4. **Restart** without `DATABASE_URL` (or with `DATABASE_URL=sqlite:////app/data/iptv_proxy.db`).

5. If you stamped Alembic on SQLite before trying PG, the stamped SQLite DB remains valid — no restamp needed unless you ran new Alembic revisions on PG only.

**Note:** Changes made only on PostgreSQL after cutover are **not** synced back to SQLite automatically.

## Operator checklist

### Pre-deploy (SQLite → Alembic image, PR #67)

- [ ] Confirm PR #67 is merged and a new `ghcr.io/klopstack/iptv-proxy-v2` image is published
- [ ] Backup `iptv_proxy.db` (copy + optional `PRAGMA integrity_check`)
- [ ] Stop `iptv-proxy-v2` container
- [ ] Run `flask db stamp head` against the SQLite file (see above)
- [ ] Pull new image and restart
- [ ] Verify `docker logs iptv-proxy-v2` shows successful `flask db upgrade`
- [ ] Smoke-test admin UI and `/api/accounts`

### Pre-deploy (enable PostgreSQL on klopstack)

- [ ] PR #67 merged; image includes Alembic entrypoint
- [ ] `./create_iptv_proxy_database.sh` completed successfully
- [ ] Set in `.env`: `IPTV_PROXY_DATABASE`, `IPTV_PROXY_DATABASE_URL`, `IPTV_PROXY_USE_POSTGRES=true`
- [ ] Backup SQLite `.db` before any data migration
- [ ] Run data export/import when TODO 116 tooling is available (skip for empty PG test)

### Post-deploy

- [ ] `docker exec iptv-proxy-v2 alembic current` shows expected revision
- [ ] Admin dashboard loads via Traefik + Authentik
- [ ] Client paths (`/player_api.php`, `/playlist/…`) still work without Authentik
- [ ] Scheduler heartbeat resets on boot (check logs for sync activity)
- [ ] Keep SQLite backup until PG cutover is verified stable (7+ days recommended)

### Manual migration commands

```bash
docker exec -it iptv-proxy-v2 flask db upgrade
docker exec -it iptv-proxy-v2 flask db stamp head   # legacy SQLite only — see stamp section above
docker exec -it iptv-proxy-v2 alembic current
docker exec -it iptv-proxy-v2 flask db downgrade   # use with caution
```

## Related documentation

- [DEPLOYMENT.md](../DEPLOYMENT.md) — Traefik, Authentik, container env (Alembic section added in PR #67)
- [DEVELOPER_GUIDE.md](../DEVELOPER_GUIDE.md) — local dev, Alembic commands (updated in PR #67)
- [TODO 113 — Alembic migration system](../todos/113-pg-prep-alembic-migration-system.md)
- [TODO 115 — CI/Docker PG config](../todos/115-pg-prep-ci-docker-config.md)
- [TODO 116 — data export tooling](../todos/116-pg-migration-data-export-tooling.md)
- [TODO 117 — schema creation](../todos/117-pg-migration-schema-creation.md)
- [TODO 118 — cutover procedure](../todos/118-pg-migration-cutover-procedure.md)
- [pg-sqlite3-audit.md](./pg-sqlite3-audit.md) — raw sqlite3 inventory
