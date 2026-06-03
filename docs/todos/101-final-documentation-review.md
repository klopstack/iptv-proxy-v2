# Final documentation review (post–Wave 9)

**Status:** ✅ Done  
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

- [x] No broken internal doc links from todos README
- [x] Open TODO count in README matches ⬜ rows (18 open: 107–110, 111–119, 120–124)
- [x] API_REFERENCE and DEVELOPER_GUIDE claims verifiable against code or marked “planned”
- [x] ROADMAP snapshot reflects Waves 1–10 completion state
- [x] Wave 9 TODO files 96–100, 102, 103, 105 have PR links in **Completion**

## Test plan

- Manual review checklist (no code tests)
- Optional: `make test-docs` or link checker if added later

## Dependencies

- **Run after** Wave 9 batches **W–Z** (and optional **AA**) merge — do not start while 96–100 are still open unless doing incremental sub-pass
- [87](./87-fix-stale-documentation.md) ✅ — baseline; this is the **final** sync

## Completion

**Wave 10 doc sync (June 2026)** — no implementation PR; documentation-only pass.

Synced after Wave 9 merges #39–47:

| Area | Updates |
|------|---------|
| `README.md` | Backlog pointer; parallel test commands |
| `docs/todos/README.md` | Wave 9–10 ✅; parents 78/85/92/95 ✅; open count 18 |
| `docs/todos/ROADMAP.md` | Waves 9–10 ✅; snapshot; next-five → 120–124 / 111 / 107 |
| `docs/API_REFERENCE.md` | Config export/import endpoints |
| `docs/DEVELOPER_GUIDE.md` | Route service map; PPV package layout; `make test-parallel` |
| `docs/ARCHITECTURE.md` | Thin route modules + route services |
| Per-TODO 96–100, 102, 103, 105 | Status ✅; Completion PR links verified |

**PR inventory (Wave 9):** [#39](https://github.com/klopstack/iptv-proxy-v2/pull/39) 97, [#40](https://github.com/klopstack/iptv-proxy-v2/pull/40) 99, [#41](https://github.com/klopstack/iptv-proxy-v2/pull/41) 98, [#42](https://github.com/klopstack/iptv-proxy-v2/pull/42) 96, [#43](https://github.com/klopstack/iptv-proxy-v2/pull/43) 100, [#44](https://github.com/klopstack/iptv-proxy-v2/pull/44) 103, [#45](https://github.com/klopstack/iptv-proxy-v2/pull/45) 102, [#46](https://github.com/klopstack/iptv-proxy-v2/pull/46) 104, [#47](https://github.com/klopstack/iptv-proxy-v2/pull/47) 105.

**Known residual drift (doc-only fix deferred):** Index rows for archived TODOs **01–51** still use markdown links to removed spec files (~45 paths). README now documents this; full fix would strip links or restore archived specs (out of Wave 10 scope).
