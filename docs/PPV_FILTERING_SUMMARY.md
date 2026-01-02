# PPV Channel Filtering - Quick Summary

## Problem

Your PPV.list contains ~12,000 channels, most of which have no actual events scheduled. This creates clutter in generated playlists with hundreds of channels showing "NO EVENT STREAMING" or future placeholder dates (2098-12-31).

**Current state:** 500+ PPV channels visible, <50 actually playable
**Desired state:** Only show PPV channels with scheduled/active events

---

## Solution Overview: Provider-Aware Intelligent Filtering

The system will detect **if a PPV channel has an actual scheduled event** by examining the channel name and applying provider-specific rules.

### Key Insight: PPV Formats Fall Into 5 Categories

#### 1. **Dated Events with Placeholder** (ESPN+, others)
```
US (ESPN+ 001) | Event Name (2025-12-27 03:35:06) → SHOW
US (ESPN+ 046) |  (2098-12-31 08:00:01)           → HIDE (placeholder)
```
**Rule:** Extract datetime, hide if `2098-12-31` or in past

#### 2. **Dated Events (No Placeholder)** (B1G+, Fanatiz)
```
US (BTN+ 001) | Basketball: Rutgers at MSU (2025-12-28 13:50:00) → SHOW
```
**Rule:** Extract datetime, hide if in past

#### 3. **Text-Based "NO EVENT"** (DAZN variants)
```
AT: DAZN PPV 1 - NO EVENT STREAMING - ...  → HIDE
```
**Rule:** Hide if "NO EVENT STREAMING" found

#### 4. **24/7 Entertainment** (Movies, shows, feeds)
```
US: 24/7 COMEDY MOVIES                      → SHOW (always)
```
**Rule:** Show if "24/7" in name (always available content)

#### 5. **No Data / Always Available** (Bally Sports)
```
US: BALLY SPORTS ARIZONA HD                 → SHOW (always)
```
**Rule:** These are traditional channel subscriptions, not event-gated

---

## Implementation Approach

### Phase 1 (MVP - 2-3 weeks)

**What:** Support the most common formats with 80%+ coverage
- ✅ ESPN+ PPV (ISO datetime + 2098-12-31 placeholder)
- ✅ B1G+ PPV (ISO datetime, always populated)
- ✅ DAZN variants (ALL regions - text-based "NO EVENT")
- ✅ 24/7 Entertainment (text-based "24/7")
- ✅ Bally Sports (always show)

**Tech Stack:**
- New model: `PPVEventFilter` - stores rules per provider/category
- New service: `PPVFilterService` - applies filtering logic
- Integration: Hooks into existing `FilterService`
- Database: Migration to create table + seed default rules

**DB Schema (simplified):**
```python
class PPVEventFilter:
    category: str           # "US| ESPN+ PPV"
    filter_type: str        # "ISO_DATETIME", "TEXT_BASED", "ALWAYS_SHOW", etc.
    date_pattern: str       # Regex to extract datetime
    hide_text: str          # Text to look for (for TEXT_BASED)
    placeholder_date: str   # "2098-12-31" (for ESPN+)
```

**Result:** ~90% of PPV channels correctly filtered, reducing visible PPV from 500+ to ~50-100 active

---

### Phase 2 (International) - 1-2 weeks

**What:** Expand to international providers
- Fanatiz (BR) - dated events
- FLO College/Racing (US) - requires smarter parsing
- Regional variants

**Result:** 95%+ coverage globally

---

### Phase 3 (Advanced Features) - Future

**What:** Smart caching, historical events, user preferences
- Cache PPV availability decisions (1 hour TTL)
- Show past events for known-rerun providers (FLO Sports)
- Per-account filtering customization
- Event notifications

---

## Data Insights from PPV.list Analysis

### Format Breakdown

**12,000 total PPV entries analyzed:**

| Provider | Count | Has Event Data | Format |
|----------|-------|---|---|
| ESPN+ PPV | 500 | ISO datetime | `...  (2025-MM-DD HH:MM:SS)` |
| B1G+ PPV | 100+ | ISO datetime | `... (2025-MM-DD HH:MM:SS)` |
| DAZN (all regions) | 1000+ | Text marker | "NO EVENT STREAMING" |
| 24/7 Entertainment | 50+ | "24/7" marker | "24/7" in name |
| Bally Sports (US) | 50+ | Channel name only | Region names |
| Fanatiz (BR) | 100+ | ISO datetime | `(Fanatiz ##) \| Event (2025-...)` |
| FLO Sports variants | 300+ | Mixed (mostly slots) | Dates `DD/MM HH:MM` (mostly past) |
| International DAZN | 2000+ | Text marker | "NO EVENT STREAMING" |
| **Other** | **7000+** | Varies | Mostly placeholder slots |

### Key Observations

1. **Placeholder patterns are consistent per provider**
   - ESPN+ always uses `2098-12-31` for unscheduled
   - DAZN variants always use "NO EVENT STREAMING" text
   - ISO datetimes are standard format when present

2. **Most PPV is sports-scheduled, not always-on**
   - 90% of channels have no event (should hide)
   - Only future events should be visible
   - EPG can be generated from datetime info

3. **Entertainment (24/7) is distinct category**
   - Movies, shows, live feeds (always available)
   - Should never be hidden by date/placeholder filters
   - Clearly marked with "24/7" in name

4. **FLO Sports is problematic**
   - Mixes old past events (2+ months ago) with current ones
   - No way to distinguish reruns from stale data
   - Defer to Phase 2/3

---

## User Impact

### Before
- 500+ PPV channels in playlist
- ~450 channels show "NO EVENT STREAMING" 
- ~50 channels show valid events
- User must scan manually to find playable content
- Clutter in IPTV apps

### After
- ~50-100 PPV channels in playlist
- Only channels with scheduled events visible
- EPG shows event times and durations
- User sees relevant, playable PPV
- Clean, curated experience
- Optional: Notifications when events become available

---

## Implementation Checklist (Phase 1)

### Backend
- [ ] Create `PPVEventFilter` SQLAlchemy model
- [ ] Write database migration (idempotent)
- [ ] Seed 12+ default provider rules
- [ ] Implement `PPVFilterService` class
- [ ] Add datetime extraction & validation
- [ ] Integrate into filter pipeline
- [ ] Add caching layer (1 hour TTL)

### Testing
- [ ] Unit tests for each filter type
- [ ] Regex pattern tests (100+ sample channels)
- [ ] Performance tests (10K channels < 500ms)
- [ ] Integration tests (full filter chain)
- [ ] Edge case handling (malformed names, etc.)

### UI/Admin
- [ ] Add admin page to view current rules
- [ ] Allow enable/disable per rule
- [ ] Test filter UI (apply rules to samples)
- [ ] Documentation

### Deployment
- [ ] Feature flag (default: disabled initially)
- [ ] Beta test with sample users
- [ ] Monitor real-world data
- [ ] Gradual rollout (week 1-2: beta, week 3+: general)
- [ ] Document for users

---

## Architecture Benefits

1. **Extensible:** New providers can be added without code changes (just DB entries)
2. **Flexible:** Admin can adjust rules without deployment
3. **Performant:** Caching prevents repeated regex evaluation
4. **Safe:** Conservative fallback (show if uncertain)
5. **Testable:** Each rule type has clear test cases
6. **Reversible:** Can disable per-account if users want old behavior

---

## Estimated Effort

- **Phase 1 (MVP):** 2-3 weeks (40-60 hours)
  - Core filtering logic: 1 week
  - Testing & validation: 1 week
  - UI & documentation: 3-5 days
  
- **Phase 2:** 1-2 weeks (20-30 hours)
- **Phase 3:** Ongoing (as needed)

---

## Next Steps

1. **Review this design** with stakeholders
2. **Validate patterns** against live IPTV data (if available)
3. **Start Phase 1** implementation
4. **Create test suite** (critical for confidence)
5. **Beta test** with real users
6. **Monitor** filtering accuracy and adjust patterns

---

## Questions to Clarify

Before starting implementation:

1. **User preferences:** Should users be able to disable PPV filtering per account?
2. **EPG handling:** How to handle EPG generation for multi-slot events?
3. **Past events:** Should FLO Sports past events ever be shown (as reruns)?
4. **Timezone:** Which timezone(s) should be assumed for time comparisons?
5. **Cache invalidation:** Acceptable staleness? (Propose 1 hour)
6. **Bally Sports:** Confirmed these should always show?

---

## References

See detailed documentation:
- [PPV_FILTERING_DESIGN.md](PPV_FILTERING_DESIGN.md) - Full technical design
- [PPV_PATTERNS_REFERENCE.md](PPV_PATTERNS_REFERENCE.md) - Provider pattern library
