# Final documentation review (post–Wave 9)

**Status:** ⬜ Not started  
**Priority:** P2  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — **Wave 10** (gate after Wave 9 implementation)

## Summary

Single documentation pass after Wave 9 code lands: sync README, ROADMAP, API reference, developer guide, and TODO index with merged PRs and current architecture. Closes doc drift called out in TODO 87 and ongoing wave merges.

## Problem

Waves 1–8 and Wave 9 will leave scattered **Completion** sections and README statuses. Without a final pass:

- `docs/API_REFERENCE.md` may drift from routes and auth model
- `docs/DEVELOPER_GUIDE.md` may miss parallel pytest, ESM layout, route service map
- `docs/todos/README.md` open counts and P5/P6 summaries become stale
- `ROADMAP.md` snapshot and “next five” lag merged PR batches
- Root `README.md` links and feature lists may reference pre-refactor paths

## Affected files

- `README.md` (repo root)
- `docs/API_REFERENCE.md`
- `docs/DEVELOPER_GUIDE.md`
- `docs/ARCHITECTURE.md` (if blueprint/service lists changed)
- `docs/FRONTEND_JS.md` (after TODO 99)
- `docs/todos/README.md`
- `docs/todos/ROADMAP.md`
- `docs/DEPLOYMENT.md` (CDN/SRI procedure after TODO 98)
- Per-TODO **Completion** sections for Wave 9 items (96–100, optional 102)

## Proposed solution

1. **Inventory:** `gh pr list --state merged` since last doc sync; map PR → TODO numbers.
2. **README.md:** Accurate backlog pointer; wave summary; no broken todo links.
3. **API_REFERENCE:** Xtream URLs, auth (Traefik + Authentik), new/removed endpoints from route splits.
4. **DEVELOPER_GUIDE:** Test commands (serial vs parallel), service layer map for extracted routes, PPV package layout if 102 merged.
5. **TODO index:** Mark 96–100 (and 102) ✅ with PR links; set open backlog count; archive or note parent TODOs 78/85/65/92/95 as fully complete.
6. **ROADMAP:** Mark Wave 9 complete; update snapshot; “next five” → maintenance or empty.
7. **Cross-check:** Blueprint count in `app.py` vs ARCHITECTURE; scripts README vs `scripts/`.

## Acceptance criteria

- [ ] No broken internal doc links from todos README
- [ ] Open TODO count in README matches ⬜/🔄 rows (excluding optional 102 if deferred)
- [ ] API_REFERENCE and DEVELOPER_GUIDE claims verifiable against code or marked “planned”
- [ ] ROADMAP snapshot reflects Waves 1–9 (and 10) completion state
- [ ] Wave 9 TODO files 96–100 have PR links in **Completion** where applicable

## Test plan

- Manual review checklist (no code tests)
- Optional: `make test-docs` or link checker if added later

## Dependencies

- **Run after** Wave 9 batches **W–Z** (and optional **AA**) merge — do not start while 96–100 are still open unless doing incremental sub-pass
- [87](./87-fix-stale-documentation.md) ✅ — baseline; this is the **final** sync

## Completion

_(Add PR link when merged.)_
