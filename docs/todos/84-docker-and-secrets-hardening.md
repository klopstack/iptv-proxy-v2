# Docker and secrets hardening

**Status:** ✅ Complete  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Deployment security gaps:

| Issue | Location |
|-------|----------|
| No `.dockerignore` | `Dockerfile` does `COPY . .` — can bake `.env`, `node_modules`, test DBs |
| Misleading `SECRET_KEY` | `docker-compose.yml`, `app.py` — Flask boilerplate; app uses Traefik + Authentik, not session auth |
| Container runs as root | `Dockerfile` had no `USER` directive |
| Host networking | `docker-compose.yml` `network_mode: host` exposes admin on all interfaces |
| CDN scripts without SRI | `templates/base.html` bootstrap from jsdelivr |

Note: `static/js/mpegts.min.js` **exists** in repo (218KB); CI verifies required static assets on build.

## Affected files

- `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`
- `app.py`, `services/flask_session.py`
- `.dockerignore`, `.env.example`
- `.github/workflows/build.yml`
- `README.md`, `docs/DEPLOYMENT.md`

## Proposed solution

1. Add `.dockerignore` (`.env`, `venv`, `node_modules`, `instance/`, `htmlcov/`, `*.db`, `.git`)
2. **Disable Flask sessions** (`NullSessionInterface`) — no `SECRET_KEY` required; admin auth is Traefik + Authentik (TODO 68)
3. Remove `SECRET_KEY` from compose, `.env.example`, and operator docs
4. Add non-root `USER` aligned with compose PUID/PGID
5. Document firewall / bind address expectations for host networking
6. CI step: verify required static assets exist

## Acceptance criteria

- [x] `.dockerignore` present and excludes secrets/local artifacts
- [x] Flask sessions disabled; no `SECRET_KEY` in deployment config
- [x] Documented deployment security section in README

## Test plan

- [x] Unit test: app serves requests without `SECRET_KEY` (null session interface)
- Docker build smoke test in CI (deferred to TODO 87)

## Dependencies

- TODO 68 (document Traefik + Authentik model) complements deployment hardening

## Completion

- Disabled Flask sessions via `services/flask_session.py`; removed `SECRET_KEY` from app and deploy config
- Added `.dockerignore`, non-root `USER` in Dockerfile, README/DEPLOYMENT security notes
- CDN SRI hardening deferred to [92-cdn-script-sri-hardening.md](./92-cdn-script-sri-hardening.md)

## Deferred

| Item | TODO |
|------|------|
| Bootstrap/jQuery CDN Subresource Integrity | [92](./92-cdn-script-sri-hardening.md) |
| Docker build smoke test on PR | [87](./87-fix-stale-documentation.md) / [88](./88-expand-ci-quality-gates.md) |
