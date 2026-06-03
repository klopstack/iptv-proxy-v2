# Expand CI and local quality gates

**Status:** ✅ Done (Wave 7 PR V)  
**Priority:** P3  
**Audit:** Application-wide audit, June 2026

## Problem

CI gaps vs local Makefile capabilities:

| Check | CI | Local |
|-------|-----|-------|
| Python lint | ✅ | ✅ |
| JS lint (narrow scope) | ✅ | ✅ |
| Vitest | ✅ | ✅ |
| pytest 75% cov | ✅ | ✅ |
| vulture dead code | ❌ | ✅ Makefile target |
| Docker build | Push to main only, not PRs | manual |
| pre-commit tests | ❌ (lint only) | `make ci` |
| PRs to develop | ❌ (main only) | — |

`vitest.config.mjs` uses `environment: 'node'` while `jsdom` is installed unused.

`pyproject.toml` omits `scripts/*` from coverage.

## Affected files

- `.github/workflows/build.yml`
- `.pre-commit-config.yaml`
- `Makefile`
- `vitest.config.mjs`

## Proposed solution

1. Add optional vulture job (allow failure initially)
2. Docker build smoke on PRs
3. Extend `pull_request.branches` to include `develop`
4. Document `make ci` as pre-push requirement in DEVELOPER_GUIDE
5. Use jsdom in vitest for DOM helper tests or remove unused dep

## Acceptance criteria

- [x] PR workflow runs docker build (no push)
- [x] vulture runs in CI (warn-only acceptable initially)
- [x] DEVELOPER_GUIDE documents full CI parity commands

## Test plan

- Verify workflow YAML on test PR

## Dependencies

None.

## Completion (Wave 7 PR V)

- `build.yml`: `vulture` job (`continue-on-error`), `docker-build-smoke` on PRs, `develop` in `pull_request.branches`
- `vitest.config.mjs`: `environmentMatchGlobs` for `account_select.test.js`
- `DEVELOPER_GUIDE.md`: `make ci`, `make vulture`, `make docker-build`
- `pyproject.toml` already omits `scripts/*` from coverage (unchanged)
