# PPV Historical category and visibility toggles

**Status:** ⬜ Not started  
**Priority:** P1  
**Audit:** PPV production report, June 2026 (`docker.klopnet.com`)

## Problem

When account **`ppv_visibility = group_live_replay`** (“Group PPV as Live/Replay”), playlist output uses two virtual categories with generic titles **Live** and **Replay**. Product needs:

1. **Clearer naming** — prefix virtual groups with `PPV -` so they stand out in IPTV clients.
2. **A third bucket for long-past replays** — Flo/FLSP and similar archive feeds expose events months or years old that are **still streamable** but do not belong in “recent replay.” Today they either land in **Replay** (undifferentiated) or are treated as **`stale_archive`** noise and hidden/skipped during enrichment ([123](./123-extended-calendar-coverage-college-obscure-sports.md) Track D).
3. **Operator control** — the PPV Management page (`/ppv`) should let operators show/hide **Replay** and **Historical** groups per account (Live visibility **TBD** — see Requirements).

Policy shift: **do not discard enrichable ancient content**. Enrich when possible, then classify by age into **Replay** vs **Historical** instead of `stale_archive` skip or silent hide.

## Current state

| Layer | Behavior today |
|-------|------------------|
| Virtual group titles | M3U/Xtream emit **`Live`** and **`Replay`** (`playlist_format_service._ppv_group_title`, `routes/xtream.py`) |
| Classification | `PPVVisibilityService.classify_live_replay_event` — **24h Live window**; any `scheduled_at < now` → **`replay`** only (no Historical split) |
| Constants | `PPV_GROUP_LIVE = "live"`, `PPV_GROUP_REPLAY = "replay"` in `services/ppv/visibility.py`; `STALE_ARCHIVE_ENRICHMENT_DAYS = 21` in `services/ppv/constants.py` |
| Enrichability | ESPN Play ancient US dates → **`stale_archive`** skip ([123](./123-extended-calendar-coverage-college-obscure-sports.md) Track D); Flo/replay providers exempt per [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A |
| PPV Management UI | Per-account visibility mode `<select>` only; **no** per-group show/hide toggles (`templates/ppv.html`) |
| Accounts UI | Describes “Live (next 24 hours) and Replay” (`templates/accounts.html`) |

```python
# services/ppv/visibility.py — classify_live_replay_event (simplified)
if event.scheduled_at < current_time:
    return cls.PPV_GROUP_REPLAY  # all past → single "replay" bucket
```

## Proposed solution

### 1. Rename virtual categories (group_live_replay only)

| Internal key | Current title | New title |
|--------------|---------------|-----------|
| `live` | Live | **`PPV - Live`** |
| `replay` | Replay | **`PPV - Replay`** |
| `historical` (new) | — | **`PPV - Historical`** |

Wire titles in `_ppv_group_title` (M3U), Xtream category mapping, and any preview/copy on `/ppv` and `/accounts`.

### 2. Replay vs Historical age threshold

Introduce **`PPV_HISTORICAL_THRESHOLD_DAYS`** (proposed default: **21**, same as `STALE_ARCHIVE_ENRICHMENT_DAYS`) in `services/ppv/constants.py`.

| Bucket | Rule (linked event with `scheduled_at`) |
|--------|----------------------------------------|
| **PPV - Live** | Unchanged: `STATUS_LIVE`, or start within **24 hours** ahead (`classify_live_replay_event` live cutoff) |
| **PPV - Replay** | Past event: `now - scheduled_at ≤ 21 days` |
| **PPV - Historical** | Past event: `now - scheduled_at > 21 days` |

Rationale:

- **24h Live window** stays the near-term “live” signal (existing behavior).
- **21-day Replay window** reuses the enrichment stale-archive horizon so operators have one mental model: “recent past” vs “archive library.”
- Events **older than 21 days** that remain linked and streamable move to **Historical** — not dropped as junk.

Extend `classify_live_replay_event` (or successor) to return `PPV_GROUP_HISTORICAL = "historical"` when past age exceeds threshold. Unmatched channels under `group_live_replay` remain hidden (`None`) unless product decides otherwise.

**Update (2026-06):** Added fourth bucket **`PPV - Unmatched Live`** (`-13`) for `no_match` channels with enrichable extraction (competitors + date in live window). Toggle: `ppv_show_unmatched_live` (default true). See PR for classification rules.

**Enrichability reconciliation:** `stale_archive` skip ([123](./123-extended-calendar-coverage-college-obscure-sports.md) Track D) applies only to **non-enrichable** archive noise (e.g. ESPN Play with no replay provider tag). **Enrichable** providers ([129](./129-ppv-replay-archive-enrichment-flosp.md)) must never be skipped solely for age — classify into Historical after match.

### 3. PPV Management visibility toggles

On `/ppv` Visibility tab, when account mode is **`group_live_replay`**, show two checkboxes (persist per account — new columns or JSON settings on `Account`):

- ☐ Show **`PPV - Replay`**
- ☐ Show **`PPV - Historical`**

**Live visibility TBD:** User specified two checkboxes only. Document options for implementer:

- **Option A (minimal):** Live always shown; toggles affect Replay + Historical only.
- **Option B (symmetric):** Three toggles (Live / Replay / Historical) — out of scope unless product expands.

Default proposal: both checkboxes **checked** (preserve current “show all classified past events” behavior).

Filtered groups: channels whose classification maps to a hidden group are omitted from playlist/Xtream output for that account (same as hiding a virtual category).

### 4. Policy matrix (supersedes partial 123/129 Track D wording)

| Content type | Enrichability | Playlist bucket |
|--------------|---------------|-----------------|
| ESPN Play 2023, no provider, no calendar path | **`stale_archive`** skip | Hidden / not in playlist |
| Flo/FLSP Oct 2025 replay, enrichable | Enrich → link | **PPV - Historical** (age > 21d) or **PPV - Replay** if within window |
| Recent tennis replay (linked, 3 days ago) | Enrichable | **PPV - Replay** |
| Upcoming within 24h | Enrichable | **PPV - Live** |

## Requirements

1. Add **`PPV_GROUP_HISTORICAL`** and extend classification with **21-day** Replay/Historical split (configurable constant).
2. Rename group titles to **`PPV - Live`**, **`PPV - Replay`**, **`PPV - Historical`** for `group_live_replay` accounts.
3. Add **Replay** and **Historical** show/hide checkboxes on `/ppv` for `group_live_replay` accounts; document Live as TBD (default: always show).
4. Update **`templates/accounts.html`** (and `/ppv` help text) to describe three virtual groups and toggles.
5. Reconcile **`stale_archive`** in `enrichability.py`: skip only **non-enrichable** ancient titles; enrichable streams → Historical path per [129](./129-ppv-replay-archive-enrichment-flosp.md).
6. API: persist toggle state on account update (`routes/accounts.py` or dedicated PPV settings endpoint).

## Acceptance criteria

- [ ] M3U `#EXTINF group-title` uses **`PPV - Live`**, **`PPV - Replay`**, **`PPV - Historical`** for `group_live_replay` accounts.
- [ ] Xtream live/replay/historical category mapping matches M3U titles.
- [ ] Event 25 days in the past → **Historical**; event 5 days in the past → **Replay**; event in 12 hours → **Live**.
- [ ] Unchecking “Show PPV - Historical” hides historical-classified channels for that account; Replay toggle analogous.
- [ ] Flo/replay-provider channels remain enrichable (not `stale_archive`); linked Oct 2025 fixture → **PPV - Historical** when age > threshold.
- [ ] ESPN Play 2023 non-replay titles still **`stale_archive`** skip (regression guard).
- [ ] Accounts + PPV Management copy updated.

## Test plan

### Unit tests

- `tests/ppv/test_visibility.py` — classification boundaries at 21 days; Historical constant.
- `tests/ppv/test_replay_provider_enrichability.py` — Flo enrichable; ESPN Play stale unchanged.

### Integration tests

- `tests/test_playlist_generation.py` — group titles **PPV - *** ; Historical vs Replay split; toggle hides groups.
- `tests/test_xtream.py` — Xtream categories for three buckets + toggle behavior.

### Manual

1. Set account to **Group PPV as Live/Replay**; generate M3U; verify three group titles.
2. On `/ppv`, toggle Historical off; regenerate; confirm long-past Flo channels absent.
3. Confirm Live bucket still present when Replay/Historical toggled (unless Option B implemented).

## Affected files

- `services/ppv/visibility.py` — `PPV_GROUP_*`, `classify_live_replay_event`, age thresholds, toggle-aware `should_show_channel`
- `services/ppv/constants.py` — `PPV_HISTORICAL_THRESHOLD_DAYS` (proposed 21)
- `services/playlist_format_service.py` — `_ppv_group_title` renamed labels + Historical branch
- `routes/xtream.py` — group title mapping for three buckets
- `routes/accounts.py` — persist visibility toggles
- `models/account.py` — columns or JSON for Replay/Historical show flags
- `templates/ppv.html` — checkboxes on Visibility tab
- `templates/accounts.html` — Live/Replay/Historical description text
- `services/ppv/enrichability.py` — reconcile `stale_archive` vs historical enrichment ([129](./129-ppv-replay-archive-enrichment-flosp.md) Track D)
- Tests: `tests/test_playlist_generation.py`, `tests/test_xtream.py`, `tests/ppv/test_visibility.py`, `tests/ppv/test_replay_playlist_group.py`

## Dependencies

- [129](./129-ppv-replay-archive-enrichment-flosp.md) — enrichability + replay matching (Track A/B); **Track C** group titles superseded by this TODO for naming and Historical bucket.
- [123](./123-extended-calendar-coverage-college-obscure-sports.md) — Track D `stale_archive`; refined here for enrichable vs non-enrichable.
- [131](./131-sofascore-college-amateur-calendar-provider.md) — historical calendar fetch enables linking Flo → Historical classification.
- **Can land in parallel with** [129](./129-ppv-replay-archive-enrichment-flosp.md) Track C UI/title work; classification logic should merge cleanly once 129 Track A enrichability is merged.

## References

- [129 Track D](./129-ppv-replay-archive-enrichment-flosp.md#track-d--reconcile-with-todo-123-stale-archive-policy) — skip vs enrich matrix
- [123 Track D](./123-extended-calendar-coverage-college-obscure-sports.md#track-d--stale-archive-channels) — original `stale_archive` policy
- [ppv-multi-source-events.md](../architecture/ppv-multi-source-events.md) — enrichability skip reasons
- Production Flo queue: [129](./129-ppv-replay-archive-enrichment-flosp.md) (~243 channels)

## Recommended order

**After** [129](./129-ppv-replay-archive-enrichment-flosp.md) Track A enrichability (or in same PR series as Track C refresh). **Before or with** production Flo requeue so linked archive events land in correct bucket. Toggle UI can ship with title rename in one PR.

**Impact:** Preserves long-tail replay library in playlists under **PPV - Historical** instead of hiding or skipping; gives operators client-friendly group names and selective visibility.
