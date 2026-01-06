# PPV Analysis Scripts

This folder contains scripts for analyzing PPV enrichment and matching performance.

## Scripts

### `analyze_matching_stats.py`
Shows overall statistics about PPV matching:
- Total channels analyzed
- Successfully matched channels (with confidence breakdown)
- Channels with extracted competitors but no match
- Channels with no competitors extracted
- Events in database with no channel matches

**Usage:**
```bash
python scripts/analyze_matching_stats.py [--account-id ID] [--min-confidence 0.35]
```

### `show_matched_channels.py`
Lists all successfully matched channels with their match details.

**Usage:**
```bash
python scripts/show_matched_channels.py [--account-id ID] [--min-confidence 0.35] [--output CSV|JSON|TABLE]
```

### `show_unmatched_channels.py`
Lists channels that failed to match, grouped by reason:
- Had competitors but no match found
- No competitors extracted
- Date extraction failed

**Usage:**
```bash
python scripts/show_unmatched_channels.py [--account-id ID] [--reason all|no-competitors|no-match|no-date]
```

### `show_unmatched_events.py`
Lists events in the database that haven't been matched to any channels.

**Usage:**
```bash
python scripts/show_unmatched_events.py [--min-age-days 0] [--max-age-days 30]
```

### `analyze_match_patterns.py`
Analyzes patterns in successful and failed matches to identify improvement opportunities.

**Usage:**
```bash
python scripts/analyze_match_patterns.py [--account-id ID]
```

### `analyze_non_vs_events.py`
Analyzes unmatched PPV channels to identify non-vs events and placeholders.

Categorizes channels by type:
- **Placeholder**: Generic numbered channels or section headers (e.g., "EVENT 1-10", "#####HEADER#####", "NO EVENT STREAMING")
- **Tournament/League**: League matches and tournament series
- **Highlight/Recap**: Post-match highlights and replays
- **Documentary**: Documentaries and specials
- **Show/Program**: Talk shows, news, commentary
- **Training**: Practices, press conferences, friendlies
- **Player**: Player profiles and interviews
- **Other**: Likely vs events that didn't match

**Placeholder detection:**
- Channels starting with `#` (section headers)
- Channels explicitly marked "NO EVENT STREAMING"
- Channels with 2+ entries sharing same base name but different numbers (e.g., "DAZN PPV 1", "DAZN PPV 2")

**Usage:**
```bash
# Show all categories with examples
python scripts/analyze_non_vs_events.py

# Filter by account
python scripts/analyze_non_vs_events.py --account-id 5

# Hide examples (just show counts)
python scripts/analyze_non_vs_events.py --no-examples
```

**Output includes:**
- Count and percentage of each category
- Example channels for each category
- Recommendations for improving matching or filtering

**Example findings from database:**
```
Placeholder channels:  6,894 ( 58.3%)  ← Generic/numbered/empty
Likely vs events:      4,549 ( 38.5%)  ← Should match but didn't
Likely non-vs:           387 (  3.3%)  ← Real non-event content
```

### `rerun_matching.py`
Re-runs PPV channel matching. Useful after:
- Improving matching algorithms
- Adding new events to the database
- Fixing text extraction issues

**Usage:**
```bash
# Dry run (shows what would happen)
python scripts/rerun_matching.py [--account-id ID] [--clear-existing]

# Actually run matching
python scripts/rerun_matching.py --execute [--account-id ID] [--clear-existing]

# Re-run for specific account, keeping existing matches
python scripts/rerun_matching.py --account-id 5 --execute

# Clear all existing matches and re-match from scratch
python scripts/rerun_matching.py --clear-existing --execute
```

**Options:**
- `--account-id ID` - Re-match only specific account (default: all accounts)
- `--clear-existing` - Clear existing matches before re-matching (default: keeps and adds new)
- `--execute` - Actually run matching (default is dry run)

### `cleanup_old_events.py`
Removes old/stale events from the database to prevent incorrect matches to historical events.

**Usage:**
```bash
# Dry run (shows what would be deleted)
python scripts/cleanup_old_events.py [--max-age-days 30]

# Actually delete
python scripts/cleanup_old_events.py --execute [--max-age-days 30]
```

## Environment Setup

These scripts use the same database and configuration as the main application:

```bash
export DATABASE_URL="sqlite:////app/data/iptv_proxy.db"  # or your path
python scripts/analyze_matching_stats.py
```

## Typical Workflow

1. **Get an overview of matching performance:**
   ```bash
   python scripts/analyze_matching_stats.py
   ```

2. **Clean up old events that might cause incorrect matches:**
   ```bash
   python scripts/cleanup_old_events.py  # dry run first
   python scripts/cleanup_old_events.py --execute
   ```

3. **Investigate unmatched channels that should have matches:**
   ```bash
   python scripts/show_unmatched_channels.py --reason no-match | head -100
   ```

4. **Review events that have no channel matches:**
   ```bash
   python scripts/show_unmatched_events.py
   ```

5. **Analyze match quality patterns:**
   ```bash
   python scripts/analyze_match_patterns.py
   ```

6. **Export matched channels for external analysis:**
   ```bash
   python scripts/show_matched_channels.py --output csv > matches.csv
   ```
