# PPV Provider Patterns Reference

Comprehensive pattern library for detecting and filtering PPV channels by provider.

---

## Table of Contents

1. [North America](#north-america)
2. [Europe](#europe)
3. [South America](#south-america)
4. [Asia-Pacific](#asia-pacific)
5. [Testing Guide](#testing-guide)

---

## North America

### US - ESPN+ PPV

**Category:** `US| ESPN+ PPV`

**Characteristics:**
- Numbered slots: `ESPN+ 001` through `ESPN+ 500+`
- ISO datetime in parentheses: `(2025-12-27 03:35:06)`
- Placeholder for unscheduled: `2098-12-31`

**Pattern Rules:**

| Rule | Type | Pattern | Action |
|------|------|---------|--------|
| Extract datetime | Regex | `\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)` | Parse to datetime |
| Check placeholder | Equality | `== "2098-12-31"` | Hide if true |
| Check past | Comparison | `< current_datetime` | Hide if true |
| Show | Default | - | Show + EPG (4hr duration) |

**Sample Channels:**

```
✅ SHOW:
37084|1601718|US (ESPN+ 001) | Adelaide United vs. Western Sydney Wanderers FC Dec 27 3:35AM ET (2025-12-27 03:35:06)|US| ESPN+ PPV|1

✅ SHOW:
37087|1601715|US (ESPN+ 004) | BYU Gameday Dec 27 1:30PM ET (2025-12-27 13:30:00)|US| ESPN+ PPV|1

❌ HIDE:
37129|1601673|US (ESPN+ 046) |  (2098-12-31 08:00:01)|US| ESPN+ PPV|1
[Reason: Placeholder date 2098-12-31]

❌ HIDE:
37083|...|US (ESPN+ 000) | ... (2025-01-01 12:00:00)|US| ESPN+ PPV|1
[Reason: Past event (today is Jan 2)]
```

**Edge Cases:**
- Event name might be empty (just datetime)
- Datetime formatting varies slightly (inconsistent padding)
- Multiple pipes in event name (use regex split carefully)

**EPG Generation:**
- Event name: Extract from name before `|` if available, else "ESPN+ Event"
- Start time: Extracted datetime
- Duration: 4 hours (conservative estimate for sports)
- Description: Include event name if available

---

### US - B1G+ PPV (Big Ten)

**Category:** `US| B1G+ PPV`

**Characteristics:**
- Numbered slots: `BTN+ 001`, `BTN+ 002`, etc.
- ISO datetime in parentheses: `(2025-12-28 13:50:00)`
- **No placeholder value** - always has a datetime
- Sport type prefix: `Basketball (W):`, `Ice Hockey (M):`, etc.

**Pattern Rules:**

| Rule | Type | Pattern | Action |
|------|------|---------|--------|
| Extract datetime | Regex | `\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)` | Parse to datetime |
| Check future only | Comparison | `>= current_datetime` | Hide if false |
| Show | Default | - | Show + EPG (varies by sport) |

**Sample Channels:**

```
✅ SHOW:
39432|1659345|US (BTN+ 001) | Basketball (W): Rutgers at Michigan State (2025-12-28 13:50:00)|US| B1G+ PPV|1

✅ SHOW:
39433|1659344|US (BTN+ 002) | Ice Hockey (M): Kwik Trip Holiday Face_Off: #2 Wisconsin vs. Lake Superior State (2025-12-28 16:50:00)|US| B1G+ PPV|1

❌ HIDE:
39500|...|US (BTN+ 100) | Basketball: Old Game (2025-01-01 10:00:00)|US| B1G+ PPV|1
[Reason: Past event]
```

**Sport Type → Suggested EPG Duration:**
- Basketball: 2.5 hours
- Ice Hockey: 2.5 hours
- Wrestling: 4 hours (tournament)
- Football: 3 hours
- Other: 2 hours (default)

**Edge Cases:**
- Wrestling channels often have `Session X _ Mat Y` format (different tracking)
- Very long event names might be truncated
- No day-of-week indicator, only datetime

---

### US - DAZN PPV

**Category:** `US| DAZN PPV`

**Characteristics:**
- Numbered placeholder slots: `DAZN PPV 1`, `DAZN PPV 2`, etc.
- **No real event data** - just slots with NO EVENT indicator
- All slots typically unavailable

**Pattern Rules:**

| Rule | Type | Pattern | Action |
|------|------|---------|--------|
| Check "NO EVENT" | Text search | `"NO EVENT STREAMING"` in name | Hide if found |
| Default | - | - | Show (but most will have NO EVENT) |

**Sample Channels:**

```
❌ HIDE:
6025|947890|AT: DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE|AT| DAZN PPV|0

❌ HIDE:
6026|947889|AT: DAZN PPV 2 - NO EVENT STREAMING - | 8K EXCLUSIVE|AT| DAZN PPV|0

✅ SHOW (theoretical - would show if no "NO EVENT"):
(This rarely happens in DAZN listings)
```

**Note:** DAZN PPV exists in many countries (AT, BE, BR, CA, CH, DE, DK, ES, FR, IT, NL, etc.) - all follow same pattern.

**Status in IPTV list:** Most marked as `|0` (unavailable), but filtering by name is safety check.

---

### US - Bally Sports PPV

**Category:** `US| BALLY SPORTS PPV`

**Characteristics:**
- **No per-event slots** - these are regional channel subscriptions, not PPV events
- Channel names: `BALLY SPORTS ARIZONA HD`, `BALLY SPORTS FLORIDA (MIAMI) HD`, etc.
- No embedded event data
- Always available (when subscribed)

**Pattern Rules:**

| Rule | Type | Pattern | Action |
|------|------|---------|--------|
| Always show | - | - | Show all |

**Sample Channels:**

```
✅ SHOW:
35561|430332|US: BALLY SPORTS ARIZONA HD|US| BALLY SPORTS PPV|1

✅ SHOW:
35555|430338|US: BALLY SPORTS FLORIDA (MIAMI) HD|US| BALLY SPORTS PPV|1
```

**Note:** These are not true "PPV" channels - they're regional sports network subscriptions. Include in filtering to avoid confusion.

---

### US - FLO Sports PPV (Various)

**Category:** `US| FLO SPORTS PPV`, `US| FLO COLLEGE PPV`, `US| FLO RACING PPV`

**Characteristics:**
- Mixed format: Some are pure slot numbers, some have event names
- Date format when present: `DD/MM HH:MM` (e.g., `22/10 19:00`)
- **Challenge:** Event dates are often in past (data includes 2+ months of old events)
- No way to distinguish between reruns and stale data

**Sample Channels:**

```
❌ HIDE (No event name, just slot):
38823|1500901|:Flo College  03|US| FLO COLLEGE PPV|1

✅ SHOW (Has event name):
38821|1500903|Columbia College vs UNCW @ Dec 27 12:00 PM :Flo College  01|US| FLO COLLEGE PPV|1

❌ HIDE (Past date):
39042|615701|Flo (FLSP) 100: 2025 American International vs Franklin Pierce - Field Hockey - 22/10 19:00|US| FLO SPORTS PPV|1
[Oct 22 is 72 days in the past from Jan 2]

✅ SHOW (Recent date - if implemented):
38922|1500711|PBR RidePass :Flo Racing  01|US| FLO RACING PPV|1
```

**Challenges (Phase 2/3):**
1. No consistent datetime format across all FLO channels
2. Some have human-readable dates only (need parsing)
3. Past events shouldn't display unless explicitly archived
4. Pure slot numbers (no event name) shouldn't show

**Recommended Approach:**
- **Phase 1:** Hide all FLO PPV channels (no reliable data)
- **Phase 2:** Implement date parsing for channels with dates
- **Phase 3:** Maintain allowlist of events known to be reruns

---

### CA - SPORTSNET+ PPV

**Category:** `CA| SPORTSNET+ PPV`

**Characteristics:**
- Similar to ESPN+ with ISO datetimes
- Format: `SPORTSNET+ ###` with `(YYYY-MM-DD HH:MM:SS)`

**Pattern:** Same as ESPN+ PPV (ISO datetime extraction)

---

### CA - DAZN PPV, TSN+ PPV

**Category:** `CA| DAZN PPV`, `CA| TSN+ PPV`

**Characteristics:**
- Similar to US DAZN - mostly placeholder slots with "NO EVENT"

**Pattern:** Same as US DAZN (text-based "NO EVENT" detection)

---

## Entertainment PPV (Cross-Regional)

### 24/7 PPV Channels

**Categories:** `US| 24/7 PPV *`, `NL| VIAPLAY PPV` (24/7), `UK| TRILLER TV PPV` (24/7)

**Characteristics:**
- Contains `24/7` in channel name
- Always available content (movies, shows, live feeds)
- Not event-scheduled
- Should always show (if not locked)

**Pattern Rules:**

| Rule | Type | Pattern | Action |
|------|------|---------|--------|
| Check "24/7" | Text search | `"24/7"` in name | Show if found |
| Check status | Channel flag | `enabled == 1` | Respect existing lock |

**Sample Channels:**

```
✅ SHOW:
32962|485207|US: 24/7  COMEDY MOVIES|US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ|1

✅ SHOW:
6688|1406418|NL: VIAPLAY TV 24/7 ᴿᴬᵂ|NL| VIAPLAY PPV|0
[Note: Even marked as |0, it's continuous content, not event-gated]

❌ HIDE (not marked 24/7):
32866|485304|#### 24/7 MOVIES ᴿᴬᵂ ⁶⁰ᶠᵖˢ ####|US| 24/7 PPV ᴿᴬᵂ ⁶⁰ᶠᵖˢ|0
[Header channel - is a category marker]
```

---

## Europe

### EU - DAZN PPV (Multi-country)

**Categories:** `AT| DAZN PPV`, `BE| DAZN PPV`, `DE| DAZN PPV`, `FR| DAZN PPV`, `IT| DAZN PPV`, `NL| DAZN PPV`, `ES| DAZN PPV`, `CH| DAZN PPV`

**Pattern:** Same as US DAZN (text-based "NO EVENT STREAMING" detection)

All DAZN variants follow the same format: placeholder slots with no real event data.

---

### DE - MAGENTA PPV

**Category:** `DE| MAGENTA PPV`

**Characteristics:**
- Similar to DAZN with placeholder format
- Also uses "NO EVENT" indicators

**Pattern:** Text-based "NO EVENT" detection

---

### DE - FORMULA 1 PPV

**Category:** `DE| FORMULA 1 PPV`

**Characteristics:**
- Event-based (F1 races)
- Potentially has embedded event data
- Seasonal (Oct-Dec, then break until March)

**Status:** Requires analysis of current sample channels (not in current PPV.list)

---

### UK - Sky Sports PPV, etc.

**Status:** Requires analysis of sample channels

---

## South America

### BR - FANATIZ PPV

**Category:** `BR| FANATIZ PPV`

**Characteristics:**
- Full event information: `(Fanatiz ###) | Event Name (YYYY-MM-DD HH:MM:SS)`
- Clearly populated with real events
- ISO datetime format
- **No placeholder value** - always has event name and time

**Pattern Rules:**

| Rule | Type | Pattern | Action |
|------|------|---------|--------|
| Extract datetime | Regex | `\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)` | Parse to datetime |
| Check future | Comparison | `>= current_datetime` | Hide if false |
| Show | Default | - | Show + EPG |

**Sample Channels:**

```
✅ SHOW:
40051|1535759|(Fanatiz 001) | Benin vs Botswana (2025-12-27 07:30:00)|BR| FANATIZ PPV|0

✅ SHOW:
40054|1535756|(Fanatiz 004) | Famalicão vs Estrela (2025-12-27 13:00:00)|BR| FANATIZ PPV|0

❌ HIDE:
40070|...|Fanatiz 020) | Porto vs AVS (2025-01-01 15:15:00)|BR| FANATIZ PPV|0
[Reason: Past event]
```

**EPG Generation:**
- Event name: Full event description (e.g., "Benin vs Botswana")
- Start time: ISO datetime
- Duration: 2 hours (soccer/football default)

---

### BR - DAZN PPV, Disney+ PPV, MAX PPV, etc.

**Characteristics:** Similar to their US/EU counterparts

**Patterns:**
- DAZN: Text-based "NO EVENT"
- Disney+: Check if any event data available
- MAX: Check if any event data available

---

## Asia-Pacific

### AU - NRL TV PPV, AFL PPV, OPTUS PPV

**Status:** Requires sample channel analysis

---

### AU - STAN PPV, ESPN PLAY PPV

**Status:** Requires sample channel analysis

---

## Pattern Library: Regex Expressions

### Datetime Formats Supported

The service handles multiple datetime formats automatically:

```
ISO Formats:
  • 2025-12-27 03:35:06    (ISO with space)
  • 2025-12-27T03:35:06    (ISO with T)
  • 2025-12-27 03:35       (ISO with space, no seconds)
  • 2025-12-27T03:35:06Z   (ISO with Z timezone)
  • 2025-12-27T03:35:06+00:00  (ISO with offset)

Regional Formats:
  • 22/10 19:00            (DD/MM HH:MM - FLO Sports, European)
  • 10/22 19:00            (MM/DD HH:MM - US regional variant)

Note: When year is missing (DD/MM format), assumes current year or next year
      if the date has already passed this year.
```

### Event Name Extraction (Before Datetime)

```regex
# Extract event name before datetime parentheses
\|([^(]+)\s*\(

# Capture text between 'US (...) | ' and ' (YYYY'
US\s*\([^)]+\)\s*\|\s*(.+?)\s+\(
```

### Provider Slot Number Extraction

```regex
# ESPN+ 001, ESPN+ 002, etc.
ESPN\+\s*(\d+)

# BTN+ 001, FLO 03, etc.
(?:BTN\+|Flo\s+)(\d+)
```

---

## Testing Guide

### Test Channels Per Provider

For each provider, maintain a test file with:
1. Channel names that should SHOW
2. Channel names that should HIDE
3. Edge cases

**Example: ESPN+ PPV Test Cases**

```python
test_cases = [
    # (channel_name, should_show, reason)
    (
        'US (ESPN+ 001) | Adelaide United vs. Western Sydney Wanderers FC Dec 27 3:35AM ET (2025-12-27 03:35:06)',
        True,
        'Future event with valid datetime'
    ),
    (
        'US (ESPN+ 046) |  (2098-12-31 08:00:01)',
        False,
        'Placeholder date 2098-12-31 indicates unscheduled'
    ),
    (
        'US (ESPN+ 050) | Old Event (2025-01-01 10:00:00)',
        False,
        'Past event (before current date)'
    ),
    (
        'US (ESPN+ 100) | Event (invalid-date)',
        True,
        'Invalid date - fallback to show (conservative)'
    ),
]
```

### Validation Process

For each new provider pattern:

1. **Collect samples:** Get 20-50 actual channel entries
2. **Extract patterns:** Identify common format elements
3. **Write regex:** Create datetime/event extraction patterns
4. **Test coverage:** Verify against all samples
5. **Edge case handling:** Document behavior for malformed entries
6. **Document:** Add to this reference with examples

---

## Provider Status Matrix

| Provider | Country | Type | Format | Confidence | Phase | Notes |
|----------|---------|------|--------|------------|-------|-------|
| ESPN+ | US | Sports PPV | ISO datetime + 2098-12-31 placeholder | ✅ High | 1 | Tested, reliable |
| B1G+ | US | Sports PPV | ISO datetime, no placeholder | ✅ High | 1 | Tested, reliable |
| DAZN | Multi | Sports PPV | Text-based "NO EVENT" | ✅ High | 1 | Consistent across regions |
| Bally Sports | US | Regional channel | No event data | ⚠️ Medium | 1 | Always show (not true PPV) |
| 24/7 PPV | Multi | Entertainment | Text-based "24/7" | ✅ High | 1 | Simple pattern |
| Fanatiz | BR+ | Sports PPV | ISO datetime | ✅ High | 2 | Well-structured, reliable |
| FLO Sports | US | Sports PPV | Mixed (date format varies) | ❌ Low | 2/3 | Inconsistent, needs work |
| FLO College | US | Sports PPV | Mostly slot numbers | ❌ Low | 2/3 | Requires external data |
| SportsNet+ | CA | Sports PPV | ISO datetime | ⚠️ Medium | 2 | Likely similar to ESPN+ |
| TSN+ | CA | Sports PPV | "NO EVENT" placeholder | ⚠️ Medium | 2 | Likely similar to DAZN |
| Regional DAZN | EU | Sports PPV | Text-based "NO EVENT" | ✅ High | 2 | Consistent pattern |

---

## Notes for Implementation

### Datetime Parsing Best Practices

```python
from datetime import datetime, UTC
import re

def extract_datetime(channel_name, pattern):
    """Safely extract and parse ISO datetime from channel name."""
    match = re.search(pattern, channel_name)
    if not match:
        return None
    
    datetime_str = match.group(1)
    try:
        # Try standard ISO format first
        return datetime.fromisoformat(datetime_str.replace(' ', 'T'))
    except ValueError:
        # Try with manual parsing for edge cases
        try:
            return datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            # Fallback: return None, handle in filter logic
            return None
```

### Caching Strategy

- Cache PPV availability decisions for 1 hour
- Invalidate cache when:
  - Admin updates PPV filter rules
  - New account created (needs recalc)
  - Manual refresh requested
- Store in Redis with key: `ppv_channel:{channel_id}:{account_id}`

### Performance Optimization

For 10K+ channels:

1. **Pre-filter by category** (index lookup)
2. **Batch regex matching** (500 at a time)
3. **Parallel processing** if available
4. **Cache after first run** (most critical)

---

## Future Enhancements

- [ ] Auto-detect provider from category + sample channels
- [ ] ML pattern learning from provider data
- [ ] Direct API integration where available
- [ ] Event notification system
- [ ] User feedback loop to refine patterns
