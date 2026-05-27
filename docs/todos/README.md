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
| 23 | [23-remove-backward-compat-shims.md](./23-remove-backward-compat-shims.md) | ✅ | Delete 6 facade shims, `models/_core.py`, `account_xml_cache` param |
| 24 | [24-consolidate-epg-route-tests.md](./24-consolidate-epg-route-tests.md) | ✅ | Merge 3 overlapping EPG route test modules (~2,700 lines) |
| 25 | [25-refactor-epg-service-and-phase-tests.md](./25-refactor-epg-service-and-phase-tests.md) | ✅ | Split `test_epg_service.py` (3.4k lines); rename phase-era tests |
| 26 | [26-mediaflow-stream-backend-tests.md](./26-mediaflow-stream-backend-tests.md) | ✅ | Test stream factory + MediaFlow service (zero tests today) |
| 27 | [27-clarify-is-visible-semantics.md](./27-clarify-is-visible-semantics.md) | ✅ | Resolve `is_visible` cache vs live filters; channel health UI |
| 28 | [28-playlist-config-hardening.md](./28-playlist-config-hardening.md) | ✅ | PUT schema validation; indexed slug column (replace O(n) scan) |
| 29 | [29-deduplicate-shared-helpers.md](./29-deduplicate-shared-helpers.md) | ✅ | Single `get_iptv_service_for_account`; Xtream CQS cleanup |
| 30 | [30-split-epg-match-rules-service.md](./30-split-epg-match-rules-service.md) | ✅ | Split 2k-line `epg_match_rules_service.py` into `services/epg/match_rules/` |
| 31 | [31-deprecate-provider-epg-ui.md](./31-deprecate-provider-epg-ui.md) | ✅ | Align EPG management UI with deprecated provider EPG |
| 32 | [32-expand-frontend-js-tests.md](./32-expand-frontend-js-tests.md) | ✅ | Extend Vitest beyond 2 files / 18 JS modules |
| 33 | [33-error-handling-and-logging-hygiene.md](./33-error-handling-and-logging-hygiene.md) | ✅ | Replace silent `except` blocks in routes/services |
| 34 | [34-post-cleanup-simplifications.md](./34-post-cleanup-simplifications.md) | ✅ | Final layer removal after 22–33 (EpgService facade, FilterService) |

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

---

## P4 — Database hardening (May 2026)

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 35 | [35-referential-integrity-and-account-delete.md](./35-referential-integrity-and-account-delete.md) | ✅ | FK pragma, AccountDeleteService, model ondelete alignment |
| 36 | [36-schema-lifecycle-and-migration-tracking.md](./36-schema-lifecycle-and-migration-tracking.md) | ✅ | schema_migrations table, create_all+migrate boot, playlist_configs migration |
| 37 | [37-sync-lock-hardening.md](./37-sync-lock-hardening.md) | ✅ | Atomic sync lock, sync_started_at, stale lock recovery |
| 38 | [38-data-retention-and-growth-control.md](./38-data-retention-and-growth-control.md) | ✅ | EPG/health cleanup scheduler, prune inactive channel_tags |
| 39 | [39-indexing-test-parity-and-docs.md](./39-indexing-test-parity-and-docs.md) | ✅ | channel_tags index, schema parity tests, developer docs |

## P1–P2 — EPG sync orchestration follow-up (May 2026)

Audit of parallel EPG sync + per-source progress (orchestrator, `EpgSyncProgress`, settings UI). Items **40–51** address correctness bugs, integration gaps, test holes, and duplicated tests.

| # | Document | Status | Summary |
|---|----------|--------|---------|
| 40 | [40-epg-sync-last-sync-on-failure.md](./40-epg-sync-last-sync-on-failure.md) | ✅ | Do not advance `last_sync` when per-source sync fails |
| 41 | [41-epg-sync-global-metadata-on-failure.md](./41-epg-sync-global-metadata-on-failure.md) | ✅ | Do not set global `last_epg_sync` when all sources fail |
| 42 | [42-epg-bulk-sync-concurrency-guard.md](./42-epg-bulk-sync-concurrency-guard.md) | ✅ | Atomic `sync_in_progress` / skip overlapping scheduler + API sync |
| 43 | [43-per-source-epg-sync-orchestrator.md](./43-per-source-epg-sync-orchestrator.md) | ✅ | Route `POST /api/epg/sources/<id>/sync` through orchestrator + progress |
| 44 | [44-epg-sources-page-progress-ui.md](./44-epg-sources-page-progress-ui.md) | ✅ | Show live sync progress on EPG sources page (not only Settings) |
| 45 | [45-ppv-events-epg-progress-callbacks.md](./45-ppv-events-epg-progress-callbacks.md) | ✅ | Wire `progress` through `sync_ppv_events_source` |
| 46 | [46-schedules-direct-program-progress.md](./46-schedules-direct-program-progress.md) | ✅ | Granular programme counters for SD program sync |
| 47 | [47-epg-sync-phase-skipped.md](./47-epg-sync-phase-skipped.md) | ✅ | Implement or remove unused `PHASE_SKIPPED` |
| 48 | [48-epg-sync-failure-semantics-tests.md](./48-epg-sync-failure-semantics-tests.md) | ✅ | Contract tests for `last_sync` + global metadata on failure |
| 49 | [49-epg-orchestrator-integration-tests.md](./49-epg-orchestrator-integration-tests.md) | ✅ | Orchestrator + real `EpgSyncService` (mocked HTTP) integration tests |
| 50 | [50-fix-stale-scheduler-epg-tests.md](./50-fix-stale-scheduler-epg-tests.md) | ✅ | Fix `_sync_epg_sources` stale mock; `run_scheduler` smoke tests |
| 51 | [51-consolidate-bulk-epg-sync-api-tests.md](./51-consolidate-bulk-epg-sync-api-tests.md) | ✅ | Merge duplicate `POST /api/sync/epg` tests into one module |

### Recommended order for items 40–51

```
40-last-sync ──┬──► 48-failure-tests
41-metadata ───┘
42-concurrency ──► 47-skipped (optional) ──► 43-per-source-route ──► 44-sources-ui
45-ppv-progress ──► 46-sd-progress (independent)
49-integration-tests (after 40–43)
50-scheduler-tests
51-dedupe-api-tests (anytime)
```

**Highest impact first:** 40 → 41 → 48 (correct retry + honest status) → 42 → 43 (safe concurrent sync + unified entry points).

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

**Remaining debt (EPG sync orchestration — see 40–51):**
- ~~Failed sync advances `last_sync` and global `last_epg_sync` metadata~~ (fixed in 40–41)
- ~~Per-source sync bypasses orchestrator/progress; progress UI only on Settings~~ (fixed in 43)
- ~~Bulk sync can overlap scheduler; no EPG stale-lock recovery~~ (fixed in 42)
- ~~Duplicate `POST /api/sync/epg` tests; stale `_sync_epg_sources` scheduler mock~~ (fixed in 50–51)
- ~~Orchestrator integration tests only mocked `sync_source`~~ (fixed in 49)

**Other remaining debt:**
- EPG test modules remain large (~2.7k lines across orchestrator/service/route tests); further consolidation optional
- `is_visible` column semantics contradict FilterService docstrings (TODO 27 documents admin-only use)
- Playlist config PUT lacks schema validation; slug lookup is O(n)
- Provider EPG de-emphasized in UI with deprecation warnings (TODO 31 ✅)
- Vitest coverage expanded across lib helpers (TODO 32 ✅)
- MediaFlow/stream-factory tests added (TODO 26 ✅); EPG audit remediation (52) complete
