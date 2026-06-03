# Fix build-team-locations GitHub Actions workflow

**Status:** ✅ Done  
**Priority:** P2  
**Audit:** CI / PPV team-location pipeline, June 2026

## Problem

The scheduled workflow [`.github/workflows/build-team-locations.yml`](../../.github/workflows/build-team-locations.yml) does not run successfully. Recent runs fail immediately (~0s) with GitHub’s **“workflow file issue”** message (no job logs).

### Root cause 1 — Invalid workflow YAML

The commit step embeds a shell heredoc inside a YAML `run: |` block:

```yaml
git commit -m "$(cat <<'EOF'
chore: refresh team location registry

Automated weekly rebuild via TheSportsDB premium API.
EOF
)"
```

Lines 43–46 are parsed as top-level YAML keys (`chore: refresh…` lacks a `:`), so the workflow file is **invalid**. `yaml.safe_load` fails at line 45.

### Root cause 2 — Incomplete CI dependencies

The job installs only [`scripts/requirements-build.txt`](../../scripts/requirements-build.txt). The build script imports app modules (`services.thesportsdb_api`, `services.thesportsdb_service`, `services.ppv.city_timezone_map`, `services.mlb_stats_api`), which pull in Flask/SQLAlchemy and other production deps.

With build-only packages, `_build_tsdb_league_entries` fails:

```text
Warning: TheSportsDB league build failed: No module named 'flask_sqlalchemy'
```

Registry output drops **fb** (and **wnba**) coverage (~344 entries vs ~5541 with full deps). Weekly commits would silently ship an incomplete registry.

### Operational gaps

| Gap | Impact |
|-----|--------|
| `THESPORTSDB_API_KEY` repo secret | Required for V2 API; free key skips WNBA and limits league lists |
| No `workflow_dispatch` smoke in PR CI | YAML/deps regressions only surface on schedule or manual run |
| Push to default branch | Needs `contents: write` + branch protection rules that allow `github-actions[bot]` |
| Docs | `ppv-documentation-gaps.md` lists pipeline docs as unchecked; `scripts/README.md` omits build script (see TODO 87) |

## Affected files

- `.github/workflows/build-team-locations.yml`
- `scripts/requirements-build.txt` (or workflow install step)
- `scripts/build_team_locations.py` (optional: isolate TSDB/MLB helpers to reduce app imports)
- `docs/ppv_timezone_analysis.md`, `docs/DEPLOYMENT.md` (operator secret + workflow notes)
- `tests/test_build_fb_locations.py` (fixture-based; keep passing after workflow fix)

## Proposed solution

1. **Fix YAML** — Replace heredoc commit message with a safe form, e.g.:
   - `git commit -m "chore: refresh team location registry" -m "Automated weekly rebuild via TheSportsDB premium API."`
   - Or move commit logic to `scripts/ci_commit_registry.sh` referenced by the workflow
2. **Fix dependencies** — Either:
   - Install production deps in the workflow (`pip install -r requirements.txt` or `make install-py`), or
   - Extend `requirements-build.txt` with minimal transitive deps needed by imported `services/*` modules, or
   - Refactor build script to avoid Flask/SQLAlchemy imports for offline registry build (preferred long-term)
3. **Validate in CI** — Add to [88](./88-expand-ci-quality-gates.md) or this PR:
   - `actionlint` / YAML parse check on workflow files
   - Optional job: `python scripts/build_team_locations.py` without `--refresh` (uses cache) on PR when `data/team_locations/**` or build script changes
4. **Secrets & docs** — Document `THESPORTSDB_API_KEY` in deployment runbook; note WNBA requires premium V2 key
5. **Manual verification** — `workflow_dispatch` on default branch; confirm bot commit or “no changes” path

## Acceptance criteria

- [x] Workflow YAML parses; `workflow_dispatch` run completes (success or intentional no-op commit)
- [x] Build step produces registry with **fb** entries when `THESPORTSDB_API_KEY` is set (same order of magnitude as local full-env build)
- [x] Commit/push step uses valid shell without breaking YAML
- [x] Operator docs mention repo secret and weekly schedule
- [x] (Optional) PR check or actionlint prevents invalid workflow YAML

## Test plan

1. Parse workflow: `python -c "import yaml; yaml.safe_load(open('.github/workflows/build-team-locations.yml'))"`
2. Clean venv with only workflow-installed deps: run `python scripts/build_team_locations.py`; assert no `flask_sqlalchemy` import error and `coverage_by_sport` includes `fb`
3. `workflow_dispatch` on GitHub; verify job logs and registry commit (or empty diff)
4. Existing: `pytest tests/test_build_fb_locations.py tests/test_build_milb_locations.py tests/test_team_location_registry.py`

## Dependencies

- Complements [87](./87-fix-stale-documentation.md) (scripts README, deploy order)
- [88](./88-expand-ci-quality-gates.md) (workflow lint in CI)
- Related PPV: [58](./58-fix-team-resolution-and-validation.md) (registry consumers)

## Completion

https://github.com/klopstack/iptv-proxy-v2/pull/18
