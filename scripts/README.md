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
