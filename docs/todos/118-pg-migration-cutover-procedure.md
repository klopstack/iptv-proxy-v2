# PostgreSQL cutover procedure and rollback plan

**Status:** ⬜ Open  
**Priority:** P1  
**Track:** Database Migration — Series B (Switchover)

## Problem

Switching from SQLite to PostgreSQL in production is a one-time event that requires a planned outage window. The cutover must be:

- **Safe**: original SQLite file backed up and preserved
- **Verified**: data integrity confirmed before traffic is restored
- **Reversible**: rollback procedure ready to execute within minutes if verification fails
- **Documented**: every step written as a runbook, not ad-hoc

Without a documented cutover procedure, there is a risk of data loss, extended downtime, or an inconsistent database state if the migration is interrupted.

## Current state

No cutover procedure exists. This document defines the planned procedure for review and approval before execution.

## Proposed cutover procedure

### Pre-cutover checklist (1–2 days before)

- [ ] All Series A TODOs (111–115) complete and merged to `main`
- [ ] All Series B TODOs 116 (data export tooling) and 117 (schema creation) complete and tested on a copy of production data
- [ ] `scripts/pg_migration_validate.py` passes against a recent production data snapshot
- [ ] `DATABASE_URL=postgresql://... pytest tests/ -m "not sqlite_only"` passes in CI
- [ ] PostgreSQL service is provisioned and reachable from the app host
- [ ] `psycopg2-binary` (or `psycopg2`) installed in the production Docker image
- [ ] Production SQLite `iptv_proxy.db` is less than 72 hours old (ensure low row-delta during migration window)
- [ ] Maintenance page or 503 response configured in Traefik (to block user traffic during window)

### Cutover runbook

**Step 0 — Communicate planned maintenance window**

Notify any users / dependent services. Target maintenance window: 30–60 minutes.

---

**Step 1 — Stop the application**

```bash
docker compose stop iptv-proxy-v2
```

Verify no processes hold the SQLite WAL:
```bash
lsof ./data/iptv_proxy.db 2>/dev/null | grep -v "^COMMAND"
# Expect: no output
```

---

**Step 2 — Checkpoint and back up the SQLite database**

```bash
# Checkpoint the WAL to merge any pending writes into the main DB file
sqlite3 ./data/iptv_proxy.db "PRAGMA wal_checkpoint(FULL);"

# Take a timestamped backup
cp ./data/iptv_proxy.db ./data/iptv_proxy_pre_pg_migration_$(date +%Y%m%d_%H%M%S).db

# Verify backup
sqlite3 ./data/iptv_proxy_pre_pg_migration_*.db "SELECT COUNT(*) FROM accounts;"
```

**Do not proceed if the backup is missing or the count is 0.**

---

**Step 3 — Create PostgreSQL database and apply schema**

```bash
# If PostgreSQL is running via Docker Compose
docker compose --profile postgres up -d postgres

# Wait for healthy
docker compose ps postgres  # status: healthy

# Apply Alembic schema
DATABASE_URL=postgresql://iptv:changeme@localhost/iptv_proxy docker compose run --rm iptv-proxy-v2 flask db upgrade

# Stamp alembic_version (schema applied fresh, not via old runner)
DATABASE_URL=postgresql://iptv:changeme@localhost/iptv_proxy alembic current
# Expect: <revision hash> (head)
```

---

**Step 4 — Run data migration (pgloader)**

```bash
# Edit pg_migrate.pgloader: set correct source path and destination credentials
pgloader scripts/pg_migrate.pgloader 2>&1 | tee /tmp/pgloader_$(date +%Y%m%d_%H%M%S).log

# Check exit code
echo "pgloader exit: $?"
# Expect: 0

# Check log for ERRORs
grep -i "error\|FATAL\|summary.*errors" /tmp/pgloader_*.log
```

Expect output like:
```
             table name     errors       read   imported      bytes
-----------------------  ---------  ---------  ---------  ---------
                accounts          0        ...        ...      ...
                channels          0        ...        ...      ...
              epg_programs        0        ...        ...      ...
```

**Do not proceed if any table shows errors > 0.**

---

**Step 5 — Validate data integrity**

```bash
python scripts/pg_migration_validate.py \
  --src sqlite:///./data/iptv_proxy.db \
  --dst postgresql://iptv:changeme@localhost/iptv_proxy \
  --full-check

# Expect: "All checks passed: N tables, N rows, N FK spot-checks"
```

---

**Step 6 — Update environment and restart application**

Edit the deployment environment to set the new `DATABASE_URL`:

```bash
# docker-compose.yml or .env
DATABASE_URL=postgresql://iptv:changeme@localhost/iptv_proxy

# Start the application pointing at PostgreSQL
docker compose up -d iptv-proxy-v2
```

---

**Step 7 — Post-restart smoke tests**

```bash
# Health check
curl -f http://localhost:8000/ -o /dev/null -w "%{http_code}"
# Expect: 200

# API smoke test
curl -s http://localhost:8000/api/accounts | python -m json.tool | head -20
# Expect: accounts list with correct data

# Dashboard load
curl -s http://localhost:8000/api/overview/stats | python -m json.tool
# Expect: correct counts matching production row counts

# Scheduler still running
curl -s http://localhost:8000/api/scheduler/status | python -m json.tool
# Expect: scheduler running

# Check for any 500 errors in logs
docker compose logs iptv-proxy-v2 --tail=100 | grep -i "error\|traceback\|exception"
```

---

**Step 8 — Restore traffic**

Remove maintenance page / 503 override from Traefik. Monitor error logs for 15 minutes.

---

### Rollback procedure

If Step 5 (validation) or Step 7 (smoke tests) fail:

**Step R1 — Stop the application**
```bash
docker compose stop iptv-proxy-v2
```

**Step R2 — Revert `DATABASE_URL`**
```bash
# Restore original environment (SQLite)
DATABASE_URL=sqlite:////app/data/iptv_proxy.db
```

**Step R3 — Verify SQLite file is intact**
```bash
sqlite3 ./data/iptv_proxy.db "PRAGMA integrity_check;"
# Expect: "ok"
sqlite3 ./data/iptv_proxy.db "SELECT COUNT(*) FROM accounts;"
# Expect: same count as pre-migration backup
```

If the SQLite file is intact, restart:
```bash
docker compose up -d iptv-proxy-v2
```

If the SQLite file was corrupted (should not happen — app was stopped before migration), restore from backup:
```bash
cp ./data/iptv_proxy_pre_pg_migration_*.db ./data/iptv_proxy.db
docker compose up -d iptv-proxy-v2
```

**Step R4 — Destroy partial PostgreSQL state**
```bash
# Drop and recreate the PG database to clean up
psql -h localhost -U postgres -c "DROP DATABASE iptv_proxy;"
psql -h localhost -U postgres -c "CREATE DATABASE iptv_proxy OWNER iptv;"
# (Can be left for later cleanup — does not affect SQLite-running app)
```

**Step R5 — Document failure**

Record which validation check failed, what the error was, and open a follow-up issue before rescheduling the cutover.

---

### Expected downtime

| Step | Estimated time |
|------|---------------|
| Step 1: Stop app | < 1 min |
| Step 2: Backup SQLite | 1–2 min |
| Step 3: PG schema creation | 2–5 min |
| Step 4: pgloader data migration | 5–20 min (depends on DB size) |
| Step 5: Validation | 2–5 min |
| Step 6: Restart with PG | 1–2 min |
| Step 7: Smoke tests | 5 min |
| **Total** | **~20–40 min** |

## Acceptance criteria

- [ ] Runbook reviewed and approved before execution
- [ ] Backup of SQLite file exists and is verified (non-zero row count) before any PG operations begin
- [ ] `pgloader` exits with code 0 and no table-level errors
- [ ] `pg_migration_validate.py` passes with `--full-check`
- [ ] Application serves real requests from PostgreSQL within the maintenance window
- [ ] Rollback procedure is tested in a staging environment before production cutover
- [ ] Post-cutover monitoring runs for at least 24 hours before declaring success

## Test plan

```bash
# Test the entire runbook in staging (with a copy of production data)
# 1. Copy production SQLite to staging host
# 2. Execute Steps 0–8 exactly
# 3. Verify smoke tests pass
# 4. Practice rollback: execute R1–R5
# 5. Re-run full runbook to confirm idempotency
```

## Affected files

- `docs/DEPLOYMENT.md` — embed or reference this runbook
- `scripts/pg_migrate.pgloader` — used in Step 4
- `scripts/pg_migration_validate.py` — used in Step 5
- `docker-compose.yml` — `DATABASE_URL` env var updated post-cutover

## Dependencies

- **Depends on** [TODO 116](./116-pg-migration-data-export-tooling.md) — pgloader script and validation script must exist.
- **Depends on** [TODO 117](./117-pg-migration-schema-creation.md) — PostgreSQL schema must be tested before cutover.
- **Enables** [TODO 119](./119-pg-migration-cleanup-and-removal.md) — cleanup begins only after successful cutover.

## Risks

- **Data written between Step 1 (stop) and Step 4 (pgloader start)**: Because the app is stopped before backup, there is no write-during-migration risk. The WAL checkpoint in Step 2 ensures the SQLite file is fully flushed.
- **Scheduler writes during migration**: The scheduler is part of the Flask app and stops when the app stops. Confirm `DISABLE_IN_WORKER_SCHEDULER=true` is not set to a value that leaves a stale scheduler process running. Use `pgrep -a python` to verify no app processes remain after `docker compose stop`.
- **pgloader boolean cast mistakes**: See TODO 116 risk section. Test explicitly that `is_active`, `is_visible`, `enabled`, `is_new`, `is_live`, etc. are migrated as PostgreSQL `true`/`false`, not `1`/`0`.
- **Sequence collision on first insert**: If pgloader's `reset sequences` clause is omitted or fails, the first ORM INSERT after cutover will generate a PK that collides with an existing row. The validation script must check max(id) vs sequence current value for every table with an auto-increment PK.
- **Traefik auth during maintenance**: The maintenance 503 must be applied **before** stopping the app (Step 0, not Step 1). If traffic reaches the stopped app, Docker will return a connection refused, which may confuse users more than a 503 maintenance page.
