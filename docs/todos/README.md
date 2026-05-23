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
| 10 | [10-deduplicate-channel-processing.md](./10-deduplicate-channel-processing.md) | ✅ | Extract shared tag-loading and duplicate-collapse helpers |
| 11 | [11-test-hygiene.md](./11-test-hygiene.md) | ✅ | Remove 26 skipped legacy tests; consolidate fixtures in conftest |
| 12 | [12-ui-and-nav-cleanup.md](./12-ui-and-nav-cleanup.md) | ✅ | Nav links, `/test` route naming, artifact cleanup |

## P3 — Optional / longer-term

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 13 | [13-coverage-test-audit.md](./13-coverage-test-audit.md) | ✅ | Audit and trim coverage-padding test modules |
| 14 | [14-models-package-split.md](./14-models-package-split.md) | ✅ | Continue splitting `models/_core.py` into domain modules |
| 15 | [15-facade-layer-consolidation.md](./15-facade-layer-consolidation.md) | ✅ | Gradually remove backward-compat service facades |
| 16 | [16-frontend-tests.md](./16-frontend-tests.md) | ✅ | Add minimal JS/HTML lint test coverage |

## P1–P2 — Remaining structural deduplication (post-TODO 08 audit)

These items close gaps where **behavioral parity exists** (TODO 08 tests) but **parallel implementations remain** in route code. Not fully covered by TODO 10 alone.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 17 | [17-route-preview-through-cqs.md](./17-route-preview-through-cqs.md) | ✅ | Preview endpoints call CQS entry points, not inline FilterService + PPV |
| 18 | [18-config-epg-collapse-duplicates.md](./18-config-epg-collapse-duplicates.md) | ✅ | Add `?collapse_duplicates=true` to config EPG (parity with config M3U) |
| 19 | [19-extract-m3u-generation-helper.md](./19-extract-m3u-generation-helper.md) | ✅ | Shared M3U EXTINF/URL formatting for account vs config routes |
| 20 | [20-align-admin-visible-channel-semantics.md](./20-align-admin-visible-channel-semantics.md) | ✅ | Align or document filter-only counts in stats/categories/EPG admin APIs |
| 21 | [21-remove-dead-channel-selection-code.md](./21-remove-dead-channel-selection-code.md) | ✅ | Remove `_matches_tag_filter`, orphan tests, sync stale todo statuses |

---

## Dependencies between items (first pass — complete)

All P0–P3 items **01–21** are ✅. The graph below is kept for historical context.

```
01-unify-epg ──────────┐
02-unify-preview ──────┼──► 08-parity-tests ──► 17-preview-through-cqs ──► 20-admin-visible-semantics
03-config-preview ─────┤                      └──► 21-dead-code-cleanup
04-tag-id-detection ───┘

01 + 02 ──► 10-deduplicate-channel-processing ──► 18-config-epg-collapse, 19-m3u-format-helper

09-models-py-refs ── (independent)

07-test-db-isolation ──► 08 (reliable CI)
```

---

## P1–P3 — Second-pass audit (May 2026)

Follow-up audit after TODOs 01–21. Focus: dead shims, test duplication, semantic footguns, missing backend coverage, UI/doc drift.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 22 | [22-audit-index-and-doc-sync.md](./22-audit-index-and-doc-sync.md) | ✅ | Sync stale index (incl. TODO 18 ✅), fix misleading docstrings |
| 23 | [23-remove-backward-compat-shims.md](./23-remove-backward-compat-shims.md) | ⬜ | Delete 6 facade shims, `models/_core.py`, `account_xml_cache` param |
| 24 | [24-consolidate-epg-route-tests.md](./24-consolidate-epg-route-tests.md) | ✅ | Merge 3 overlapping EPG route test modules (~2,700 lines) |
| 25 | [25-refactor-epg-service-and-phase-tests.md](./25-refactor-epg-service-and-phase-tests.md) | ✅ | Split `test_epg_service.py` (3.4k lines); rename phase-era tests |
| 26 | [26-mediaflow-stream-backend-tests.md](./26-mediaflow-stream-backend-tests.md) | ✅ | Test stream factory + MediaFlow service (zero tests today) |
| 27 | [27-clarify-is-visible-semantics.md](./27-clarify-is-visible-semantics.md) | ✅ | Resolve `is_visible` cache vs live filters; channel health UI |
| 28 | [28-playlist-config-hardening.md](./28-playlist-config-hardening.md) | ⬜ | PUT schema validation; indexed slug column (replace O(n) scan) |
| 29 | [29-deduplicate-shared-helpers.md](./29-deduplicate-shared-helpers.md) | ⬜ | Single `get_iptv_service_for_account`; Xtream CQS cleanup |
| 30 | [30-split-epg-match-rules-service.md](./30-split-epg-match-rules-service.md) | ⬜ | Split 2k-line `epg_match_rules_service.py` |
| 31 | [31-deprecate-provider-epg-ui.md](./31-deprecate-provider-epg-ui.md) | ⬜ | Align EPG management UI with deprecated provider EPG |
| 32 | [32-expand-frontend-js-tests.md](./32-expand-frontend-js-tests.md) | ⬜ | Extend Vitest beyond 2 files / 18 JS modules |
| 33 | [33-error-handling-and-logging-hygiene.md](./33-error-handling-and-logging-hygiene.md) | ⬜ | Replace silent `except` blocks in routes/services |
| 34 | [34-post-cleanup-simplifications.md](./34-post-cleanup-simplifications.md) | ⬜ | Final layer removal after 22–33 (EpgService facade, FilterService) |

### Recommended order for items 22–34

```
22-doc-sync ──► 23-shim-removal ──► 34-simplifications
     │                │
     ├──► 24-epg-route-tests ──► 31-provider-epg-ui
     ├──► 25-epg-service-tests
     ├──► 26-mediaflow-tests
     ├──► 27-is-visible ──► 34-simplifications
     ├──► 28-playlist-config
     ├──► 29-shared-helpers ──► 34-simplifications
     ├──► 30-match-rules-split
     ├──► 32-frontend-tests
     └──► 33-error-handling
```

**Highest impact first:** 22 (truth in docs) → 26 (untested MediaFlow) → 27 (visibility semantics) → 24 (CI time / maintainability).

## How to use these documents

1. Open the next ⬜ item in order (or pick one explicitly).
2. Read the full document before coding.
3. Implement only what that document specifies — avoid scope creep.
4. Run the test plan listed in the document.
5. Mark the item ✅ in this index and note the commit/PR in the document's **Completion** section.

## Audit source

These items were derived from full codebase reviews covering:
- **First pass (TODOs 01–21):** EPG/M3U/preview divergence, parity tests, deduplication, UI/nav cleanup
- **Second pass (TODOs 22–34):** Dead shims, test monoliths, MediaFlow gaps, `is_visible` semantics, provider EPG UI drift, silent error handling

### Second-pass findings summary (healthy vs debt)

**Healthy (guarded by tests):**
- Channel selection unified via `ChannelQueryService` for M3U, EPG, Xtream, previews
- Parity contract tests in `tests/test_channel_output_parity.py`
- Config EPG `collapse_duplicates` implemented (TODO 18 — index was stale)
- Models package split; proxy defaults aligned; admin visible counts use CQS (TODO 20)

**Remaining debt:**
- Six unused Python deprecation shims + `models/_core.py`
- ~6,500 lines of overlapping EPG tests across 4 files
- Zero MediaFlow/stream-factory tests
- `is_visible` column semantics contradict FilterService docstrings
- Playlist config PUT lacks schema validation; slug lookup is O(n)
- Provider EPG promoted in UI but marked deprecated in architecture
- 2 Vitest files vs 18 JS modules
