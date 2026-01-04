# Date-But-No-Competitors Analysis

## Summary

Analysis of PPV channels that extract date/time information but fail to extract competitor information reveals a significant pattern recognition gap in the PPV event extractor.

**Generated:** 2026-01-03 (Updated after placeholder filtering)
**Total Channels Analyzed:** 1,492 (12.5% of all PPV channels)  
**Placeholder Dates Excluded:** 571 channels with 2098-12-31 or 2099-01-01 dates

## Key Finding

Your suspicion was correct: **Most of these channels DO contain event information**, but the extractor isn't recognizing the competitors due to:

1. **Missing separator patterns** (e.g., "x" for Spanish/Portuguese)
2. **Contextual separators** (e.g., "v" single letter, dash within provider prefix)
3. **Event title formatting** (e.g., "League: Team1 vs Team2")

## Statistics (After Placeholder Filtering)

From `regenerate_ppv_lists.py` output:

```
📊 Total channels processed: 11,937

✅ EXTRACTABLE.list: 3,092 channels (25.9%)
   - With competitors: 1,600 (51.7%)
   - With date/time: 2,953 (95.5%)
   - With both: 1,461 (47.2%)

⚠️  DATE_BUT_NO_COMPETITORS.list: 1,492 channels (48.3% of extractable)
   (Included in EXTRACTABLE but flagged for analysis)

❌ NO_DATA.list: 8,845 channels (74.1%)
   - Placeholders: 4,775 (54.0%) - includes 571 far-future dates
   - Inactive: 0 (0%)
   - No extraction: 4,070 (46.0%)
```

## Top Affected Providers (After Cleanup)

| Provider | Count | % of Total |
|----------|-------|------------|
| FLO ⱽᴵᴾ PPV | 655 | 43.9% |
| FLO SPORTS PPV | 116 | 7.8% |
| ESPN+ PPV ⱽᴵᴾ | 64 | 4.3% |
| STAN PPV | 62 | 4.2% |
| MAX PPV ⱽᴵᴾ | 57 | 3.8% |
| VIAPLAY PPV ⱽᴵᴾ | 51 | 3.4% |

**Note:** Victory+ and STAN placeholder channels (571 total) have been properly filtered out.

## Separator Patterns Found (After Cleanup)

| Pattern | Count | % | Notes |
|---------|-------|---|-------|
| `vs` | 385 | 25.8% | Should work but doesn't |
| `:` (colon) | 258 | 17.3% | Event title format |
| `-,:` (dash+colon) | 100 | 6.7% | Provider prefix issue |
| `vs,-,:` | 85 | 5.7% | Mixed separators |
| `vs,-` | 83 | 5.6% | Should work |
| `v` (single) | 44 | 2.9% | Not recognized |
| `-` (dash only) | 37 | 2.5% | Ambiguous |
| `v,:` | 29 | 1.9% | Single v with colon |
| `vs,:` | 20 | 1.3% | Should work |
| `x` | 16 | 1.1% | **Not supported!** |
| None found | 435 | 29.2% | True non-events or unknown patterns |

## Example Channels

### Should Be Extractable (vs/at/@)

```
UK: D+ PPV 1 - NORTHAMPTON SAINTS - HARLEQUINS | Sat 03 Jan 17:15
UK: DAZN PPV 7 - PROVIDENCE @ ST. JOHN'S | Sat 03 Jan 17:50
Flo (FLSP) 10: 2025 New Jersey Bears vs Pennsylvania Huntsmen - 22/10 11:30
Super League Plus | Event 1 Hull KR v St Helens // UK Sat 4 Oct 5:25pm
```

### Missing Pattern: "x" separator

```
MLB 1 | Dodgers x Blue Jays start:2025-11-02 12:00am Sun
ACB EVENTO 01 | Liga Endesa: Joventut Badalona x La Laguna TFE 17:50 h
```

### Event Titles (no competitors)

```
UEFA | 19 - Women's UCL Play Off Draw 12:00pm
PDC Board 3 : Players championship 34 board 4 // UK Thu 30 Oct 2:00pm
```

## Why Extraction Is Failing

### 1. Provider Prefix Interference

Channels like:
```
UK: DAZN PPV 7 - PROVIDENCE @ ST. JOHN'S | Sat 03 Jan 17:50
```

The extractor sees:
- `UK: DAZN PPV 7 -` as a prefix with dash
- Then looks for `PROVIDENCE @ ST. JOHN'S`
- But the dash pattern may be interfering with @ pattern

### 2. Missing "x" Separator

Common in Spanish/Portuguese content:
```
Liga Endesa: Joventut Badalona x La Laguna TFE 17:50 h
Dodgers x Blue Jays
```

The current `COMPETITOR_PATTERN` doesn't include "x" as a separator.

### 3. Single "v" Not Recognized

UK/Irish sports commonly use single "v":
```
Hull KR v St Helens
Motherwell v Queen's Park
```

The pattern requires "vs" or longer separators.

### 4. Event Titles vs Matchups

Some channels are legitimately event titles without team matchups:
```
Women's UCL Play Off Draw
Players championship 34 board 4
```

These are draws, tournaments, or board/table identifiers, not team matchups.

## Recommendations

### Immediate Fixes

1. **Add "x" separator** - Spanish/Portuguese standard
   ```python
   COMPETITOR_PATTERN = r"...|([A-Za-z0-9\s&\'-]+?)\s+x\s+([A-Za-z0-9\s&\'-]+?)..."
   ```

2. **Support single "v"** - UK/Irish sports
   ```python
   # But be careful: "v" appears in many words (victory, vs, etc.)
   # Need context: word boundaries and capitalized words nearby
   ```

3. **Improve dash handling** - Distinguish prefixes from separators
   - Pattern should skip dashes in "PPV 7 -" format
   - Look for dashes between capitalized words

### Analysis Tools Added

1. **export_ppv_from_db.py** - Export current database to PPV.list
2. **regenerate_ppv_lists.py** (updated) - Now tracks date_but_no_competitors
3. **analyze_date_but_no_competitors.py** - Pattern analysis tool

### Updated Files Generated

- `EXTRACTABLE.list` - 3,663 channels with extractable data
- `NO_DATA.list` - 8,274 channels with no extraction
- `DATE_BUT_NO_COMPETITORS.list` - 2,063 suspicious channels (subset of EXTRACTABLE)

## Impact

**Before Analysis:**
- Assumed "date but no competitors" = incomplete channel data
- ~17% of PPV channels in this category (including placeholder dates)

**After Placeholder Filtering:**
- Correctly identified 571 far-future placeholder dates (2098-12-31, 2099-01-01)
- Reduced suspicious channels from 2,063 to 1,492 (-27.7%)
- Now 12.5% of total channels, 48.3% of extractable channels

**After Analysis:**
- Many remaining channels are valid matchups with unrecognized patterns
- Estimated ~385+ channels (25.8%) have "vs" that should work
- Estimated ~16+ channels use "x" separator (not supported)
- Estimated ~44+ channels use single "v" (not supported)

**Potential Recovery:**
- Adding "x" support: +16 channels
- Fixing single "v": +44 channels
- Debugging "vs" failures: +385 channels
- **Total: ~445 additional extractable channels (29.8% improvement over current suspicious list)**

## Next Steps

1. ✅ **FIXED:** Far-future placeholder dates (2098-12-31, 2099-01-01) now properly filtered
2. **Fix extractor patterns** in `services/ppv_event_extractor.py` for "x" and "v" separators
3. **Add tests** for new separator patterns
4. **Re-run analysis** after fixes to measure improvement
5. **Document** remaining non-extractable cases (true event titles)

## Implementation: Placeholder Date Filtering

**Added to `services/ppv_event_extractor.py`:**

```python
# In is_date_far_future():
if event_date.year >= 2098:
    return True  # Common provider placeholder dates

# In extract_all() - early detection before other strategies:
iso_match = re.search(self.ISO_DATE_PATTERN, channel_name, re.IGNORECASE)
if iso_match:
    year = iso_match.group(1)
    if int(year) >= 2098:
        result["inferred_how"] = "date_too_far_future"
        return result
```

**Result:** 571 placeholder channels (Victory+, STAN) now correctly filtered as placeholders instead of being categorized as "date_but_no_competitors".

## Files

- Source data: [PPV.list](../PPV.list) - All PPV channels
- Extractable: [EXTRACTABLE.list](../EXTRACTABLE.list) - Channels with competitor or date
- No data: [NO_DATA.list](../NO_DATA.list) - Channels with no extraction
- Analysis target: [DATE_BUT_NO_COMPETITORS.list](../DATE_BUT_NO_COMPETITORS.list) - Suspicious cases

## Tools

```bash
# Export fresh data from database
python export_ppv_from_db.py

# Regenerate analysis files with statistics
python regenerate_ppv_lists.py

# Analyze date_but_no_competitors patterns
python analyze_date_but_no_competitors.py
```

## References

- [PPV Event Extraction Quick Start](PPV_EVENT_EXTRACTION_QUICK_START.md)
- [PPV Patterns Reference](PPV_PATTERNS_REFERENCE.md)
- Current extractor: [services/ppv_event_extractor.py](../services/ppv_event_extractor.py)
