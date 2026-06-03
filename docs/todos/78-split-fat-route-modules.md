# Split fat route modules (phased extraction)

**Status:** ✅ Done (phases 1–4; phases 2–4 via Wave 9 PRs #39–42, #41)  
**Priority:** P2  
**Audit:** Application-wide audit, June 2026

## Problem

Several route modules exceed 500–1,500 lines with inline DB queries, serialization, sync orchestration, and business logic:

| File | Lines (approx) |
|------|----------------|
| `routes/accounts.py` | 1,358 |
| `routes/epg/match_rules.py` | 1,500 |
| `routes/config_transfer.py` | 1,075 |
| `routes/epg/channels.py` | 1,025 |
| `routes/fcc_match_patterns.py` | 930 |
| `routes/xtream.py` | 869 |
| `routes/streams.py` | 758 |
| `routes/api.py` | 696 |

Hard to test, review, and change safely. Service layer exists partially but routes still own too much.

## Affected files

Listed above; target services in `services/`.

## Proposed solution

Phased extraction — one module per PR:

1. **accounts.py** — credential CRUD, category sync, channel stats → `AccountAdminService` ✅ (PR phase 1)
2. **epg/match_rules.py** — preview/rematch orchestration → existing match_rules services
3. **config_transfer.py** — export/import serialization → `ConfigTransferService` (may already exist partially)
4. **fcc_match_patterns.py** — shared serializers with config export

Routes become: parse request → call service → serialize response.

## Acceptance criteria

- [x] Phase 1 (`accounts.py`): reduced 1,381 → 932 lines (−32%) via `AccountAdminService`
- [x] Phase 4 (`fcc_match_patterns.py`): reduced 801 → 128 lines (−84%) via `FccMatchPatternsService` + shared CRUD helper (PR batch **X**)
- [x] Each remaining phase reduces target route file by ≥30% without behavior change
- [x] Extracted logic has unit tests independent of Flask request context (`tests/test_account_admin_service.py`)
- [x] No regression in existing route test suites (`tests/test_accounts_routes.py`)

## Test plan

- Run full route test suite after each phase
- Add service-level tests for extracted logic

## Dependencies

- TODO 79 (shared serializers) ✅ — helps FCC/config phases
- See `docs/architecture/api-layer-and-fat-routes.md`

## Wave 9 continuation

| Phase | TODO | PR batch |
|-------|------|----------|
| 2 — `epg/match_rules.py` | [96](./96-extract-epg-match-rules-routes.md) | **W** |
| 3 — `config_transfer.py` | [97](./97-extract-config-transfer-routes.md) | **W** |
| 4 — `fcc_match_patterns.py` + CDN SRI | [98](./98-fcc-patterns-split-and-cdn-sri.md) | **X** |

## Completion

- **Phase 1 — PR #36:** `AccountAdminService`; `accounts.py` 1,381 → 932 lines (−32%); `tests/test_account_admin_service.py`
- **Phase 2 — PR #42:** `EpgMatchRulesRouteService`; `epg/match_rules.py` 1,444 → 294 lines (−80%); `tests/test_epg_match_rules_route_service.py`
- **Phase 3 — PR #39:** `ConfigTransferService`; `config_transfer.py` 954 → 71 lines (−93%); `tests/test_config_transfer_service.py`
- **Phase 4 — PR #41:** `FccMatchPatternsService`; `fcc_match_patterns.py` 801 → 128 lines (−84%); CDN SRI in `templates/base.html`
