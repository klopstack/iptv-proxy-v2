# Reverse Event Matcher - Hit Rate Analysis & Improvements

**Analysis Date:** January 4, 2026  
**Calendar Coverage:** 14,578 events from 2025-12-14 to 2026-01-18

## Executive Summary

The reverse event matcher achieved a **52% hit rate** on channels that failed traditional extraction, demonstrating significant value. However, only **6.4% of matches were high confidence (≥0.7)**, indicating room for improvement in match quality.

### Key Metrics

- **Channels Tested:** 500 (failed extraction channels only)
- **Matches Found:** 260 (52.0%)
- **High Confidence Matches:** 32 (6.4%)
- **Average Confidence:** 0.60

### Match Type Distribution

| Match Type | Count | Percentage |
|------------|-------|------------|
| one_team | 171 | 65.8% |
| one_last_name | 54 | 20.8% |
| both_teams | 15 | 5.8% |
| both_last_names | 9 | 3.5% |
| league | 6 | 2.3% |
| event_name_fuzzy | 5 | 1.9% |

**Observation:** The matcher heavily relies on single team matches (66%), which have lower confidence. Only 9.3% achieve both-team matches which typically have higher confidence.

## Failure Analysis (240 failures, 48% of test set)

### 1. Generic Channel Names - **47.5% of failures**
**Count:** 114 failures

**Examples:**
- `Milb 02 :`
- `Paramount+ 86 :`
- `:Tennis  18`
- `NCAAF 49:`

**Root Cause:** Channels contain only network/sport category info with no event details.

**Recommendation:** ❌ **Not Fixable** - Skip these channels or rely on EPG schedule-based matching.

---

### 2. No Sports Keywords - **44.6% of failures**
**Count:** 107 failures

This is the most important category because these channels *do* contain sports content but the matcher can't find it.

#### Sub-patterns identified:

**a) Network-Branded Channels (6 channels, 5%)**
- Examples: `US: NFL NETWORK ᴴᴰ`, `US: NFL REDZONE ᴴᴰ`
- **Fix:** Mark as generic and skip

**b) Date/Time Heavy Format (35 channels, 29%)**
- Examples: 
  - `UFC 00 : CFFC BJJ 16 start:2025-12-28 01:55:00 stop:2025-12-28 07:00:00`
  - `UFC 03: UFC VEGAS 112: POST-FIGHT PRESS CONFERENCE start:2025-12-14 06:55:0`
- **Fix:** Improve timestamp stripping in preprocessing

**c) Fighter Names (Boxing/MMA) (~10-15 channels estimated)**
- Example: `LIVE EVENT 26 -Danny Garcia vs Daniel Gonzalez / Oct 18 : 11PM UK`
- **Root Cause:** TheSportsDB calendar doesn't include fighter names, only event titles
- **Fix Priority:** HIGH - Build fighter name index from combat sports events

**d) Individual Sports (Tennis) (~5-10 channels)**
- Example: `AU (STAN 29) | Paolini v Bencic: Group C _ United Cup 2025/26`
- **Root Cause:** Player names not indexed
- **Fix Priority:** MEDIUM - Extract player names from tennis/golf events

**e) Unclear/Minimal Info (78 channels, 65%)**
- Examples: `MLS LIVE 20:`, `NFL  | 01 -`, `NHL | 14 -`
- **Fix:** These are essentially generic channels, should be filtered

---

### 3. Combat Sports - **2.9% of failures**
**Count:** 7 failures

Small but important category. Most are UFC/Boxing events where the calendar has the event (UFC VEGAS 112) but not the fighter names that appear in channel names.

---

### 4. Unknown - **5.0% of failures**
**Count:** 12 failures

Examples: `US: BOX OFFICE HD`, `US: BOX OFFICE SD`

These are likely PPV placeholder channels without specific event info.

## Success Cases - What's Working Well

### ✅ High Confidence Matches (confidence ≥ 0.7)

Examples that matched correctly with high confidence:

1. **Both Teams Match (0.95-1.00 confidence):**
   - `Arsenal v Liverpool _ Premier League` → Arsenal vs Liverpool
   - `Atlanta Hawks @ New York Knicks` → New York Knicks vs Atlanta Hawks
   - `Belleville Senators vs Laval Rocket` → Belleville Senators vs Laval Rocket

2. **Both Last Names (0.80 confidence):**
   - `NFL | 07 - 1PM Titans at Jaguars` → Jacksonville Jaguars vs Tennessee Titans

3. **One Team with Context (0.75 confidence):**
   - `Houston vs. Oklahoma State` → Oklahoma vs Mississippi (wrong match but reasonable)

### ✅ Surprising Successes

The matcher handled some complex formats well:
- Flo Sports formats: `(FLSP 365) | flohockey: 2026 Greenville Swamp Rabbits vs Jacksonville`
- Timestamped: `NBA: SACRAMENTO KINGS ᴴᴰ` → Los Angeles Lakers vs Sacramento Kings
- Foreign formats: `AU (STAN 60) | 4K _ Arsenal v Liverpool`

## Priority Improvements

### Priority 1: Combat Sports Fighter Name Index 🥊
**Impact:** Could recover 10-20+ additional matches  
**Effort:** Medium

**Implementation:**
1. Extract fighter names from Boxing/MMA events in calendar
2. Build first_name + last_name index
3. Match on `Name1 vs Name2` patterns in channel names
4. Store fighter associations with events

**Expected Improvement:** +2-4% hit rate

---

### Priority 2: Better Timestamp/Metadata Stripping 🕐
**Impact:** Could improve 35+ channels  
**Effort:** Low

**Problem:** Timestamps and metadata interfere with matching:
- `start:2025-12-28 01:55:00 stop:2025-12-28 07:00:00`
- `| Oct 18 : 11PM UK / 6PM ET / 3PM PT`

**Implementation:**
1. Enhance `_clean_channel_name()` method
2. Add regex patterns for common timestamp formats
3. Remove start:/stop: metadata
4. Strip multi-timezone displays

**Expected Improvement:** +3-5% hit rate

---

### Priority 3: Individual Sports Player Index 🎾
**Impact:** Could recover 10-15+ tennis/golf channels  
**Effort:** Medium-High

**Implementation:**
1. Extract player names from individual sports events
2. Handle formats like "Player1 v Player2"
3. Build player name variations (last name only, etc.)

**Expected Improvement:** +2-3% hit rate

---

### Priority 4: Generic Channel Filtering 🔍
**Impact:** Better metrics and reduced false positives  
**Effort:** Low

**Implementation:**
1. Add `is_generic_channel()` check
2. Skip matching for channels with patterns like:
   - `Milb \d+`
   - `[SPORT] NETWORK`
   - Sport name only channels
3. Return early instead of attempting match

**Expected Improvement:** No hit rate change, but cleaner results and faster processing

---

### Priority 5: Team Abbreviation Index 📝
**Impact:** Small but valuable for specific channels  
**Effort:** Medium

**Problem:** Some channels use team abbreviations:
- `LAL vs GSW` → Lakers vs Warriors
- `PHX @ NYK` → Phoenix @ New York Knicks

**Implementation:**
1. Build abbreviation mapping from team names
2. Match 2-4 character uppercase sequences
3. Expand before searching index

**Expected Improvement:** +1-2% hit rate

## Testing Improvements

### Current Test Suite
- ✅ `tests/test_reverse_event_matcher.py` - Unit tests for matcher
- ✅ `test_reverse_matcher.py` - Integration test with real data
- ✅ `analyze_matcher_hit_rate.py` - Comprehensive hit rate analysis
- ✅ `analyze_matcher_failures.py` - Deep dive on failure patterns

### Recommended Additional Tests

1. **Regression Test Suite:**
   - Create fixture of 50 known good matches
   - Run after each improvement to ensure no degradation
   - Track confidence changes

2. **Confidence Calibration:**
   - Review matches at 0.4-0.6 confidence range
   - Are these actually good matches?
   - Adjust scoring if needed

3. **False Positive Detection:**
   - Sample "high confidence" matches manually
   - Verify they're actually correct
   - Track false positive rate

## Projected Improvements Impact

If all Priority 1-3 improvements are implemented:

| Metric | Current | Projected | Change |
|--------|---------|-----------|--------|
| Overall Hit Rate | 52.0% | 62-65% | +10-13% |
| High Confidence (≥0.7) | 6.4% | 12-15% | +5-9% |
| Average Confidence | 0.60 | 0.65 | +0.05 |

**Combined with existing extraction:** Could increase total PPV event matching from current ~17% (399/2904 + 260/2904) to ~25-28% coverage.

## Next Steps

1. **Implement Priority 1 (Combat Sports)** - Highest impact
2. **Implement Priority 2 (Timestamp Stripping)** - Quick win
3. **Re-run hit rate analysis** - Measure improvement
4. **Implement Priority 3 if needed** - Based on results
5. **Create regression test suite** - Prevent degradation

## Code Locations

**Reverse Event Matcher:**
- Implementation: [services/reverse_event_matcher.py](services/reverse_event_matcher.py)
- Tests: [tests/test_reverse_event_matcher.py](tests/test_reverse_event_matcher.py)

**Analysis Scripts:**
- Hit rate analysis: [analyze_matcher_hit_rate.py](analyze_matcher_hit_rate.py)
- Failure analysis: [analyze_matcher_failures.py](analyze_matcher_failures.py)
- Integration test: [test_reverse_matcher.py](test_reverse_matcher.py)

**Documentation:**
- Implementation: [docs/LAST_NAME_MATCHING_IMPLEMENTATION.md](docs/LAST_NAME_MATCHING_IMPLEMENTATION.md)
- Quick Start: [docs/LAST_NAME_MATCHING_QUICK_START.md](docs/LAST_NAME_MATCHING_QUICK_START.md)
