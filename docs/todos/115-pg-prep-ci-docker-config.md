# PostgreSQL in CI, Docker Compose service, and DATABASE_URL config abstraction

**Status:** ⬜ Open  
**Priority:** P2  
**Track:** Database Migration — Series A (Preparation)

## Problem

Three infrastructure gaps must be closed before the PostgreSQL cutover can be validated or executed:

1. **CI has no PostgreSQL test target.** The `build.yml` workflow runs the test suite exclusively against SQLite (`os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"`). Any PostgreSQL incompatibility in services, models, or routes will only be discovered after the cutover — too late.

2. **`docker-compose.yml` has no PostgreSQL service.** The `./data:/app/data` volume mount is the only persistence strategy. There is no PostgreSQL container definition, no environment variable wiring for a PG connection, and no health-check pattern for a DB dependency.

3. **`app.py` `SQLALCHEMY_ENGINE_OPTIONS` is SQLite-specific.** The `connect_args` dict contains `timeout`, `check_same_thread`, and `isolation_level` — all SQLite connection arguments that PostgreSQL (`psycopg2`) does not accept. If `DATABASE_URL` is switched to PostgreSQL without changing this block, SQLAlchemy will pass these kwargs to psycopg2 and raise `TypeError`.

## Current state

### CI (`build.yml`)

The test job runs `pytest` without a `services:` block (no PostgreSQL container). The only database interaction is through the `conftest.py`-injected SQLite URL.

```yaml
# Current: no services block, SQLite only
- name: Run tests
  run: make test
```

### Docker Compose (`docker-compose.yml`)

```yaml
services:
  iptv-proxy-v2:
    volumes:
      - ./data:/app/data  # SQLite .db file lives here
    environment:
      DATABASE_URL: not set  # app defaults to sqlite:////app/data/iptv_proxy.db
```

No `postgres` service, no `DATABASE_URL` injection.

### `app.py` engine options

```python
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "connect_args": {
        "timeout": 60,               # SQLite: wait for write lock
        "check_same_thread": False,  # SQLite: allow cross-thread use
        "isolation_level": None,     # SQLite: autocommit mode
    },
    "pool_pre_ping": True,
}

# Conditional PRAGMA block
if "sqlite" in app.config["SQLALCHEMY_DATABASE_URI"]:
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        ...
```

The `if "sqlite" in ...` gate protects the PRAGMA listener, but `connect_args` is always applied regardless of dialect.

## Proposed solution

### 1 — Fix `app.py` engine options to be dialect-aware

Replace the static `connect_args` dict with dialect-branched logic:

```python
db_url = os.getenv("DATABASE_URL", "sqlite:////app/data/iptv_proxy.db")
app.config["SQLALCHEMY_DATABASE_URI"] = db_url

if db_url.startswith("sqlite"):
    engine_options = {
        "connect_args": {
            "timeout": 60,
            "check_same_thread": False,
            "isolation_level": None,
        },
        "pool_pre_ping": True,
    }
else:
    # PostgreSQL / any other dialect — no SQLite-specific kwargs
    engine_options = {
        "pool_pre_ping": True,
        "pool_size": int(os.getenv("DB_POOL_SIZE", "5")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "10")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "30")),
    }

app.config["SQLALCHEMY_ENGINE_OPTIONS"] = engine_options
```

`pool_size` and `max_overflow` are ignored by SQLAlchemy for SQLite (it uses `StaticPool` or `NullPool` for file-based DBs) but are meaningful for PostgreSQL connection pooling.

### 2 — Add PostgreSQL service to `docker-compose.yml`

Define an optional `postgres` service that the main app can depend on:

```yaml
services:
  iptv-proxy-v2:
    environment:
      DATABASE_URL: "${DATABASE_URL:-sqlite:////app/data/iptv_proxy.db}"
    volumes:
      - ./data:/app/data   # kept for SQLite fallback
    depends_on:
      postgres:
        condition: service_healthy
        required: false    # optional — only active when POSTGRES_ENABLED=true or profile

  postgres:
    image: postgres:16-alpine
    container_name: iptv-proxy-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: "${POSTGRES_DB:-iptv_proxy}"
      POSTGRES_USER: "${POSTGRES_USER:-iptv}"
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD:-changeme}"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-iptv} -d ${POSTGRES_DB:-iptv_proxy}"]
      interval: 10s
      timeout: 5s
      retries: 5
    profiles:
      - postgres    # opt-in via: docker compose --profile postgres up

volumes:
  postgres_data:
```

The `profiles: [postgres]` approach means the PostgreSQL service is **opt-in** — existing SQLite deployments are unaffected unless they explicitly pass `--profile postgres`.

### 3 — Add `psycopg2-binary` to `requirements.txt`

PostgreSQL requires `psycopg2` (or `psycopg2-binary` for convenience). Add to `requirements.txt` and pin a known-working version. Consider using `psycopg2-binary` for development/CI and `psycopg2` (compiled) for production Docker images.

Also add a `[postgresql]` extras or a `requirements-postgres.txt` to keep the SQLite-only footprint minimal for deployments that do not need PostgreSQL.

### 4 — Add PostgreSQL CI job to `build.yml`

Add a new job (or test matrix entry) that:
1. Spins up `postgres:16` as a service container.
2. Creates a test database.
3. Runs `alembic upgrade head` (from TODO 113) to create the schema.
4. Runs `pytest tests/ -m "not sqlite_only"` with `DATABASE_URL=postgresql://...`.

```yaml
test-postgres:
  runs-on: ubuntu-latest
  needs: [lint-py]

  services:
    postgres:
      image: postgres:16-alpine
      env:
        POSTGRES_DB: iptv_test
        POSTGRES_USER: iptv
        POSTGRES_PASSWORD: iptv
      ports:
        - 5432:5432
      options: >-
        --health-cmd pg_isready
        --health-interval 10s
        --health-timeout 5s
        --health-retries 5

  env:
    DATABASE_URL: postgresql://iptv:iptv@localhost:5432/iptv_test

  steps:
    - uses: actions/checkout@v4
    - uses: actions/setup-python@v5
      with:
        python-version: "3.11"
        cache: pip
    - name: Install deps
      run: pip install -r requirements.txt psycopg2-binary
    - name: Apply Alembic migrations
      run: flask db upgrade
    - name: Run tests (non-SQLite)
      run: pytest tests/ -m "not sqlite_only" -x -v
```

The existing SQLite test job remains unchanged (no regression risk).

### 5 — Document `DATABASE_URL` in `.env.example` and `DEPLOYMENT.md`

Add an `.env.example` file (if not present) with both SQLite and PostgreSQL variants:

```dotenv
# SQLite (default)
DATABASE_URL=sqlite:////app/data/iptv_proxy.db

# PostgreSQL
# DATABASE_URL=postgresql://iptv:changeme@localhost:5432/iptv_proxy
```

Update `DEPLOYMENT.md` with:
- PostgreSQL Docker Compose profile instructions
- `DATABASE_URL` format documentation
- Pool sizing env vars (`DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`)
- How to run Alembic migrations in production (`flask db upgrade` or `alembic upgrade head`)

## Acceptance criteria

- [ ] `app.py` `SQLALCHEMY_ENGINE_OPTIONS` is dialect-branched; starting with a PostgreSQL `DATABASE_URL` raises no `TypeError` on import or first request
- [ ] `docker-compose.yml` has a `postgres` service under the `postgres` profile; `docker compose --profile postgres up` starts both app and PostgreSQL
- [ ] `psycopg2-binary` is in `requirements.txt` (or `requirements-postgres.txt`)
- [ ] `.env.example` documents both SQLite and PostgreSQL `DATABASE_URL` formats
- [ ] CI `build.yml` has a `test-postgres` job that runs against PostgreSQL 16 and passes `pytest -m "not sqlite_only"`
- [ ] `DEPLOYMENT.md` updated with PostgreSQL setup instructions

## Test plan

```bash
# Verify app starts with PG URL (requires local PG or Docker)
DATABASE_URL=postgresql://iptv:iptv@localhost/iptv_test python -c "import app; print('OK')"

# Docker Compose PostgreSQL profile
docker compose --profile postgres up --build -d
curl http://localhost:8000/ -o /dev/null -w "%{http_code}"  # expect 200 or 302

# CI simulation
act -j test-postgres  # using `act` locally if available
```

## Affected files

- `app.py` — dialect-branched `SQLALCHEMY_ENGINE_OPTIONS`
- `docker-compose.yml` — `postgres` service under `postgres` profile; `DATABASE_URL` env var on app service; `postgres_data` volume
- `requirements.txt` — add `psycopg2-binary` (or `requirements-postgres.txt`)
- `.github/workflows/build.yml` — add `test-postgres` job
- `.env.example` — new file with DATABASE_URL variants
- `DEPLOYMENT.md` — PostgreSQL setup, pool env vars, Alembic commands
- `DEVELOPER_GUIDE.md` — local PostgreSQL testing with Docker

## Dependencies

- **Depends on** [TODO 113](./113-pg-prep-alembic-migration-system.md) (Alembic required for `flask db upgrade` in CI job).
- **Depends on** [TODO 114](./114-pg-prep-test-db-hardening.md) (injectable `DATABASE_URL` in conftest, `sqlite_only` markers).
- This is the final Series A item — once complete, all Series B migration work can begin.

## Risks

- **`isolation_level=None` (autocommit) on SQLite**: The current SQLite config uses connection-level autocommit (`isolation_level=None` in `connect_args`). SQLAlchemy's default transaction management (begin/commit/rollback) is bypassed on SQLite as a result. On PostgreSQL, this is incorrect — standard transaction management must be used. The dialect-branch in step 1 stops passing `isolation_level=None` to PostgreSQL connections, which is the correct behavior. **Verify that removing autocommit does not break background scheduler writes on SQLite** — the scheduler concurrency workaround may have been relying on autocommit.
- **`network_mode: host` and PostgreSQL**: `docker-compose.yml` uses `network_mode: host` for the app and MediaFlow. Adding a standard bridge-network `postgres` service requires the app to reach it. On Linux host-network mode, `localhost:5432` on the host is reachable from within the app container. Verify this with `pg_isready` from inside the container.
- **CI service container port binding**: GitHub Actions service containers on `ubuntu-latest` bind to `localhost`; the app job can connect via `localhost:5432`. This is standard and well-documented but worth noting in the CI job comments.
