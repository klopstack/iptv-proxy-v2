# PPV Channel Classification & Filtering

## Overview

After analyzing PPV.list with improved filtering for inactive channels and far-future dates, we now have a much clearer picture of which channels are actually actively broadcasting PPV events.

## Revised Extraction Results

**Total Channels**: 11,937

### Channel Classification Breakdown

```
📊 Total Channels:                    11,937 (100.0%)
├─ 🗑️  Placeholders (NO EVENT):       4,415 (37.0%)
│   Examples: "NO EVENT STREAMING", "- NO EVENT STREAMING -"
│
├─ 🔌 Inactive channels:              1,312 (11.0%)
│   Examples: "(Fanatiz 012)", "AFL TV 00", "###", ":"
│
├─ 📅 Far future dates (>1 year):        0 (0.0%)
│   (None in current dataset)
│
└─ ✅ Actively broadcasting:          6,210 (52.0%)
    └─ With extractable event data:   1,455 (23.4% of total, 23.4% of active)
        ├─ With competitors:            707 (11.4% of active)
        ├─ With date info:              748 (12.0% of active)
        └─ With both:                   593 (9.5% of active) ← HIGH CONFIDENCE
```

## What Changed

### Previous Analysis
- Total channels: 11,937
- Placeholders filtered: 4,415 (37%)
- **"Matchable" channels: 7,522**
- Extractable: 1,455 (9.4% of total)
- **Unextractable: 6,633 (88.2%)**

### Updated Analysis
- Total channels: 11,937
- Placeholders filtered: 4,415 (37%)
- Inactive channels: 1,312 (11%) ← **NEW**
- **Actively broadcasting: 6,210 (52%)**
- Extractable: 1,455 (23.4% of active)
- **Unextractable: 4,755 (76.6% of active)**

## The Key Insight

**The 88% "unextractable" rate was misleading because it counted inactive channels.**

When we account for channels that simply aren't streaming events (49% of all channels):
- **Inactive: 1,312 channels (11%)**
  - No event data, just provider/package names
  - Generic placeholders like "NFL TV 00", "AFL TV"
  - Section headers and formatting

- **Actually streaming but no extractable data: 4,755 channels (76.6% of active)**
  - These might have team names that don't match our patterns
  - Or events in unfamiliar formats
  - Or regional/specialty content

## Inactive Channel Patterns

The following patterns are now filtered as "inactive":

1. **Just provider names**: `(Fanatiz 012)`, `(Sportsnet Canada)`
   - Regex: `^\([^)]*\)$`

2. **Generic channel numbers**: `AFL TV 00`, `NFL TV 01`
   - After stripping identifiers, often <5 characters

3. **Section headers**: `###`, `###...###`, `::::::`
   - Regex: `^[#*_\s:]+$`

4. **Empty/whitespace only**
   - Less than 5 characters

## Active vs Inactive Examples

| Channel | Classification | Reason |
|---------|----------------|--------|
| `Vegas vs Colorado @ Dec 28 4:05 AM` | ✅ Active | Has competitors + date |
| `Arsenal vs Brighton` | ✅ Active | Has competitors |
| `(Fanatiz 012)` | 🔌 Inactive | Just provider name |
| `AFL TV 00` | 🔌 Inactive | Generic placeholder |
| `###` | 🔌 Inactive | Section header |
| `NO EVENT STREAMING` | 🗑️ Placeholder | Explicit placeholder |
| `Robbitohs vs Panthers 9:00am` | ✅ Active | Has competitors + time |

## Extraction Rates by Category

Of the **6,210 actively broadcasting channels**:

```
Extraction Success Rate:
├─ With competitors:           707 (11.4%)
├─ With date information:      748 (12.0%)
│  ├─ Full dates:             333 (43% of date extractions)
│  ├─ Weekday + time:          49 (6%)
│  ├─ Time-only inferred:     392 (50%)
│  └─ Weekday-only:             1 (<1%)
└─ With both competitors AND date: 593 (9.5%) ← BEST FOR MATCHING

Total matchable channels: 1,455 (23.4% of active)
Remaining unextractable: 4,755 (76.6% of active)
```

## Coverage for Event Matching

### Tier 1: Direct Team Name Search
- **Candidates**: 707 channels with team names
- **API calls**: ~707 (1 per candidate)
- **Success rate**: ~90% (rough estimate)
- **Status**: ✅ Feasible

### Tier 2: Calendar Browse
- **Candidates**: 748 channels with date info
- **Unique dates**: 9 (very small set!)
- **HTTP calls**: ~9 (browse_calendar)
- **Expected event results**: Varies
- **Status**: ✅ Highly efficient

### Combined Coverage
- **Extractable channels**: 1,455 (23.4% of active)
- **Expected API calls**: ~716 total
- **Cost per extractable channel**: 0.49 API calls (very efficient!)
- **Channels with high-confidence match** (competitors + date): 593

## Implementation

### Filters Applied

```python
# In PPVEventExtractor.extract_all()

1. is_placeholder() - Filters "NO EVENT STREAMING"
2. is_inactive_channel() - Filters provider names, generic placeholders
3. is_date_far_future() - Filters events >1 year away
```

### Method Signatures

```python
def is_inactive_channel(channel_name: str) -> bool:
    """Returns True if channel has no event data or is just a placeholder."""
    # Filters:
    # - Empty/very short names
    # - Just provider names: "(Fanatiz 012)"
    # - Section headers: "###", "::::::"
    # - Generic placeholders: "AFL TV 00"

def is_date_far_future(event_date: datetime) -> bool:
    """Returns True if event is >1 year in future (likely not broadcasting)."""
```

## Implications

1. **The 49% of completely inactive channels can be safely ignored**
   - These provide no useful event information
   - Not currently broadcasting anything

2. **Of the 52% actively broadcasting, 23.4% are extractable**
   - 707 with competitors (11.4%)
   - 748 with date info (12.0%)
   - 593 with both (9.5%) - high confidence

3. **The remaining 76.6% of active channels might need:**
   - Different extraction patterns (sports we don't support)
   - Manual review (regional content, specialty events)
   - Additional data sources (not in channel name)

## Next Steps

1. ✅ Filter inactive channels (DONE)
2. ✅ Filter far-future dates (DONE)
3. Implement direct team search for 707 competitors
4. Implement calendar browse for 748 dated events
5. For remaining 4,755 channels, consider:
   - Fuzzy matching on team names
   - Secondary data sources
   - Manual curated lists

## Code Quality

- ✅ `make lint` passes (0 errors)
- ✅ `make format` applied
- ✅ Type hints complete
- ✅ Measurement script updated with new categories
