# Extract config transfer routes (TODO 78 phase 3)

**Status:** ⬜ Not started  
**Priority:** P2  
**Parent:** [78-split-fat-route-modules.md](./78-split-fat-route-modules.md) (phase 1 ✅ PR #36)  
**Roadmap:** [ROADMAP.md](./ROADMAP.md) — Wave 9, PR batch **W**

## Summary

Extract export/import serialization and validation from `routes/config_transfer.py` (~1,075 lines) into `ConfigTransferService` (or extend existing partial service). Routes delegate file/JSON handling to the service layer.

## Problem

Config transfer routes duplicate entity serialization already partially unified in TODO 79. The module mixes import parsing, validation, DB writes, and export assembly — risky to change and untested at the service layer.

## Affected files

- `routes/config_transfer.py`
- `services/` — `ConfigTransferService` or equivalent
- Config transfer / import route tests

## Proposed solution

1. Map export/import endpoints to service entry points (one direction per method).
2. Centralize entity serialization via shared serializers (TODO 79 ✅).
3. Keep route-level concerns: multipart upload, download headers, error mapping.
4. Align import validation with TODO 69 ✅ operator hardening patterns.

## Acceptance criteria

- [ ] `routes/config_transfer.py` reduced by ≥30% without behavior change
- [ ] Export and import paths share service methods used by tests independent of Flask
- [ ] Existing config transfer tests pass unchanged

## Test plan

```bash
venv/bin/pytest tests/ -k "config_transfer" -q --no-cov
make test-fast
```

## Dependencies

- [78](./78-split-fat-route-modules.md) phase 1 ✅
- [79](./79-extract-shared-route-serializers.md) ✅ — export/import entity shapes
- [69](./69-lock-down-destructive-admin-endpoints.md) ✅ — import validation expectations
- Prefer after [96](./96-extract-epg-match-rules-routes.md) in batch **W** (parallel OK if no merge conflicts)

## Completion

_(Add PR link when merged.)_
