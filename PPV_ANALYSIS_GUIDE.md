# PPV Channel Analysis Guide

## Current Status

**Total PPV Channels:** 11,937
- **EXTRACTABLE:** 986 (8.3%) - Channels with competitor/date data
- **NO_DATA:** 10,951 (91.7%) - Channels awaiting extraction improvement

## What's in NO_DATA.list?

The [NO_DATA.list](NO_DATA.list) contains channels that currently don't extract event data. This includes:

### 1. **Placeholders** (~4,400 channels)
Pattern: `"NO EVENT STREAMING"`, `"NO SCHEDULED EVENT"`
```
BR: MAX PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE
BR: NBA PASS PPV 2 - NO EVENT STREAMING - 8K EXCLUSIVE
CA: DAZN PPV 1 - NO EVENT STREAMING - | 8K EXCLUSIVE
```
*Status: Correctly filtered by `is_placeholder()` detection*

### 2. **Inactive Channels** (~1,300 channels)
Pattern: Provider names, generic headers, empty slots
```
(Fanatiz 012)
###########
::::::::::::
AFL TV 00
TSN+ 04 :
```
*Status: Correctly filtered by `is_inactive_channel()` detection*

### 3. **Unextractable Events** (~5,250 channels)
These are the interesting ones! They may contain:
- Real events with team names we're not catching
- Non-standard delimiters
- Non-English team names
- Alternative date formats
- Typos or abbreviations
- Multi-language content

## How to Help Improve Extraction

### Step 1: Search for Patterns
Open [NO_DATA.list](NO_DATA.list) and look for examples of:

**A. Team Matchups with Different Separators**
```
Team A - Team B          (dash/hyphen)
Team A ... Team B        (ellipsis)
Team A | Team B          (pipe)
Team A > Team B          (greater than)
Team A : Team B          (colon)
```

**B. Non-English Team Names**
```
Équipe A vs Équipe B     (French)
Équipo A vs Equipo B     (Spanish)
醫隊 A vs 醫隊 B         (Chinese)
```

**C. Alternative Date Formats**
```
27-Dec-2025 15:00        (DD-MMM-YYYY)
27/12/2025 15:00         (DD/MM/YYYY)
2025/12/27 15:00         (YYYY/MM/DD)
December 27, 2025 3 PM   (Full text)
```

**D. Unusual Abbreviations**
```
Team A v Team B          (v without s)
Team A -vs- Team B       (dashes around vs)
Team A x Team B          (x as separator)
```

### Step 2: Flag Examples

When you find patterns, please provide:
```
1. Full channel name from NO_DATA.list
2. What's being extracted (team names, dates, etc.)
3. What should be extracted
4. Pattern description (separator, format, language, etc.)
```

### Step 3: Example Format

**Pattern Found: Hyphen Separator**
```
Example: "TEAM A - TEAM B | Dec 27 15:00"
Current: Not extracted (pattern uses "-" not "vs")
Should Extract: Teams: ("TEAM A", "TEAM B"), Date: 2025-12-27 15:00
Pattern: Teams separated by single hyphen with spaces around it
Count: Need to verify how many channels use this
```

## Current Test Coverage

The following patterns are **already tested and working:**
- ✅ vs / VS / vs. / VS. (competitors)
- ✅ at / AT / at. / AT. (competitors)
- ✅ @ symbol (competitors)
- ✅ versus (competitors)
- ✅ Multi-word team names (SAN DIEGO STATE)
- ✅ ISO date format: YYYY-MM-DD HH:MM
- ✅ Month Day Time format: Dec 27 15:00
- ✅ Weekday inference: Sat 27 Dec 15:00
- ✅ Ranking prefixes: #25, #22
- ✅ Team abbreviations: BYU, MH, SPO (2-3 chars)
- ✅ Special chars in names: &, ', -

## Quick Stats

Run this to get counts of potential patterns:

```bash
# Count channels with specific separators in NO_DATA
grep -c " - " NO_DATA.list       # Hyphen separator
grep -c " | " NO_DATA.list       # Pipe separator
grep -c " : " NO_DATA.list       # Colon separator
grep -c " . " NO_DATA.list       # Period separator
```

## Files for Reference

- **[EXTRACTABLE.list](EXTRACTABLE.list)** - 986 successfully extracted channels
- **[NO_DATA.list](NO_DATA.list)** - 10,951 channels needing analysis
- **[tests/test_ppv_event_extractor.py](tests/test_ppv_event_extractor.py)** - 56 test cases

## Adding New Patterns

Once you identify a pattern, here's how to add it:

1. **Update regex pattern** in `services/ppv_event_extractor.py`:
   ```python
   COMPETITOR_PATTERN = r"..."  # Add new separator
   ```

2. **Add test case** in `tests/test_ppv_event_extractor.py`:
   ```python
   def test_extract_competitors_hyphen_separator(self):
       result = self.extractor.extract_competitors("TEAM A - TEAM B")
       assert result == ("TEAM A", "TEAM B")
   ```

3. **Regenerate lists**:
   ```bash
   python extract_ppv.py
   ```

4. **Run tests**:
   ```bash
   pytest tests/test_ppv_event_extractor.py -v
   ```

## Expected Improvements

Based on patterns observed in NO_DATA, we estimate:
- **50-100+ more channels** from non-standard separators
- **100-200+ more channels** from alternative date formats
- **50-100+ more channels** from multi-language support
- **Potential total: 1,100-1,200+ extractable channels**

This aligns with your estimate of ~1,220 real events! 🎯
