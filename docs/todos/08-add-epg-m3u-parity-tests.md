# TODO 08: Add EPG/M3U/Xtream Parity Contract Tests

**Priority:** P1  
**Status:** ⬜ Not started  
**Estimated scope:** Medium (new test module)

---

## Problem

The `ChannelQueryService` refactor lacks **contract tests** verifying that all output paths return the same channel set. The audit found EPG, preview, and M3U diverge — tests did not catch this because each route is tested in isolation with mocks.

---

## Goal

A dedicated test module that asserts channel-set parity across outputs for representative scenarios.

---

## Proposed test module

Create `tests/test_channel_output_parity.py`.

### Scenarios to cover

| # | Scenario | Endpoints to compare |
|---|----------|---------------------|
| 1 | Basic account, no filters | M3U vs EPG vs Xtream streams |
| 2 | Account with blacklist filter | M3U vs EPG vs preview |
| 3 | Account with `ppv_visibility=hide_all` + PPV channel | M3U vs EPG vs preview |
| 4 | Account with `ppv_visibility=hide_inactive` + past PPV event | M3U vs EPG |
| 5 | Playlist config with tag include filter | Config M3U vs config EPG |
| 6 | Playlist config with tag exclude (IDs only) | Config M3U vs config EPG |
| 7 | `collapse_duplicates=true` | M3U vs EPG (same stream_ids after collapse) |

### Helper functions

```python
def stream_ids_from_m3u(response_data: bytes) -> set[str]:
    """Extract stream IDs from M3U URLs like /stream/{account_id}/{stream_id}.ts"""

def stream_ids_from_xtream(response_json: list) -> set[str]:
    """Extract stream_id from get_live_streams response."""

def channel_ids_from_epg_xml(response_data: bytes) -> set[str]:
    """Extract channel IDs from XMLTV <channel id="..."> elements."""
    # Must compare using same tvg-id scheme as M3U (ch-{account}-{stream} or event-{id})

def stream_ids_from_preview(response_json: dict) -> set[str]:
    """Extract stream_id from preview API response."""
```

### Comparison logic

For account outputs, compare **stream_id sets** (not display names).

For EPG, map M3U `tvg-id` values to XMLTV `<channel id="...">` — should match `ChannelQueryService.epg_channel_id_for_channel`.

---

## Dependencies

**Must be done after:**
- TODO 01 (EPG unification)
- TODO 02 (preview unification)
- TODO 03 (config preview) — for config preview parity if included

Can stub config preview parity as follow-up if TODO 03 not done yet.

---

## Files to create/modify

| File | Changes |
|------|---------|
| `tests/test_channel_output_parity.py` | **New** — parity contract tests |
| `tests/conftest.py` | Optional shared fixtures: `account_with_ppv`, `playlist_config_with_tags` |

---

## Acceptance criteria

- [ ] At least 5 parity scenarios implemented
- [ ] Tests fail if EPG includes a channel M3U excludes (regression guard)
- [ ] Tests fail if PPV visibility not applied to EPG
- [ ] Tests use real route handlers (integration style), not mocked `EpgService`
- [ ] EPG tests parse actual XML output (minimal fixture, mock EPG data in DB if needed)

---

## Test plan

```bash
venv/bin/pytest tests/test_channel_output_parity.py -v --no-cov
```

For EPG content without full EPG sync, either:
- Mock only `EpgService.generate_epg_for_channels` output while asserting **input channel list**, or
- Seed minimal `EpgProgram` / mapping data and parse real XML

**Preferred:** Assert the channel list passed to `generate_epg_for_channels` via spy/mock **and** end-to-end XML channel count for at least one scenario.

---

## Completion

| Field | Value |
|-------|-------|
| Completed | — |
| PR/Commit | — |
| Notes | — |
