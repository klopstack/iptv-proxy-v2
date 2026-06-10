# Deployment

Production deployments of IPTV Proxy v2 in this project’s stack use **Traefik** as the reverse proxy and **Authentik** for admin authentication. The Flask app does not implement login (`POST /login` does not exist).

Canonical wiring lives in the sibling **[klopstack](https://github.com/klopstack/klopstack)** repository (`../klopstack` relative to this repo). This document summarizes how that stack protects IPTV Proxy v2.

## Authentication model

| Traffic | Host (example) | Traefik | App-level auth |
|---------|----------------|---------|----------------|
| **Admin** — web UI, `/api/*` | `iptv.${CLOUDFLARE_DNS_ZONE}` | `authentik-forwardauth@file` | None (proxy only) |
| **Client** — playlists, EPG, streams, Xtream | `iptv.${CLOUDFLARE_DNS_ZONE}` | Public router (higher priority), no forward-auth | Xtream username/password on client paths |
| **Authentik UI** | `auth.${CLOUDFLARE_DNS_ZONE}` | `security-headers@file` only — **no** forward-auth | Authentik’s own login |

Replace `${CLOUDFLARE_DNS_ZONE}` with your registered domain (e.g. `stonecrusher.us` in the reference stack).

## Authentik forward-auth middleware

Defined in klopstack `traefik-dynamic.yaml` (file provider mounted at `/etc/traefik`):

```yaml
http:
  middlewares:
    authentik-forwardauth:
      forwardAuth:
        address: http://authentik:9000/outpost.goauthentik.io/auth/traefik
        trustForwardHeader: true
        authResponseHeaders:
          - X-authentik-username
          - X-authentik-groups
          - X-authentik-email
          - X-authentik-name
          - X-authentik-uid
          - X-authentik-jwt
          - X-authentik-meta-jwks
          - X-authentik-meta-outpost
          - X-authentik-meta-provider
          - X-authentik-meta-app
          - X-authentik-meta-version
```

Requirements:

- Traefik and Authentik on the same Docker network (`mediastack` in klopstack).
- An Authentik **Traefik forward-auth outpost** configured for application URLs under `https://iptv.${CLOUDFLARE_DNS_ZONE}/`.
- Do **not** attach `authentik-forwardauth` to the Authentik router itself (see comment on `authentik` service labels in klopstack `docker-compose.yaml`).

## IPTV Proxy v2 — Traefik Docker labels

From klopstack `docker-compose.yaml` service `iptvproxy` (`container_name: iptv-proxy-v2`). Two routers share one backend service on port **8000**:

### 1. Client router (public, priority 100)

No Authentik. Matches **only** these path prefixes on `iptv.${CLOUDFLARE_DNS_ZONE}`:

```yaml
traefik.http.routers.iptv-streams.rule: >-
  Host(`iptv.${CLOUDFLARE_DNS_ZONE}`) && (
    PathPrefix(`/playlist`) ||
    PathPrefix(`/epg`) ||
    PathPrefix(`/stream`) ||
    PathPrefix(`/image`) ||
    PathPrefix(`/icon`) ||
    PathPrefix(`/player_api.php`) ||
    PathPrefix(`/xmltv.php`) ||
    PathPrefix(`/ppv-epg`) ||
    PathPrefix(`/live/`) ||
    PathPrefix(`/movie/`) ||
    PathPrefix(`/series/`)
  )
traefik.http.routers.iptv-streams.entrypoints: secureweb
traefik.http.routers.iptv-streams.tls.certResolver: letsencrypt
traefik.http.routers.iptv-streams.middlewares: security-headers@file
traefik.http.routers.iptv-streams.priority: "100"
```

**Typical client paths in iptv-proxy-v2:**

| Prefix | Purpose |
|--------|---------|
| `/playlist/` | M3U playlists (`/playlist/<account_id>.m3u`, `/playlist/config/<slug>.m3u`) |
| `/epg/` | Account/config XMLTV EPG |
| `/stream/` | Stream proxy (HLS/MPEG-TS) |
| `/image/`, `/icon/` | Channel icons |
| `/player_api.php` | Xtream Codes API |
| `/xmltv.php` | Xtream-style XMLTV (if enabled) |
| `/live/`, `/movie/`, `/series/` | Xtream stream URLs |
| `/ppv-epg` | Reserved in stack for PPV XMLTV-style URLs (admin API is under `/api/ppv-epg`) |

Client routes use **provisioned Xtream credentials** (or playlist/EPG URL tokens), not Authentik.

### 2. Admin router (Authentik, priority 1)

Catch-all on the same host for everything **not** matched by the higher-priority client router:

```yaml
traefik.http.routers.iptv-proxy-v2.rule: Host(`iptv.${CLOUDFLARE_DNS_ZONE}`)
traefik.http.routers.iptv-proxy-v2.entrypoints: secureweb
traefik.http.routers.iptv-proxy-v2.middlewares: authentik-forwardauth@file,security-headers@file
traefik.http.routers.iptv-proxy-v2.priority: "1"
```

**Protected by Authentik (examples):**

- `/` — admin HTML pages (`/settings`, `/accounts`, `/ppv`, …)
- `/api/*` — REST management (accounts, EPG config, PPV enrichment, scheduler, …)

### Backend service

```yaml
traefik.http.services.iptv-proxy-v2.loadbalancer.server.scheme: http
traefik.http.services.iptv-proxy-v2.loadbalancer.server.port: "8000"
```

## Gluetun and port `8889` (often misunderstood)

klopstack lists **`8889:8000`** under the **gluetun** service with a comment “IPTV Proxy v2”. That pattern is used for apps that run with `network_mode: service:gluetun` (e.g. qBittorrent, SABnzbd): the app listens inside Gluetun’s network namespace, and the host port forwards to it.

**In the current `iptvproxy` service definition, IPTV Proxy v2 does not use `network_mode: service:gluetun`.** It joins the `mediastack` Docker network like Traefik and is reached at `iptv-proxy-v2:8000` for routing. Admin UI traffic normally goes **Traefik → Authentik → app**, not through the Gluetun port map.

So:

| Question | Answer |
|----------|--------|
| Is the unauthenticated UI exposed **to remote Gluetun VPN users**? | **Not by default.** `8889:8000` is a **Docker host** port publish, not “inside the VPN” for clients. Remote VPN peers do not automatically get access to host port 8889 unless you separately forward/firewall for that. |
| Does `8889` bypass Authentik today? | **Usually no** — with the current compose file, nothing in the Gluetun namespace is listening on 8000 for iptv-proxy, so `http://host:8889/` may not even reach the app (connection refused or wrong process). |
| What is Gluetun for here? | VPN egress for **other** stack services that share its network; Gluetun also exposes an HTTP proxy on **8888** (`HTTPPROXY=on`). `iptvproxy` only `depends_on` Gluetun for startup ordering; outbound provider traffic from the app container uses normal Docker routing unless you add proxy env vars. |

If you **did** switch iptv-proxy to `network_mode: service:gluetun` (to force provider API/stream egress through the VPN), then `8889:8000` would expose the **full** Flask app on the host **without** Traefik/Authentik — including unauthenticated admin UI. That would be a deliberate tradeoff; prefer keeping the app on `mediastack` and routing admin traffic only through Traefik.

Prefer admin access via `https://iptv.${CLOUDFLARE_DNS_ZONE}/` through Traefik.

## Container environment (klopstack reference)

```yaml
environment:
  - GUNICORN_WORKERS=10
  - PORT=8000
  - DEBUG=False
  - STREAM_BACKEND=mediaflow
  - MEDIAFLOW_PROXY_URL=http://mediaflow-proxy:8888
  - MEDIAFLOW_API_PASSWORD=${MEDIAFLOW_API_PASSWORD}
volumes:
  - ${FOLDER_FOR_DATA}/iptv-proxy-v2:/app/data
networks:
  - mediastack
```

VPN egress: `iptvproxy` runs behind **gluetun** (`depends_on: gluetun`) so upstream IPTV provider traffic uses the VPN tunnel.

## TLS and entrypoints

Traefik static config (`traefik-static.yaml` in klopstack):

- Entrypoint `secureweb` on `:443` with Let’s Encrypt (DNS challenge via Cloudflare).
- HTTP `:80` redirects to HTTPS.

## Operator checklist

1. Deploy Traefik + Authentik from klopstack (or equivalent labels/middleware).
2. Create Authentik application for `https://iptv.${CLOUDFLARE_DNS_ZONE}/` with Traefik forward-auth outpost.
3. Confirm client paths (e.g. `/player_api.php`) work **without** Authentik session cookies.
4. Confirm `/api/accounts` (or `/settings`) redirects to Authentik when unauthenticated.
5. Restrict or firewall host port `8000` when using `network_mode: host` without Traefik.
6. Set a non-default `MEDIAFLOW_API_PASSWORD` in production when using the mediaflow backend.
7. For automated PPV team-location registry updates, configure GitHub repository secret `THESPORTSDB_API_KEY` (premium V2 key). The weekly [build-team-locations workflow](https://github.com/klopstack/iptv-proxy-v2/blob/main/.github/workflows/build-team-locations.yml) needs `contents: write` on the default branch; WNBA coverage requires the premium key.

**Note:** This app does not use Flask session cookies or `SECRET_KEY`. Admin auth is Traefik + Authentik only (see [architecture/admin-auth-and-deployment-security.md](architecture/admin-auth-and-deployment-security.md)).

## High-privilege admin APIs

These routes are behind Traefik + Authentik but can still cause outages or data loss if misused. Restrict Authentik application access to trusted operators.

| Endpoint | Risk | Notes |
|----------|------|-------|
| `POST /api/config/import` | Overwrites rules, filters, FCC patterns, accounts | Validates bundle schema before apply; use `overwrite` carefully |
| `GET /api/config/export` | Full configuration exfiltration | Includes account server URLs when `include_accounts=true` |
| `POST /api/scheduler/stop` | Stops background sync | Pair with `start`/`restart` |
| `POST /api/scheduler/restart` | Brief sync outage | Restarts APScheduler |
| `POST /api/cache/clear` | Clears in-memory IPTV caches | Forces upstream refetch on next sync |
| `POST /api/fcc/facilities/sync` | Long-running FCC download | Canonical FCC facility sync path |

**Not available over HTTP:**

| Operation | How to run |
|-----------|------------|
| Reset FCC match patterns to factory defaults | `flask reset-fcc-patterns` (or `python scripts/reset_fcc_match_patterns.py`) |

**Removed for security:** `POST /api/fcc-match-patterns/reset-defaults` (DROP TABLE), `POST /icon/fetch` (SSRF). Icons are prefetched during provider/EPG sync only.

## Admin CDN assets (Subresource Integrity)

The admin UI loads Bootstrap and Bootstrap Icons from jsDelivr in `templates/base.html`. Each external `<link>` / `<script>` uses a pinned version URL plus `integrity` (sha384) and `crossorigin="anonymous"` so a compromised CDN cannot silently replace admin JavaScript.

Current pinned versions:

| Asset | URL path |
|-------|----------|
| Bootstrap CSS | `bootstrap@5.3.0/dist/css/bootstrap.min.css` |
| Bootstrap Icons CSS | `bootstrap-icons@1.11.0/font/bootstrap-icons.css` |
| Bootstrap JS bundle | `bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js` |

### Bumping CDN versions

1. Update the version segment in each URL in `templates/base.html`.
2. Download each file and compute a new sha384 hash:

   ```bash
   curl -fsSL 'https://cdn.jsdelivr.net/npm/<package>@<version>/<path>' \
     | openssl dgst -sha384 -binary | openssl base64 -A
   ```

3. Replace the `integrity="sha384-…"` value on the matching tag and keep `crossorigin="anonymous"`.
4. Load an admin page (e.g. `/settings`) and confirm the browser console shows no SRI failures.
5. Run `pytest tests/test_cdn_sri.py -q`.

Alternatively vendor the files under `static/vendor/` and serve them locally (no SRI required for same-origin assets).

## Database migrations

Schema is managed by **Alembic** (via Flask-Migrate). On container start, [`entrypoint.sh`](../entrypoint.sh) runs `flask db upgrade`.

### Fresh install

No action required — the entrypoint applies the baseline migration automatically.

### Upgrading from the legacy SQLite runner

If your production database was migrated by the old `run_migrations.py` system (has a `schema_migrations` table with applied rows, empty `alembic_version`), **stamp** Alembic before deploying this version. Without a stamp, the first boot fails with errors like `table accounts already exists`.

Use **`flask db stamp head`** (not bare `alembic stamp head` — needs Flask app context). If the container is running:

```bash
docker exec iptv-proxy-v2 flask db stamp head
```

If the container is stopped or crash-looping, see the one-off `docker run --entrypoint flask … db stamp head` procedure in [architecture/pg-migration-guide.md](architecture/pg-migration-guide.md#2-stamp-alembic-before-first-boot-on-alembic-image).

Do **not** run `flask db upgrade` on a fully-migrated legacy database without stamping first — the baseline migration would attempt to recreate existing tables.

### Manual migration commands

```bash
# Apply pending revisions
docker exec -it iptv-proxy-v2 flask db upgrade

# Roll back one revision (use with caution in production)
docker exec -it iptv-proxy-v2 flask db downgrade

# Check current revision
docker exec -it iptv-proxy-v2 alembic current
```

Set `DATABASE_URL` when running Alembic on the host outside Docker (default in container: `sqlite:////app/data/iptv_proxy.db`).

### PostgreSQL (optional)

Production default remains SQLite until Wave 11 Series B cutover. To run against PostgreSQL locally or on klopstack:

1. Provision a database (klopstack: `./create_iptv_proxy_database.sh`; local: `docker compose --profile postgres up -d postgres`).
2. Set `DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DBNAME` (klopstack: `IPTV_PROXY_DATABASE_URL` + `IPTV_PROXY_USE_POSTGRES=true`).
3. Start the app — `entrypoint.sh` runs `flask db upgrade` on the empty PostgreSQL database.

Local Docker Compose with the bundled PostgreSQL profile:

```bash
export DATABASE_URL=postgresql://iptv:changeme@localhost:5432/iptv_proxy
docker compose --profile postgres up --build -d
docker exec iptv-proxy-v2 alembic current
```

Connection pool sizing (PostgreSQL only): `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`.

Full operator steps: [architecture/pg-migration-guide.md](architecture/pg-migration-guide.md).

## Related documentation

- [architecture/admin-auth-and-deployment-security.md](architecture/admin-auth-and-deployment-security.md)
- [architecture/pg-migration-guide.md](architecture/pg-migration-guide.md) — SQLite → PostgreSQL operator guide (Wave 11)
- [API_REFERENCE.md — Authentication](API_REFERENCE.md#authentication)
- [XTREAM_CODES_API.md](XTREAM_CODES_API.md) — client API
- klopstack: `docker-compose.yaml` (service `iptvproxy`), `traefik-dynamic.yaml`, `traefik-static.yaml`
