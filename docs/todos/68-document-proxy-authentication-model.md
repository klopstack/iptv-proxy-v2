# Document proxy authentication model (Traefik + Authentik)

**Status:** ✅ Done  
**Priority:** P1 (documentation — not in-app auth implementation)  
**Audit:** Application-wide audit, June 2026  
**Clarification:** June 2026 — auth is **not** missing; it is delegated to Traefik + Authentik (klopstack).

## Problem

The audit incorrectly treated “no Flask-Login” as “no authentication.” In production:

- The app is an **administrative application** (HTML UI + `/api/*` management).
- **Admin access is authenticated at the edge** via **Traefik** and **Authentik** (reverse proxy), not inside Flask.
- **In-app session login is intentionally absent** — there is no `/login` route and none should be added.

Documentation was wrong and misleading (`POST /login` in API_REFERENCE).

## Resolution

Documented the klopstack reference stack:

| Deliverable | Location |
|-------------|----------|
| Traefik dual-router labels, path table, operator checklist | [docs/DEPLOYMENT.md](../DEPLOYMENT.md) |
| Auth model summary | [docs/architecture/admin-auth-and-deployment-security.md](../architecture/admin-auth-and-deployment-security.md) |
| API auth section (no `/login`) | [docs/API_REFERENCE.md](../API_REFERENCE.md#authentication) |
| Architecture security section | [docs/ARCHITECTURE.md](../ARCHITECTURE.md#security-and-authentication) |

**Source of truth for labels:** `../klopstack/docker-compose.yaml` (`iptvproxy` service), `../klopstack/traefik-dynamic.yaml` (`authentik-forwardauth`).

## Intended security model

| Surface | Authentication |
|---------|----------------|
| Admin web UI + `/api/*` | Traefik + Authentik (`iptv-proxy-v2` router, priority 1) |
| Client Xtream, playlists, EPG, streams | Path router `iptv-streams` (priority 100), no Authentik; Xtream credentials in app |

## Acceptance criteria

- [x] No documentation references `POST /login` or in-app session admin auth
- [x] DEPLOYMENT.md describes Traefik + Authentik with klopstack-derived snippets
- [x] Xtream/client credential auth documented separately
- [x] Gluetun `8889:8000` bypass documented
- [x] No new in-app auth middleware

## Completion

June 2026 — derived from klopstack `docker-compose.yaml` and `traefik-dynamic.yaml`.
