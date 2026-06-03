# Extract EPG match rules routes (TODO 78 phase 2)

**Status:** ✅ Done  
**Priority:** P2  
**Parent:** [78-split-fat-route-modules.md](./78-split-fat-route-modules.md) (phase 1 ✅ PR #36)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **W**

## Summary

Move preview/rematch orchestration and heavy inline logic out of `routes/epg/match_rules.py` (~1,500 lines) into existing `services/epg/match_rules/` services. Routes become thin: parse request → call service → serialize response.

## Problem

`routes/epg/match_rules.py` is the largest remaining fat route module after `accounts.py` phase 1. It mixes Flask handlers, DB queries, preview orchestration, and serialization — hard to test and review.

## Affected files

- `routes/epg/match_rules.py`
- `services/epg/match_rules/` (extend or add orchestration helpers)
- `tests/test_epg_match_rules*.py` (or equivalent route tests)

## Proposed solution

1. Identify route handlers that own business logic (preview, rematch, bulk operations).
2. Extract orchestration into service functions callable without Flask context.
3. Keep HTTP layer: validation, status codes, JSON envelopes (aligned with TODOs 72–73 ✅).
4. Reuse serializers from TODO 79 ✅ where applicable.

## Acceptance criteria

- [x] `routes/epg/match_rules.py` line count reduced by ≥30% vs pre-extraction baseline (1,444 → 294, −80%)
- [x] No behavior change; existing route test suite passes
- [x] Extracted logic covered by service-level unit tests (no Flask request context required)

## Test plan

```bash
venv/bin/pytest tests/ -k "match_rules" -q --no-cov
# Full route regression after extraction
make test-fast
```

## Dependencies

- [78](./78-split-fat-route-modules.md) phase 1 ✅ — pattern established with `AccountAdminService`
- [79](./79-extract-shared-route-serializers.md) ✅ — shared serialization for rulesets/rules entities
- [96](./96-extract-epg-match-rules-routes.md) before [97](./97-extract-config-transfer-routes.md) recommended (no hard blocker)

## Completion

- **PR #42:** https://github.com/klopstack/iptv-proxy-v2/pull/42 — `EpgMatchRulesRouteService`; `routes/epg/match_rules.py` 1,444 → 294 lines (−80%); `tests/test_epg_match_rules_route_service.py`
