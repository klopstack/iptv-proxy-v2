# SofaScore calendar sport slugs

Secondary PPV calendar source behind ESPN tennis ([122](../todos/122-tennis-calendar-event-source.md)). Wired in [126](../todos/126-sofascore-calendar-multi-sport-and-enrichment.md); client/parser in [125](../todos/125-sofascore-tennis-calendar-slice1.md).

## Endpoint

```http
GET https://api.sofascore.com/api/v1/sport/{slug}/scheduled-events/{YYYY-MM-DD}
```

Feature flag: `ppv_sofascore_calendar_enabled` (default **off**).

## Merge order

1. TheSportsDB HTML + API supplement + MiLB
2. **ESPN tennis** (primary)
3. **SofaScore tennis** (secondary, flag on) — deduped by `(player pair, calendar day)`; ESPN wins

## Sport slugs

| Slug | PPV use | Priority | Status |
|------|---------|----------|--------|
| `tennis` | Wheelchair, ITF, legends gaps after ESPN | P0 | Production (126) |
| `mma` | Combat PPV overlap with [123 track C](../todos/123-extended-calendar-coverage-college-obscure-sports.md) | P2 | Documented only |
| `table-tennis` | Niche feeds | P3 | Documented only |

Additional slugs: discover via SofaScore sport list; add behind per-sport flags when production `no_match` volume justifies.

## Rate budget

Module limiter: ~20 req/min with jitter (`services/tennis/sofascore_calendar.py`).

Rough envelope for tennis-only production:

- 1 sport × 1 request/day × 7-day enrichment window ≈ 7 requests per channel batch date sweep
- Stay within shared calendar supplement windows (`MAX_API_SUPPLEMENT_DAYS_BACK` / `AHEAD`)

## Detail fetch

SofaScore events use `data_completeness='basic'` — do not enqueue TheSportsDB detail worker (same as `api_tennis` / ESPN tennis).
