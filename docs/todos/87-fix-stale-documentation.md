# Fix stale documentation and developer guide drift

**Status:** ✅ Done (Wave 7 PR V)  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

Multiple docs diverge from code:

| Document | Issue |
|----------|-------|
| `docs/API_REFERENCE.md` | ~~Fictitious `/login`~~ (fixed in TODO 68); wrong Xtream URL (`/xtream-api/{id}/` vs `/player_api.php?username=`) |
| `docs/ARCHITECTURE.md` | "17 blueprints" vs 22+ registered; stale service names |
| `app.py` header | Lists 6 blueprints |
| `docs/DEVELOPER_GUIDE.md` | References removed `test_tags.py`; Python 3.9 vs CI 3.11; `.venv` vs Makefile `venv/` |
| `docs/API_REFERENCE.md` | Rate limiting and webhooks sections — not implemented |
| `scripts/README.md` | Only PPV scripts; omits `build_team_locations.py`, cleanup scripts, etc. |
| `docs/todos/README.md` | TODOs 35–39 marked ✅ but files missing |

## Affected files

All listed above.

## Proposed solution

1. Regenerate blueprint list from `app.py` for ARCHITECTURE and app header
2. Confirm API_REFERENCE auth section matches TODO 68 (Traefik + Authentik; no `/login`)
3. Align Xtream docs with `docs/XTREAM_CODES_API.md` and code
4. Update DEVELOPER_GUIDE: Python version, venv path, test file names
5. Mark rate limiting/webhooks as "planned" or remove
6. Expand scripts/README or split ops vs analysis sections
7. Fix README links for missing P4 todos (restore docs or mark archived)

## Acceptance criteria

- [x] Every doc claim verifiable against code or marked "planned"
- [x] DEVELOPER_GUIDE matches Makefile and CI Python version
- [x] No broken links in todos README

## Test plan

- Manual review checklist
- Optional: script to count registered blueprints vs doc

## Dependencies

- TODO 68 covers auth doc correction (Traefik + Authentik)
- PPV doc gaps partially in `docs/architecture/ppv-documentation-gaps.md`

## Completion (Wave 7 PR V)

- Updated `API_REFERENCE.md`, `ARCHITECTURE.md`, `DEVELOPER_GUIDE.md`, `app.py` header, `scripts/README.md`
- P4 TODO rows 35–39 marked archived (no broken file links)
- Rate limiting / webhooks marked planned in API reference
