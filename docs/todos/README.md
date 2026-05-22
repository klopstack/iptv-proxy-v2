# Post-Restructuring TODO Index

This directory contains detailed work items identified during the post-restructuring codebase audit (May 2026). Each document is self-contained: problem statement, affected files, proposed solution, acceptance criteria, and test plan.

**Work through these in order.** Later items may depend on earlier ones (especially P0 channel-selection unification).

## Status legend

| Symbol | Meaning |
|--------|---------|
| ⬜ | Not started |
| 🔄 | In progress |
| ✅ | Done |

Update the status column in this index as each item is completed.

---

## P0 — User-visible correctness (do first)

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 01 | [01-unify-epg-channel-selection.md](./01-unify-epg-channel-selection.md) | ✅ | Route account + config EPG endpoints through `ChannelQueryService` so EPG matches M3U |
| 02 | [02-unify-preview-channel-selection.md](./02-unify-preview-channel-selection.md) | ✅ | Route preview APIs through `ChannelQueryService` (PPV visibility + filters) |
| 03 | [03-fix-playlist-config-preview-live-api.md](./03-fix-playlist-config-preview-live-api.md) | ✅ | Replace live IPTV API in playlist-config preview with database-first logic |
| 04 | [04-fix-tag-id-detection.md](./04-fix-tag-id-detection.md) | ✅ | Fix `ChannelQueryService` tag ID vs name detection when only exclude_tags are IDs |

## P1 — Important fixes and consistency

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 05 | [05-align-proxy-defaults.md](./05-align-proxy-defaults.md) | ✅ | Align default `proxy=` behavior between single-account and config M3U |
| 06 | [06-fix-thesportsdb-league-ids.md](./06-fix-thesportsdb-league-ids.md) | ✅ | Replace placeholder US league IDs in TheSportsDB integration |
| 07 | [07-fix-test-db-isolation.md](./07-fix-test-db-isolation.md) | ✅ | Prevent corrupted/stale test DB from breaking the suite |
| 08 | [08-add-epg-m3u-parity-tests.md](./08-add-epg-m3u-parity-tests.md) | ✅ | Contract tests: same channel set for M3U, EPG, Xtream, previews |

## P2 — Developer experience and deduplication

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 09 | [09-update-models-py-references.md](./09-update-models-py-references.md) | ✅ | Fix Makefile, Docker, docs referencing deleted `models.py` |
| 10 | [10-deduplicate-channel-processing.md](./10-deduplicate-channel-processing.md) | ⬜ | Extract shared tag-loading and duplicate-collapse helpers |
| 11 | [11-test-hygiene.md](./11-test-hygiene.md) | ⬜ | Remove 26 skipped legacy tests; consolidate fixtures in conftest |
| 12 | [12-ui-and-nav-cleanup.md](./12-ui-and-nav-cleanup.md) | ⬜ | Nav links, `/test` route naming, artifact cleanup |

## P3 — Optional / longer-term

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 13 | [13-coverage-test-audit.md](./13-coverage-test-audit.md) | ⬜ | Audit and trim coverage-padding test modules |
| 14 | [14-models-package-split.md](./14-models-package-split.md) | ⬜ | Continue splitting `models/_core.py` into domain modules |
| 15 | [15-facade-layer-consolidation.md](./15-facade-layer-consolidation.md) | ⬜ | Gradually remove backward-compat service facades |
| 16 | [16-frontend-tests.md](./16-frontend-tests.md) | ⬜ | Add minimal JS/HTML lint test coverage |

## P1–P2 — Remaining structural deduplication (post-TODO 08 audit)

These items close gaps where **behavioral parity exists** (TODO 08 tests) but **parallel implementations remain** in route code. Not fully covered by TODO 10 alone.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 17 | [17-route-preview-through-cqs.md](./17-route-preview-through-cqs.md) | ⬜ | Preview endpoints call CQS entry points, not inline FilterService + PPV |
| 18 | [18-config-epg-collapse-duplicates.md](./18-config-epg-collapse-duplicates.md) | ⬜ | Add `?collapse_duplicates=true` to config EPG (parity with config M3U) |
| 19 | [19-extract-m3u-generation-helper.md](./19-extract-m3u-generation-helper.md) | ⬜ | Shared M3U EXTINF/URL formatting for account vs config routes |
| 20 | [20-align-admin-visible-channel-semantics.md](./20-align-admin-visible-channel-semantics.md) | ⬜ | Align or document filter-only counts in stats/categories/EPG admin APIs |
| 21 | [21-remove-dead-channel-selection-code.md](./21-remove-dead-channel-selection-code.md) | ⬜ | Remove `_matches_tag_filter`, orphan tests, sync stale todo statuses |

---

## Dependencies between items

```
01-unify-epg ──────────┐
02-unify-preview ──────┼──► 08-parity-tests ──► 17-preview-through-cqs
03-config-preview ─────┤                      └──► 21-dead-code-cleanup
04-tag-id-detection ───┘

01 + 02 ──► 10-deduplicate-channel-processing ──► 18-config-epg-collapse
                                              └──► 19-m3u-format-helper

08-parity-tests ──► 18-config-epg-collapse

17-preview-through-cqs ──► 20-admin-visible-semantics

09-models-py-refs ── (independent, do anytime)

07-test-db-isolation ──► should be done before 08 (reliable CI)
```

### Recommended order for items 17–21

1. **17** — structural preview unification (highest drift risk)
2. **18** — user-visible config EPG gap
3. **10** — shared collapse/tag helpers (unblocks 18/19 cleanup)
4. **19** — M3U formatting dedup
5. **20** — product decision on admin counts
6. **21** — cleanup after parity tests are canonical

## How to use these documents

1. Open the next ⬜ item in order (or pick one explicitly).
2. Read the full document before coding.
3. Implement only what that document specifies — avoid scope creep.
4. Run the test plan listed in the document.
5. Mark the item ✅ in this index and note the commit/PR in the document's **Completion** section.

## Audit source

These items were derived from a full codebase review covering:
- Antipatterns and incomplete implementations after EPG/PPV/`ChannelQueryService` restructuring
- Useless or misleading tests
- Strange UI/codepaths
- Broken or inconsistent functionality (EPG vs M3U divergence being the highest-impact finding)
