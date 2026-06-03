# Fix pre-commit lint hook install cycle

**Status:** ✅ Done  
**Priority:** P2  
**Discovered:** June 2026 (local commit failure on `wave9/pr-97-config-transfer`)  
**Completion:** Makefile decouples `lint-py` from `install` / `install-hooks`; CI unchanged (`install-py` then `lint-py`).

## Problem

`git commit -am` fails after pre-commit hooks pass:

```text
error: invalid object 100644 af368228c885a3dc454b6c312adf7e8130c4f7e9 for '.github/ISSUE_TEMPLATE/bug-report.md'
error: Error building trees
```

This is **not** general git object corruption in iptv-proxy-v2. The missing blob is sportsipy’s
`.github/ISSUE_TEMPLATE/bug-report.md` (hash verified against `/home/benklop/repos/sportsipy`).

### Root cause chain

1. `.pre-commit-config.yaml` runs `make lint-py` on every commit.
2. `Makefile` defined `lint-py: install` — not `lint-py: venv` or `lint-py: install-py`.
3. `install` runs `install-py`, `install-js`, and **`install-hooks`** (`pre-commit install`).
4. `install-py` runs `pip install -r requirements.txt`, which clones sportsipy from git on each hook run.
5. During `git commit -a`, git sets `GIT_INDEX_FILE=.git/index.lock` while the hook runs.
6. Pip/sportsipy git subprocesses interact badly with that locked index; after hooks pass, `commit -a`
   tries to build trees and references sportsipy’s `bug-report.md` blob, which is not in this repo’s
   object store.

pre-commit’s own source documents that `GIT_INDEX_FILE` during commit can cause “invalid object” errors.

## Affected files

- `Makefile` — `lint-py: install` dependency; consider same pattern on `vulture` / `test` if hooks ever call them
- `.pre-commit-config.yaml` — local hooks delegate to Makefile
- `docs/DEVELOPER_GUIDE.md` — document one-time `make install` vs hook expectations

## Proposed solution

1. **Decouple lint from install-hooks**
   - Change `lint-py` to depend on `venv` only (assume `make install-py` done once).
   - Do **not** run `pre-commit install` or `npm install` inside a pre-commit hook.
2. **Keep CI parity explicitly**
   - CI (`.github/workflows/build.yml`) runs `make install-py` before `make lint-py`.
   - Local docs: run `make install` once after clone; hooks assume venv is ready.
3. **Optional hardening**
   - Added `lint-py-ci` target (`install-py` + `lint-py`) for CI convenience; hooks use `lint-py` only.

## Acceptance criteria

- [x] `make lint-py` does not invoke `install-hooks` or `npm install`
- [x] `git commit -am` succeeds with pre-commit enabled after `make install`
- [x] CI lint job unchanged or explicitly updated to install deps before lint
- [x] DEVELOPER_GUIDE notes one-time setup and the `add` + `commit` vs `-am` distinction

## Test plan

1. Fresh venv: `make install`, then edit a Python file and run `git commit -am 'test'`.
2. Confirm pre-commit still runs flake8/black/isort/mypy and commit completes.
3. Push a branch and verify GitHub Actions `lint-py` job still passes.

## Dependencies

None.
