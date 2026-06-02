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

### Production run (pending)

```
# Fill in after running analyze_ppv_channel_timezones.py on production DB
```
