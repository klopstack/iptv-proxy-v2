# PPV Event-Aware Filtering System Design

## Executive Summary

This document outlines a multi-phase approach to implement intelligent PPV channel filtering that shows/hides PPV channels based on actual scheduled events. The system will be provider-aware, flexible, and extensible to handle the diverse formats found across different IPTV services.

**Phase 1 (MVP):** Support major US providers with deterministic event detection
**Phase 2:** Expand to international providers with format learning
**Phase 3:** Historical/reruns intelligence for FLO Sports and similar

---

## 1. Data Analysis & Pattern Recognition

### 1.1 PPV Format Categories

Based on analysis of the full PPV.list (11,937 channels), PPV channels fall into these categories:

#### A. **Dated Events with Structured Time Encoding** (Provider-Specific)

These channels embed event information and timestamps directly in the channel name:

**ESPN+ PPV (US)**
```
37084|1601718|US (ESPN+ 001) | Adelaide United vs. Western Sydney Wanderers FC Dec 27 3:35AM ET (2025-12-27 03:35:06)|US| ESPN+ PPV|1
37129|1601673|US (ESPN+ 046) |  (2098-12-31 08:00:01)|US| ESPN+ PPV|1  [UNSCHEDULED - placeholder date]
```
- Format: `{Country}(Provider ##) | {Event Name} {MonthDay HourAMPM ET} ({ISO-datetime})|...`
- Date encoding: ISO datetime in parentheses
- **Placeholder value:** `2098-12-31` = no event scheduled
- Action: **Show only if date ≠ 2098-12-31**

**B1G+ PPV (US)**
```
39432|1659345|US (BTN+ 001) | Basketball (W): Rutgers at Michigan State (2025-12-28 13:50:00)|US| B1G+ PPV|1
```
- Format: `{Country}(Provider ##) | {Event Description} ({ISO-datetime})|...`
- Always has datetime - need to parse and compare against current time
- **Action:** Show if datetime >= current time

**Fanatiz PPV (BR - but global)**
```
40051|1535759|(Fanatiz 001) | Benin vs Botswana (2025-12-27 07:30:00)|BR| FANATIZ PPV|0
```
- Format: `(Provider ##) | {Event Description} ({ISO-datetime})|...`
- Clear event names with ISO datetimes
- Action: **Show if event is future**

---

#### B. **Named Events Without Dates** (Requires Content Parsing)

Channels with event names but no time information:

**FLO College/Racing/Sports PPV (US)**
```
38823|1500901|:Flo College  03|US| FLO COLLEGE PPV|1
38821|1500903|Columbia College vs UNCW @ Dec 27 12:00 PM :Flo College  01|US| FLO COLLEGE PPV|1
38922|1500711|PBR RidePass :Flo Racing  01|US| FLO RACING PPV|1
```
- **Challenge:** Some entries are just slot numbers (`:Flo College 03`) with no metadata
- **Some entries** have event names embedded before the provider slot ID
- **FLO SPORTS:** Contain dates like `22/10 19:00` (October 22) but these are PAST events (data from Jan 2)
- **Action:** Need external EPG/schedule matching or metadata service

---

#### C. **24/7 Entertainment PPV** (Always Available)

Entertainment content that airs continuously:

```
32962|485207|US: 24/7  COMEDY MOVIES|US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ|1
32866|485304|#### 24/7 MOVIES ᴿᴬᵂ ⁶⁰ᶠᵖˢ ####|US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ|0
6688|1406418|NL: VIAPLAY TV 24/7 ᴿᴬᵂ|NL| VIAPLAY PPV|0
```
- **Pattern:** Contains `24/7` in title
- **Action:** Always show these (always available)
- **Note:** Some marked as `|0` (locked/unavailable) - defer to channel status flag

---

#### D. **No Event Indicators** (Should Hide)

Placeholder channels with no scheduled events:

```
42109|1036847|AR: TOD PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE|AR| TOD SPORT ⁸ᴷ & PPV ⚽|0
6025|947890|AT: DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE|AT| DAZN PPV|0
```
- **Pattern:** Contains `NO EVENT STREAMING` or `NO EVENT`
- **Action:** Always hide

---

#### E. **No Additional Information** (Provider Requires Schema)

Channels with just provider names and numbers (most common):

```
35561|430332|US: BALLY SPORTS ARIZONA HD|US| BALLY SPORTS PPV|1
```
- **Challenge:** No embedded event data
- **Action:** Either:
  1. Assume always available (conservative)
  2. Require external EPG/metadata
  3. Track by category - some providers (Bally Sports) may not use PPV for per-event; they're channel subscriptions

---

### 1.2 PPV Category Characteristics

| Provider | Country | Format | Encoding | Placeholder | Past Events | Phase |
|----------|---------|--------|----------|-------------|-------------|-------|
| ESPN+ PPV | US | Dated slots | ISO datetime | 2098-12-31 | ❌ Hide | 1 |
| B1G+ PPV | US | Dated slots | ISO datetime | None (always populated) | Hide (automatic) | 1 |
| DAZN PPV | AT/BE/BR/CA/etc | Placeholder slots | None visible | "NO EVENT" text | ❌ Hide | 1 |
| Bally Sports | US | Channel name only | None | None | ✓ Show always | 1 |
| Fanatiz PPV | BR+ | Dated events | ISO datetime | None visible | Hide (automatic) | 2 |
| FLO Sports | US | Mixed (slots + named) | Date as `DD/MM HH:MM` | Past dates visible | ✓ Show (phase 2) | 2/3 |
| FLO College/Racing | US | Named slots | Sometimes in name | Slot numbers only | ❌ Hide | 2 |
| 24/7 Entertainment | Multi | Named always available | Text `24/7` | None | ✓ Show always | 1 |

---

## 2. Proposed Architecture

### 2.1 Data Model

New table: `PPVEventFilter` (to track provider-specific filtering rules)

```python
class PPVEventFilter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(255), unique=True, nullable=False)  # e.g., "US| ESPN+ PPV"
    provider_name = db.Column(db.String(100), nullable=False)  # e.g., "ESPN+"
    filter_type = db.Column(db.String(50), nullable=False)  # "ISO_DATETIME", "TEXT_CONTAINS", "ALWAYS_HIDE", "ALWAYS_SHOW"
    
    # Config for different filter strategies
    date_field_pattern = db.Column(db.String(500))  # Regex to extract datetime: r'\((\d{4}-\d{2}-\d{2}[^)]*)\)'
    placeholder_date = db.Column(db.String(50))     # e.g., "2098-12-31" for ESPN+
    placeholder_text = db.Column(db.String(500))    # e.g., "NO EVENT STREAMING" for DAZN
    
    # For entertainment channels
    always_show_pattern = db.Column(db.String(500))  # e.g., "24/7"
    
    # For external metadata matching (phase 2)
    requires_epg_lookup = db.Column(db.Boolean, default=False)
    
    # Allow manual overrides per account
    enabled = db.Column(db.Boolean, default=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
```

### 2.2 Filtering Logic Flow

```
Input: Channel from IPTV provider
|
├─ Is this a PPV channel? (detect via category)
│  └─ No → Pass through (not affected by PPV filter)
│  
└─ Yes → Look up PPVEventFilter for this category
   │
   ├─ filter_type == "ALWAYS_SHOW" → Show (e.g., Bally Sports)
   │
   ├─ filter_type == "ALWAYS_HIDE" → Hide
   │
   ├─ filter_type == "TEXT_BASED" → Check placeholder_text
   │  └─ "NO EVENT" in name? → Hide
   │  └─ "24/7" in name? → Show
   │
   ├─ filter_type == "ISO_DATETIME"
   │  ├─ Extract datetime using date_field_pattern regex
   │  ├─ Check if == placeholder_date → Hide
   │  ├─ Check if < current_time → Hide (past event)
   │  └─ Otherwise → Show & Generate EPG entry
   │
   └─ filter_type == "REQUIRES_EPG" → Defer to EPG service (phase 2)
```

### 2.3 Implementation Components

#### A. `services/ppv_filter_service.py` (NEW)

```python
class PPVFilterService:
    """Intelligent filtering for PPV channels based on event scheduling."""
    
    def should_show_channel(self, channel: Channel) -> tuple[bool, Optional[dict]]:
        """
        Determine if a PPV channel should be shown.
        
        Returns:
            (should_show: bool, event_metadata: dict or None)
            event_metadata contains: {
                'datetime': datetime,
                'event_name': str,
                'suggested_epg_duration': timedelta,
            }
        """
        
    def extract_event_datetime(self, channel_name: str, pattern: str) -> Optional[datetime]:
        """Extract ISO datetime from channel name using regex pattern."""
        
    def create_epg_entry(self, channel: Channel, event_meta: dict) -> XMLTVProgram:
        """Generate EPG entry for scheduled event with duration estimate."""
```

#### B. Updates to `services/filter_service.py`

Add PPV filtering as early pass in the filter chain:

```python
def apply_ppv_filter(self, channels: List[Channel], 
                     account_id: int) -> List[Channel]:
    """Filter PPV channels based on event scheduling."""
    ppv_filter_service = PPVFilterService(db)
    filtered = []
    
    for channel in channels:
        is_ppv, event_meta = ppv_filter_service.should_show_channel(channel)
        if is_ppv:
            filtered.append(channel)
            # Store event metadata for EPG generation
            if event_meta:
                cache_event_metadata(channel.id, event_meta)
    
    return filtered
```

#### C. Updates to `app.py` Routes

```python
@app.route('/api/ppv-filters', methods=['GET', 'POST'])
def manage_ppv_filters():
    """CRUD for PPV filter configurations."""
    
@app.route('/api/ppv-filters/<category>/test', methods=['POST'])
def test_ppv_filter(category):
    """Test a PPV filter against sample channel names."""
```

---

## 3. Phase-by-Phase Implementation Plan

### Phase 1: MVP - Core US Providers (2-3 days)

**Target Providers:**
- ESPN+ PPV (ISO datetime with 2098-12-31 placeholder)
- B1G+ PPV (ISO datetime, future only)
- DAZN PPV (all variants) - hide if "NO EVENT"
- 24/7 Entertainment (always show if "24/7" in name)
- Bally Sports (always show - traditional channel subscription)

**Deliverables:**
1. `PPVEventFilter` model + migration
2. `services/ppv_filter_service.py` with basic filtering logic
3. Database seed: Pre-populate filters for 12+ major US categories
4. UI: Simple admin panel to view/edit PPV filters
5. Tests: Unit tests for each filter type

**Database Initialization:**

```python
# In migrations/ or seed script
filters = [
    {
        'category': 'US| ESPN+ PPV',
        'provider_name': 'ESPN+',
        'filter_type': 'ISO_DATETIME',
        'date_field_pattern': r'\((\d{4}-\d{2}-\d{2}[^)]*)\)',
        'placeholder_date': '2098-12-31'
    },
    {
        'category': 'US| B1G+ PPV',
        'provider_name': 'B1G+',
        'filter_type': 'ISO_DATETIME',
        'date_field_pattern': r'\((\d{4}-\d{2}-\d{2}[^)]*)\)',
        'placeholder_date': None  # No placeholder, check future only
    },
    {
        'category': 'US| DAZN PPV',
        'provider_name': 'DAZN',
        'filter_type': 'TEXT_BASED',
        'placeholder_text': 'NO EVENT STREAMING'
    },
    {
        'category': 'US| 24/7 PPV',
        'provider_name': 'Entertainment',
        'filter_type': 'TEXT_BASED',
        'always_show_pattern': '24/7'
    },
    {
        'category': 'US| BALLY SPORTS PPV',
        'provider_name': 'Bally Sports',
        'filter_type': 'ALWAYS_SHOW'
    }
]
```

### Phase 2: International & Complex Formats (1-2 weeks)

**Additional Providers:**
- Fanatiz (BR+) - ISO datetime, always populated
- FLO College/Racing - Named events, requires slot matching
- Regional DAZN variants (BE, AT, DE, etc.)
- International 24/7 providers

**New Features:**
- Event name parsing heuristics
- Provider-specific regex patterns library
- Admin UI for pattern testing

---

### Phase 3: Historical & Smart Caching (Future)

**For FLO Sports reruns:**
- Track dates older than X days (configurable per category)
- Option to show "archived" events for specific providers known to show reruns
- Smart invalidation: Re-parse all PPV channels on schedule (daily 2 AM)
- Performance optimization: Cache PPV availability decisions for 1 hour

---

## 4. Configuration Examples

### ESPN+ PPV Configuration

**Rule:**
- Extract datetime from `(YYYY-MM-DD HH:MM:SS)` pattern
- If datetime == `2098-12-31` → Hide (unscheduled slot)
- If datetime < now → Hide (past event)
- Otherwise → Show + Generate 4-hour EPG entry

**Sample channels:**

| Name | Datetime | Action |
|------|----------|--------|
| `US (ESPN+ 001) \| ... (2025-12-27 03:35:06)` | 2025-12-27 03:35 | ✅ Show |
| `US (ESPN+ 046) \| ... (2098-12-31 08:00:01)` | 2098-12-31 08:00 | ❌ Hide |
| `US (ESPN+ 100) \| ... (2025-01-02 14:00:00)` | 2025-01-02 14:00 | ❌ Hide (past) |

---

### DAZN PPV Configuration (Austria)

**Rule:**
- If channel name contains `NO EVENT STREAMING` → Hide
- Otherwise → Show

**Sample channels:**

| Name | Contains "NO EVENT" | Action |
|------|---------------------|--------|
| `AT: DAZN PPV 1 - NO EVENT STREAMING ...` | ✅ Yes | ❌ Hide |
| `AT: DAZN PPV 2 - IMPORTANT MATCH ...` | ❌ No | ✅ Show |

---

### 24/7 Entertainment Configuration

**Rule:**
- If channel name contains `24/7` → Show (always available)
- Category must match `24/7 PPV` pattern
- Otherwise respect lock status

---

## 5. User Experience Changes

### For End Users

**Before:** 500+ PPV channels, most showing "NO EVENT STREAMING"
- Clutter in playlists
- Confusing which events are actually available

**After:** Only ~50 active PPV channels visible
- Clean playlist with only playable events
- EPG shows scheduled event times and durations
- Can manually adjust filter rules if desired

### For Admins

New settings screen:

```
Settings → PPV Channel Filtering

☑️ Enable PPV Event Filtering
└─ Apply to all accounts

Configure Providers:
├─ US| ESPN+ PPV
│  ├─ Status: ISO_DATETIME
│  ├─ Pattern: \((\d{4}-\d{2}-\d{2}[^)]*)\)
│  ├─ Placeholder: 2098-12-31
│  └─ Test Filter [Test with sample names]
│
├─ US| DAZN PPV  
│  ├─ Status: TEXT_BASED
│  ├─ Hide Pattern: NO EVENT STREAMING
│  └─ Test Filter
│
└─ Add Custom Filter [+]
```

---

## 6. Technical Challenges & Solutions

### Challenge 1: Regex Pattern Robustness

**Issue:** Channel names vary; regex might fail on edge cases

**Solution:**
- Test each pattern against 100 sample channels from IPTV provider
- Maintain pattern version history (allow rollback)
- Add "pattern validation" test suite
- Graceful fallback: If regex fails, default to "show" (conservative)

### Challenge 2: Performance with 10K+ Channels

**Issue:** Filtering 10K channels with regex on every request = slow

**Solution:**
- **Cache results:** PPV availability decisions cached for 1 hour
- **Batch processing:** Process in 500-channel batches
- **Index by category:** Query only relevant categories
- **Async:** Optional background refresh task (scheduled 2 AM daily)

### Challenge 3: Timezone & DST Handling

**Issue:** Event times in channel names use varied formats (ET, PT, ISO, etc.)

**Solution:**
- Normalize all extracted times to UTC before comparison
- Store provider timezone offset in config
- For "smart" parsing, extract timezone indicator from name when present
- Document assumptions per provider

### Challenge 4: FLO Sports Past Events

**Issue:** 2+ months of past events still in feed; unclear if reruns or stale data

**Solution (Phase 3):**
- Add `max_event_age_days` config per category
- Default: 0 (hide all past), configurable to 60+ for known-rerun providers
- Future: Query FLO Sports API directly if available

---

## 7. Testing Strategy

### Unit Tests

```python
# test_ppv_filter_service.py
def test_espnplus_datetime_extraction():
    pattern = r'\((\d{4}-\d{2}-\d{2}[^)]*)\)'
    datetime_str = '2025-12-27 03:35:06'
    assert extract_datetime(datetime_str, pattern) == datetime(2025, 12, 27, 3, 35, 6)

def test_espnplus_placeholder_detection():
    assert should_hide_channel('...2098-12-31...') == True
    assert should_hide_channel('...2025-12-27...') == False

def test_dazn_no_event_detection():
    assert should_hide_channel('...NO EVENT STREAMING...') == True

def test_24_7_always_show():
    assert should_show_channel('...24/7 MOVIES...') == True
```

### Integration Tests

```python
# test_ppv_filtering_integration.py
def test_ppv_filter_in_playlist_generation():
    """Full flow: add account → get channels → filter PPV → generate m3u"""
```

### Manual Testing

- Sample 10 channels from each major provider
- Verify correct show/hide behavior
- Check EPG generation (Phase 1)

---

## 8. Migration Path

### For Existing Users

1. **Opt-in initially:** PPV filtering disabled by default
2. **Gradual rollout:** 
   - Week 1: Beta testers only
   - Week 2: Advanced users can opt-in
   - Week 3: Default enabled for new accounts
   - Week 4: Default enabled for all
3. **Override control:** Users can disable per-account if needed

### Database Migration

```python
# migrations/2025_02_add_ppv_event_filter.py
def migrate(db_path):
    """Add PPVEventFilter table and seed default rules."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ppv_event_filter (
            id INTEGER PRIMARY KEY,
            category VARCHAR(255) UNIQUE NOT NULL,
            provider_name VARCHAR(100) NOT NULL,
            filter_type VARCHAR(50) NOT NULL,
            date_field_pattern VARCHAR(500),
            placeholder_date VARCHAR(50),
            placeholder_text VARCHAR(500),
            always_show_pattern VARCHAR(500),
            requires_epg_lookup BOOLEAN DEFAULT 0,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Seed default filters (only for known major providers)
    default_filters = [...]
    for f in default_filters:
        cursor.execute("INSERT OR IGNORE INTO ppv_event_filter (...) VALUES (...)", f)
    
    conn.commit()
    conn.close()
    return True, "Added PPV event filtering"
```

---

## 9. Future Enhancements

1. **ML-based pattern learning:** Train model on provider naming patterns
2. **API integration:** Direct queries to IPTV provider APIs for EPG data
3. **User preferences:** Per-account, per-provider filtering rules
4. **Event notifications:** Alert users when a specific event becomes available
5. **Calendar view:** Show upcoming PPV events in a calendar interface
6. **Multi-provider event deduplication:** Detect same event across providers

---

## 10. Success Criteria

✅ **Phase 1 Complete:**
- [ ] ESPN+, B1G+, DAZN, 24/7 channels correctly filtered
- [ ] 95%+ of test channels show/hide correctly
- [ ] Performance: Filtering 10K channels < 500ms (with cache)
- [ ] Admin UI allows viewing/editing rules
- [ ] Documentation complete

✅ **Phase 2 Complete:**
- [ ] 80%+ of global PPV categories covered
- [ ] Pattern library with 30+ tested patterns
- [ ] Admin can add custom patterns via UI

✅ **Phase 3 Complete:**
- [ ] Historical event handling for known-rerun providers
- [ ] Scheduled refresh of PPV availability
- [ ] Performance maintained at scale

---

## Appendix A: Sample Provider Patterns

See [PPV_PATTERNS_REFERENCE.md](PPV_PATTERNS_REFERENCE.md) for comprehensive pattern library.

---

## Appendix B: Implementation Checklist

- [ ] Create `PPVEventFilter` model
- [ ] Create migration script
- [ ] Implement `PPVFilterService`
- [ ] Add test suite (unit + integration)
- [ ] Integrate into `FilterService`
- [ ] Add admin UI for rule management
- [ ] Documentation + API docs
- [ ] Performance testing (10K+ channels)
- [ ] Beta test with sample users
- [ ] Deploy with feature flag (default off)
- [ ] Monitor and adjust patterns based on real data
