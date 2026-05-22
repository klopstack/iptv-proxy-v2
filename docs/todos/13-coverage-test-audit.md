# TODO 13: Coverage Test Audit

**Priority:** P3  
**Status:** ⬜ Not started  
**Estimated scope:** Large (review + incremental deletion)

---

## Problem

Three test modules exist primarily to satisfy the **75% coverage gate** in `pyproject.toml`:

| File | ~Tests | Stated purpose |
|------|--------|----------------|
| `tests/test_coverage_boost.py` | 96 | "Tests to boost code coverage to 80-85%" |
| `tests/test_routes_coverage.py` | 65 | "boost route coverage to 80%+" |
| `tests/test_additional_coverage.py` | ~30 | "improve coverage for tag service and EPG" |

Characteristics of low-value tests in these files:
- Heavy use of `MagicMock` with assert-on-status-code only
- Duplicate coverage of behaviors tested elsewhere with real fixtures
- Break easily when routes refactor but don't catch real bugs
- Inflate CI time (~2 min suite includes many of these)

---

## Goal

Reduce reliance on coverage-padding tests while maintaining ≥75% coverage through meaningful tests (especially TODO 08 parity tests).

---

## Approach (incremental — do not big-bang delete)

### Phase 1: Audit

For each test class in the three files, classify:

| Category | Action |
|----------|--------|
| **A — Unique valuable** | Move to appropriate domain test file |
| **B — Duplicate** | Delete |
| **C — Mock-only status check** | Delete unless no other coverage |
| **D — Dead route** | Delete |

Run coverage before and after each deletion batch:

```bash
venv/bin/pytest tests/ --cov=. --cov-report=term-missing | tail -20
```

### Phase 2: Replace with targeted tests

As padding is removed, add behavioral tests to:
- `tests/test_playlists_routes.py`
- `tests/test_epg_routes.py`
- `tests/test_channel_output_parity.py` (TODO 08)

### Phase 3: Lower coverage floor (optional)

If maintaining 75% requires keeping low-value tests, consider:
- Raising quality bar in `pyproject.toml` exclude patterns
- Per-module coverage targets instead of global 75%

Only after audit proves meaningful tests cover critical paths.

---

## Candidates for early deletion (verify first)

- `TestWebRoutesExtended` in coverage_boost — likely covered by app route tests
- Duplicate image cache route tests if `test_image_cache.py` covers same paths
- Multiple scheduler EPG sync mock tests if `test_scheduler.py` covers them

**Do not delete without checking coverage impact.**

---

## Files involved

| File | Action |
|------|--------|
| `tests/test_coverage_boost.py` | Audit → shrink or delete |
| `tests/test_routes_coverage.py` | Audit → shrink or delete |
| `tests/test_additional_coverage.py` | Audit → move tag tests to `test_tag_service.py` |
| `pyproject.toml` | Adjust `--cov-fail-under` only if justified |

---

## Acceptance criteria

- [ ] Coverage remains ≥75% (or agreed new threshold documented)
- [ ] Test count reduced by meaningful amount (target: −50 tests minimum)
- [ ] No deletion of unique behavioral coverage without replacement
- [ ] CI time not increased
- [ ] Document audit results in this file's Completion section

---

## Test plan

Full suite + coverage report after each batch:

```bash
venv/bin/pytest tests/ -q --cov=. --cov-fail-under=75
```

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Tests removed | — |
| Coverage before/after | — |
| Notes | — |
