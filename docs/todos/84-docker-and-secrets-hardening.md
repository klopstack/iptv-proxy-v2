# Docker and secrets hardening

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** Application-wide audit, June 2026

## Problem

Deployment security gaps:

| Issue | Location |
|-------|----------|
| No `.dockerignore` | `Dockerfile` does `COPY . .` — can bake `.env`, `node_modules`, test DBs |
| Default `SECRET_KEY` | `docker-compose.yml`, `app.py` — `change-me-in-production` |
| Container runs as root | `Dockerfile` has no `USER` directive |
| Host networking | `docker-compose.yml` `network_mode: host` exposes admin on all interfaces |
| CDN scripts without SRI | `templates/base.html` bootstrap from jsdelivr |

Note: `static/js/mpegts.min.js` **exists** in repo (218KB); no CI check verifies required static assets on build.

## Affected files

- `Dockerfile`, `docker-compose.yml`, `docker-compose.dev.yml`
- `app.py`
- `.github/workflows/build.yml`

## Proposed solution

1. Add `.dockerignore` (`.env`, `venv`, `node_modules`, `instance/`, `htmlcov/`, `*.db`, `.git`)
2. Fail startup when `SECRET_KEY` is default and `DEBUG=False`
3. Add non-root `USER` aligned with compose PUID/PGID
4. Document firewall / bind address expectations for host networking
5. Optional CI step: verify required static assets exist

## Acceptance criteria

- [ ] `.dockerignore` present and excludes secrets/local artifacts
- [ ] Production mode rejects default SECRET_KEY
- [ ] Documented deployment security section in README

## Test plan

- Docker build smoke test in CI (TODO 87)
- Unit test: app refuses default secret when DEBUG=False

## Dependencies

- TODO 68 (document Traefik + Authentik model) complements deployment hardening
