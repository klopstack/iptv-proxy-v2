# TODO 06: Fix TheSportsDB US League IDs

**Priority:** P1  
**Status:** ✅ Done  
**Estimated scope:** Medium (research + service update + tests)

---

## Problem

`services/thesportsdb_service.py` maps all major US leagues to the same placeholder ID:

```python
LEAGUE_ID_MAP = {
    ...
    "NFL": "133602",  # Placeholder - use team-based lookups
    "NBA": "133602",
    "MLB": "133602",
    "NHL": "133602",
}
```

ID `133602` is **English League 1** (soccer), not any US league. PPV calendar enrichment that relies on league event lookups will fetch wrong events or fail silently.

---

## Goal

Provide correct TheSportsDB league IDs for US sports, or implement team-based lookups as the comment suggests.

---

## Research needed

Look up correct TheSportsDB league IDs (as of 2026):

| League | Likely ID | Verify via API |
|--------|-----------|----------------|
| NFL | TBD | `thesportsdb` API or website |
| NBA | TBD | |
| MLB | TBD | |
| NHL | TBD | |

TheSportsDB v1 API examples:
- NBA: commonly `4387` (verify)
- NFL: commonly `4391` (verify)
- MLB: commonly `4424` (verify)
- NHL: commonly `4380` (verify)

**Do not trust this table — verify before committing.**

---

## Proposed solution

### Option A: Correct league IDs (simplest)

Replace placeholders with verified IDs in `LEAGUE_ID_MAP`.

### Option B: Team-based lookups

For US sports, resolve events via team names extracted from PPV channel titles rather than league-wide event lists. More accurate but larger change — belongs in `services/ppv/enrichment.py` if pursued.

### Recommended: Option A first

Fix the map. Add a unit test that asserts US league IDs are distinct and not equal to `"133602"`.

---

## Files to modify

| File | Changes |
|------|---------|
| `services/thesportsdb_service.py` | Correct `LEAGUE_ID_MAP` |
| `tests/test_thesportsdb_service.py` | Assert correct IDs, mock API responses |

---

## Acceptance criteria

- [x] NFL, NBA, MLB, NHL each have distinct, verified league IDs
- [x] No US league maps to `"133602"`
- [x] `get_next_league_events` returns sport-appropriate events for each league (manual or mocked test)
- [x] Comment about "use team-based lookups" updated or removed if IDs are fixed

---

## Test plan

```bash
venv/bin/pytest tests/test_thesportsdb_service.py -v --no-cov
```

Add:
```python
def test_us_league_ids_are_not_placeholder():
    for league in ("NFL", "NBA", "MLB", "NHL"):
        assert LEAGUE_ID_MAP[league] != "133602"
        assert LEAGUE_ID_MAP[league] != LEAGUE_ID_MAP["English Premier League"]
```

Optional integration test (marked `@pytest.mark.integration`) hitting real API.

---

## Completion

| Field | Value |
|-------|-------|
| Completed | 2026-05-22 |
| PR/Commit | — |
| Notes | Verified IDs via live API: NFL 4391, NBA 4387, MLB 4424, NHL 4380 |
