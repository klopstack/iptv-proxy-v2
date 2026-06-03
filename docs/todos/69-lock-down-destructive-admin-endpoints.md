# Harden destructive admin endpoints (app-level)

**Status:** ⬜ Not started  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026  
**Clarification:** June 2026 — admin routes are protected by **Traefik + Authentik** (see [DEPLOYMENT.md](../DEPLOYMENT.md)). This TODO is **not** about adding Flask auth.

## Problem

Several admin endpoints are unusually dangerous **even for authenticated operators**. Proxy auth limits who can call them; it does not fix unsafe designs:

| Endpoint | Risk |
|----------|------|
| `POST /api/fcc-match-patterns/reset-defaults` | **DROP TABLE** via raw sqlite3, dynamic migration import — should not exist over HTTP |
| `POST /icon/fetch` | Server-side fetch of arbitrary URL (SSRF) |
| `GET /api/config/export` / `POST /api/config/import` | Full config exfiltration/overwrite (acceptable only behind Authentik; import needs validation) |
| `POST /api/scheduler/stop\|start\|restart` | Denial of service if mis-clicked or compromised Authentik session |

`config/export` lacks `@handle_errors`; FCC reset has no error decorator and bypasses SQLAlchemy migration system.

## Affected files

- `routes/config_transfer.py`
- `routes/api.py` (scheduler)
- `routes/fcc_match_patterns.py` (~522–587)
- `routes/images.py`
- `routes/streams.py`

## Proposed solution

**Not in scope:** Flask `@login_required` or API keys (handled by Traefik + Authentik per TODO 68).

**In scope:**

1. **Remove** `POST /api/fcc-match-patterns/reset-defaults` from HTTP; replace with CLI (`flask reset-fcc-patterns` or script in `scripts/`)
2. Harden `/icon/fetch`: URL scheme allowlist (https only), block private IP ranges, or restrict to known icon hosts
3. Add `@handle_errors` to config export
4. Add schema validation on config import before overwrite
5. Document high-privilege endpoints in deployment/operator runbook (Authentik group recommendations)

## Acceptance criteria

- [ ] No HTTP endpoint performs DROP TABLE or dynamic migration import
- [ ] FCC reset available only via CLI/script
- [ ] `/icon/fetch` SSRF surface reduced (allowlist or documented operator-only use)
- [ ] Config export uses `@handle_errors`
- [ ] Operator docs list destructive APIs and Authentik access expectations

## Test plan

- FCC reset CLI works; HTTP route removed or returns 404/405
- Config export/import error handling tests
- Optional: unit test for icon fetch URL validation

## Dependencies

- TODO 68 ✅ — [DEPLOYMENT.md](../DEPLOYMENT.md)
- Independent of in-app auth implementation
