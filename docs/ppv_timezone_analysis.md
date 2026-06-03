# PPV channel timezone analysis

Run against production/staging:

```bash
python scripts/analyze_ppv_channel_timezones.py --csv /tmp/ppv_tz_backtest.csv
```

## Methodology

For each linked PPV channel with a parseable title datetime:

1. Extract feed signals (country prefix, tags, sport, matchup/home team).
2. Backtest candidate IANA zones vs `Event.scheduled_at` (calendar UTC).
3. Compare legacy `America/New_York` default vs resolver output vs best zone.

## US home-team timezone source

US `@home` PPV timezone resolution uses **`SportsTeam.iana_timezone`** populated from the bundled location registry at `data/team_locations/registry.json`. The registry is rebuilt offline:

```bash
pip install -r requirements.txt   # or scripts/requirements-build.txt for cached/offline sections
python scripts/build_team_locations.py --refresh
```

**CI:** `.github/workflows/build-team-locations.yml` runs weekly (Sunday 06:00 UTC) and on `workflow_dispatch`. Set repository secret `THESPORTSDB_API_KEY` to a premium V2 key so soccer (`fb`) and WNBA entries are included in the committed registry.

During sportsipy team refresh, locations are looked up by `(sport, abbreviation)` — **no city/name heuristics**. Teams without a registry entry keep `city` and `iana_timezone` null and appear in refresh stats as `location_misses`.

Rebuild the registry after franchise moves or when adding manual entries in `data/team_locations/overrides.json`.

### MiLB (affiliated minors)

MiLB teams (`sport: milb`) use the **MLB Stats API** (`statsapi.mlb.com`, sportIds 11–14). Registry keys are MLB `team.id` strings (e.g. `534` for Rochester Red Wings). The build script fetches teams and venue coordinates; runtime schedule enrichment uses the same API for calendar matching.

- Rebuild registry: `python scripts/build_team_locations.py` (MiLB section runs automatically).
- DB refresh: `refresh_milb_teams_from_mlb_api()` (weekly scheduler after sportsipy refresh).
- Parenthetical ISO datetimes `(YYYY-MM-DD HH:MM:SS)` are interpreted as **local wall clock at the home ballpark** (`home_venue_sports_team`), not UTC. WNBA/NBA feeds still use **UTC** via `iso_paren_utc`.

### TheSportsDB-backed teams (soccer + WNBA)

Soccer (`sport: fb`) and WNBA (`sport: wnba`) use a **separate refresh path** from sportsipy. Registry keys are TheSportsDB `idTeam` values (matching `Event.home_team_id` / `idHomeTeam` from enrichment). Run `refresh_tsdb_registry_teams(sports=("fb", "wnba"))` after rebuilding the registry; the weekly scheduler calls this after the sportsipy refresh.

Women's soccer leagues (NWSL, WSL, UWCL) are stored as `sport: fb` with distinct `idTeam` keys. WNBA teams use `sport: wnba`.

Legacy 3-letter FB seed abbreviations (`MUN`, `LIV`, etc.) are removed on FB refresh — use bundled registry aliases for name-based lookup instead.

### Neutral-site / tournament titles

UFC cards, Grand Slams, and similar events are detected via `config/neutral_site_heuristics.json` as **metadata_only** — home-team city timezone is not applied. WNBA feeds with parenthetical ISO datetimes in the title still use **UTC** via `iso_paren_utc`.

## Default country-prefix map (seed)

| Prefix | Default IANA |
|--------|----------------|
| UK, GB | Europe/London |
| NL, BE | Europe/Amsterdam |
| DE | Europe/Berlin |
| FR | Europe/Paris |
| ES | Europe/Madrid |
| IT | Europe/Rome |
| JP | Asia/Tokyo |
| AU | Australia/Sydney |
| US, CA | Multi-zone — use home-team `SportsTeam.iana_timezone` when available |

## Expected outcomes

- UK/NL/ES feeds: country prefix alone should explain title time within 2h for ≥90% of channels.
- US feeds: home-team timezone (regional away@home ordering) should beat Eastern for MLB/NHL/NBA multi-zone matchups.
- Tournament/neutral titles: `metadata_only` widens MatchFilter tolerance; calendar UTC authoritative after link.

## Match-rate metric

Primary success indicator: **`eastern_fail_best_pass`** — channels where Eastern default misses by >2h but the correct zone (often Central/Pacific or EU capitals) would match.

Re-run after Phase 0 on production and paste summary stats below.

### Production backtest (runbook)

Run on a production/staging DB copy when validating timezone changes; paste summary stats here if you want a permanent record:

```bash
python scripts/analyze_ppv_channel_timezones.py --csv /tmp/ppv_tz_backtest.csv
```

No automated production run is stored in-repo — operators run the script as needed.
