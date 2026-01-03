# PPV Event Extraction - Quick Start Guide

## Overview

This guide shows how to use the PPV event extraction and matching system to:
1. Extract event metadata from PPV channel names
2. Match channels to TheSportsDB events
3. Store matches in the database for EPG building

## Basic Usage

### 1. Extract Event Metadata from a Channel Name

```python
from services.ppv_event_extractor import PPVEventExtractor

extractor = PPVEventExtractor()

# Extract all info from a channel
channel = "Arsenal vs Brighton @ Dec 27 3:55 PM :Viaplay SE  10"
data = extractor.extract_all(channel)

print(data)
# {
#     'is_placeholder': False,
#     'competitors': ('Arsenal', 'Brighton'),
#     'date': datetime(2026, 12, 27, 15, 55),
#     'weekday': None,
#     'raw_name': "Arsenal vs Brighton @ Dec 27 3:55 PM :Viaplay SE  10"
# }
```

### 2. Check Individual Components

```python
# Check if channel is a placeholder (skip these)
if extractor.is_placeholder(channel_name):
    print("Skip this channel (no event)")

# Extract just competitors
competitors = extractor.extract_competitors(channel_name)
if competitors:
    home, away = competitors
    print(f"Teams: {home} vs {away}")

# Extract date/time
event_date = extractor.extract_date(channel_name)
if event_date:
    print(f"Event: {event_date.isoformat()}")
```

### 3. Match to TheSportsDB Events

```python
from services.ppv_event_extractor import EventMatcher
from services.thesportsdb_service import TheSportsDBService

# Initialize services
thesportsdb = TheSportsDBService()
matcher = EventMatcher(thesportsdb)

# Try to match
channel_name = "Arsenal vs Brighton @ Dec 27 3:55 PM"
result = matcher.match(channel_name)

if result:
    print(f"Found event: {result['event_id']}")
    print(f"Confidence: {result['confidence']}")
    print(f"Method: {result['method']}")
else:
    print("No match found")

# Result structure:
# {
#     'event_id': '123456',
#     'confidence': 0.95,
#     'method': 'direct_search',  # or 'calendar_browse'
#     'home_team': 'Arsenal',
#     'away_team': 'Brighton'
# }
```

### 4. Batch Analysis (Measure Extraction Quality)

```python
# Analyze a batch of channels
channels = [
    "Arsenal vs Brighton @ Dec 27 3:55 PM",
    "Chelsea vs Aston Villa @ Dec 27 6:25 PM",
    "NO EVENT STREAMING - PLACEHOLDER",
    "Random Channel Name",
]

stats = matcher.analyze_batch(channels)

print(f"Total: {stats['total']}")
print(f"Placeholders: {stats['placeholders']}")
print(f"Matched: {len(stats['matches'])}")
print(f"Failed: {len(stats['failures'])}")

# Also see:
# stats['matched_direct']
# stats['matched_calendar']
# stats['matches'] - list of successful matches
# stats['failures'] - list of channel names that couldn't be matched
```

## Integration with Database

### 1. Import Models

```python
from models import Event, EventChannelLink, Channel, db
from services.ppv_event_extractor import EventMatcher
from services.thesportsdb_service import TheSportsDBService
from datetime import datetime, UTC
```

### 2. Create Event Record

```python
# After matching, create Event record
def save_matched_event(event_data_from_thesportsdb):
    """Save a TheSportsDB event to our database"""
    
    # Check if event already exists
    existing = Event.query.filter_by(
        external_id=event_data_from_thesportsdb['idEvent']
    ).first()
    
    if existing:
        return existing
    
    # Create new event
    event = Event(
        external_id=event_data_from_thesportsdb['idEvent'],
        source=Event.SOURCE_THESPORTSDB,
        sport=event_data_from_thesportsdb.get('strSport', 'Unknown'),
        league_name=event_data_from_thesportsdb.get('strLeague'),
        home_team_id=event_data_from_thesportsdb.get('idHomeTeam'),
        home_team_name=event_data_from_thesportsdb['strHomeTeam'],
        away_team_id=event_data_from_thesportsdb.get('idAwayTeam'),
        away_team_name=event_data_from_thesportsdb['strAwayTeam'],
        scheduled_at=datetime.fromisoformat(
            event_data_from_thesportsdb['dateEvent'] + 'T' + 
            event_data_from_thesportsdb.get('strTime', '00:00:00')
        ),
        venue_name=event_data_from_thesportsdb.get('strVenue'),
        city=event_data_from_thesportsdb.get('strCity'),
        home_team_badge=event_data_from_thesportsdb.get('strHomeTeamBadge'),
        away_team_badge=event_data_from_thesportsdb.get('strAwayTeamBadge'),
        data_completeness='complete',
    )
    
    db.session.add(event)
    db.session.commit()
    return event
```

### 3. Link Channel to Event

```python
def link_channel_to_event(channel_id, event_id, match_result):
    """Create link between channel and event after successful match"""
    
    # Check if link already exists
    existing = EventChannelLink.query.filter_by(
        channel_id=channel_id,
        event_id=event_id
    ).first()
    
    if existing:
        return existing
    
    # Create new link
    link = EventChannelLink(
        channel_id=channel_id,
        event_id=event_id,
        feed_type='primary',  # Can be: primary, alternate, hd, sd, regional_variant
        region=extract_region_from_channel(channel_id),  # SE, NO, DK, FI, etc.
        provider=extract_provider_from_channel(channel_id),  # Viaplay, TeliaPlay, etc.
        match_confidence=match_result['confidence'],
        match_method=match_result['method'],  # direct_search or calendar_browse
    )
    
    db.session.add(link)
    db.session.commit()
    return link
```

### 4. Complete Batch Matching Workflow

```python
def match_all_ppv_channels():
    """
    Complete workflow: extract, match, and store all PPV channels
    """
    from services.ppv_event_extractor import EventMatcher
    from services.thesportsdb_service import TheSportsDBService
    
    thesportsdb = TheSportsDBService()
    matcher = EventMatcher(thesportsdb)
    
    # Get all PPV channels
    ppv_channels = Channel.query.filter_by(is_ppv=True).all()
    
    stats = {
        'total': len(ppv_channels),
        'placeholders': 0,
        'matched_direct': 0,
        'matched_calendar': 0,
        'already_matched': 0,
        'unmatched': 0,
        'errors': [],
    }
    
    for channel in ppv_channels:
        try:
            # Skip if already matched
            if channel.thesportsdb_id:
                stats['already_matched'] += 1
                continue
            
            # Try to match
            match_result = matcher.match(channel.name)
            
            if not match_result:
                stats['unmatched'] += 1
                continue
            
            # Get event details from TheSportsDB
            event_data = thesportsdb.get_event_details(
                match_result['event_id']
            )
            
            if not event_data:
                stats['unmatched'] += 1
                continue
            
            # Save event
            event = save_matched_event(event_data)
            
            # Link channel to event
            link = link_channel_to_event(
                channel.id,
                event.id,
                match_result
            )
            
            # Update channel with thesportsdb_id
            channel.thesportsdb_id = event.external_id
            db.session.commit()
            
            # Track success
            if match_result['method'] == 'direct_search':
                stats['matched_direct'] += 1
            else:
                stats['matched_calendar'] += 1
                
        except Exception as e:
            stats['errors'].append({
                'channel': channel.name,
                'error': str(e),
            })
    
    return stats
```

## Practical Examples

### Example 1: Quick Channel Check

```python
from services.ppv_event_extractor import PPVEventExtractor

extractor = PPVEventExtractor()

channels_to_check = [
    "Arsenal vs Brighton @ Dec 27 3:55 PM :Viaplay SE",
    "Chelsea vs Aston Villa",
    "NO EVENT STREAMING - PLACEHOLDER",
    "Random PPV Channel",
]

for channel in channels_to_check:
    data = extractor.extract_all(channel)
    
    if data['is_placeholder']:
        print(f"⏭️  SKIP: {channel}")
    elif data['competitors'] or data['date']:
        print(f"✅ EXTRACT: {data['competitors']} @ {data['date']}")
    else:
        print(f"❌ FAIL: {channel}")
```

### Example 2: Matching a Single Channel

```python
from services.ppv_event_extractor import EventMatcher
from services.thesportsdb_service import TheSportsDBService

thesportsdb = TheSportsDBService()
matcher = EventMatcher(thesportsdb)

# Real PPV channel from your list
channel = "Vegas vs Colorado @ Dec 28 4:05 AM :Viaplay SE  25"

result = matcher.match(channel)

if result:
    print(f"✅ MATCHED!")
    print(f"   Event ID: {result['event_id']}")
    print(f"   Teams: {result.get('home_team')} vs {result.get('away_team')}")
    print(f"   Confidence: {result['confidence']:.0%}")
    print(f"   Method: {result['method']}")
else:
    print("❌ No match found")
```

### Example 3: Analyzing Full PPV List

```bash
# Run the measurement script
python measure_ppv_extraction.py

# Shows:
# - Total channels: 11,937
# - Placeholders: 4,415 (37.0%)
# - With competitors: 706 (9.4%)
# - With dates: 333 (4.4%)
# - Top competitor pairs
# - API cost analysis
```

## Performance Notes

### Extraction Speed
- ~50,000 channels/second on typical hardware
- All regex-based, no I/O
- Full PPV.list (11,937 channels) processes in <0.1 second

### API Costs
- Tier 1 (direct search): 1 API call per extracted event
- Tier 2 (calendar): 1 HTTP call per unique date (typically 4-10)
- TheSportsDB limit: 500 calls/day, can rate-limit to 50/hour

### Database Queries
- Event lookup: O(1) via external_id index
- Channel-Event link: O(1) via composite index
- Regional feeds: Fast with indexed queries

## Troubleshooting

### "No competitors extracted from channel"
- Channel name doesn't have "vs" or "@"
- Team names contain metadata (PPV, HD, etc.)
- Check output of `extractor.extract_all(channel)`

### "Match found but no event details"
- TheSportsDB API error or rate limit
- Event ID may be invalid
- Try adding logging to thesportsdb_service calls

### "Already matched channels reported as new"
- Channel.thesportsdb_id field not updated
- Check that database commit succeeded
- Verify Event record was created

## Configuration

### Confidence Thresholds
```python
# In your matching code, filter by confidence:
if result and result['confidence'] >= 0.9:
    # High confidence, safe to use
    save_match(result)
elif result and result['confidence'] >= 0.75:
    # Medium confidence, review before using
    flag_for_review(result)
else:
    # Low confidence, skip
    skip_match(result)
```

### Date Range Filters
```python
# Only match events within 30 days
from datetime import datetime, UTC, timedelta

def should_match_event(event_date):
    now = datetime.now()
    thirty_days = now + timedelta(days=30)
    return now <= event_date <= thirty_days

# In match workflow:
if should_match_event(match_result.get('date')):
    process_match(match_result)
```

---

**Status:** ✅ Ready to integrate with your application
