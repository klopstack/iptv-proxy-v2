# TheSportsDB Integration - Quick Start Guide

## Installation & Setup

### 1. Apply Database Migration
```bash
python run_migrations.py
# Creates thesportsdb_id column in channels table
```

### 2. Import the Service
```python
from services.thesportsdb_service import get_thesportsdb_service

service = get_thesportsdb_service()
```

---

## Common Operations

### Get Upcoming Events
```python
# Premier League upcoming events
events = service.get_next_league_events("133602", max_events=50)

for event in events:
    print(f"{event['strEvent']}")
    print(f"  Date: {event['dateEvent']} at {event['strTime']}")
    print(f"  Venue: {event['strVenue']}")
```

### Match PPV Channel to Event
```python
# Try to match a channel name to a real event
ppv_channel_name = "Arsenal vs Chelsea - PPV"
match = service.match_channel_to_event(ppv_channel_name)

if match:
    print(f"✓ Matched to: {match['strEvent']}")
    print(f"  Event ID: {match['idEvent']}")
else:
    print("✗ No matching event found")
```

### Find Events by Date
```python
# Get all events on a specific date
events = service.find_events_for_date("2026-01-04")
print(f"Found {len(events)} events on that date")

for event in events:
    print(f"  {event['strEvent']} at {event['strTime']}")
```

### Check Event Status
```python
# Check if event is live
if service.is_event_live(event):
    print("🔴 Event is LIVE")

# Check if event is upcoming within 24 hours
if service.is_event_upcoming(event, hours_ahead=24):
    print("⏰ Event is upcoming")
```

### Get League Information
```python
# Get league details
league = service.get_league_info("133602")
if league:
    print(f"League: {league['strLeague']}")
    print(f"Country: {league['strCountry']}")
    print(f"Sport: {league['strSport']}")
    print(f"Founded: {league['intFormedYear']}")
```

### Get Teams in League
```python
# Get all teams in a league
teams = service.get_league_teams("133602", max_teams=20)
for team in teams:
    print(f"{team['strTeam']} ({team['strCountry']})")
```

---

## Database Integration

### Store Event ID on Channel
```python
from models import Channel, db

# Find PPV channel
channel = Channel.query.filter_by(is_ppv=True, name="Arsenal vs Chelsea PPV").first()

# Match to TheSportsDB event
match = service.match_channel_to_event(channel.name)
if match:
    # Store the event ID
    channel.thesportsdb_id = match['idEvent']
    db.session.commit()
    print(f"✓ Channel linked to TheSportsDB event {match['idEvent']}")
```

### Retrieve Stored Event Details
```python
from models import Channel

channel = Channel.query.get(channel_id)
if channel.thesportsdb_id:
    # Get full event details
    event = service.get_event_by_id(channel.thesportsdb_id)
    if event:
        print(f"Event: {event['strEvent']}")
        print(f"Status: {event['strStatus']}")
else:
    print("Channel has no matched event")
```

---

## League ID Quick Reference

```python
COMMON_LEAGUES = {
    # English
    "133602": "English Premier League",
    "4396": "English League 1",
    "4397": "English League 2",
    "4399": "Championship",
    
    # European
    "775": "Spanish La Liga",
    "783": "Italian Serie A",
    "780": "German Bundesliga",
    "772": "French Ligue 1",
    
    # Other
    "133602": "UEFA Champions League",
}

# Usage:
events = service.get_next_league_events("133602")  # Premier League
```

---

## Response Fields

### Event Fields
- `idEvent` - Unique event ID
- `strEvent` - Event name (e.g., "Arsenal vs Chelsea")
- `dateEvent` - Date (YYYY-MM-DD)
- `strTime` - Time (HH:MM:SS)
- `strTimestamp` - ISO 8601 timestamp (with Z suffix)
- `strHomeTeam` - Home team name
- `strAwayTeam` - Away team name
- `strLeague` - League name
- `strSport` - Sport type (Soccer, etc.)
- `strStatus` - Status (Not Started, In Progress, Finished)
- `strPostponed` - "yes" or "no"
- `strVenue` - Stadium/venue name

### League Fields
- `idLeague` - League ID
- `strLeague` - League name
- `strCountry` - Country
- `strSport` - Sport type
- `intFormedYear` - Year founded

### Team Fields
- `idTeam` - Team ID
- `strTeam` - Team name
- `strCountry` - Country
- `strLeague` - League name
- `strSport` - Sport type

---

## Error Handling

```python
# Methods return empty lists/None on error (no exceptions)
events = service.get_next_league_events("invalid_id")  # Returns []
league = service.get_league_info("invalid_id")  # Returns None

# Check for success:
if events:
    print(f"✓ Got {len(events)} events")
else:
    print("✗ Failed to retrieve events")
```

---

## Performance Tips

### 1. Batch Processing
```python
# Good: Limit results
events = service.get_next_league_events("133602", max_events=10)

# Better: Process in batches
for league_id in league_ids:
    events = service.get_next_league_events(league_id, max_events=20)
    # Process...
```

### 2. Caching
```python
# Cache results in your application
from functools import lru_cache

@lru_cache(maxsize=32)
def get_cached_league_info(league_id):
    service = get_thesportsdb_service()
    return service.get_league_info(league_id)
```

### 3. Date-Based Search Instead of Listing All
```python
# Efficient: Search by date
events = service.find_events_for_date("2026-01-04")

# Less efficient: Get all then filter
all_events = service.get_next_league_events("133602", max_events=1000)
filtered = [e for e in all_events if e['dateEvent'] == "2026-01-04"]
```

---

## Testing

```bash
# Run all tests
pytest tests/test_thesportsdb_service.py -v

# Run specific test class
pytest tests/test_thesportsdb_service.py::TestMatchChannelToEvent -v

# Run with coverage
pytest tests/test_thesportsdb_service.py --cov=services.thesportsdb_service
```

---

## Troubleshooting

### No events returned
- Check league ID is valid: `service.get_league_info(league_id)`
- Try a known league (133602 = Premier League)
- Verify date range (API may only return upcoming events)

### Channel not matching to events
- Channel name must contain both team names
- Matching is case-insensitive
- Try exact event name: `"Arsenal vs Chelsea"` instead of `"Arsenal vs Chelsea - PPV"`

### API not responding
- Check internet connection
- TheSportsDB may have rate limits on free tier
- Try again after a few seconds

---

## Full API Reference

| Method | Returns | Description |
|--------|---------|-------------|
| `get_next_league_events(league_id, max_events=50)` | List[Dict] | Upcoming events |
| `get_league_season_events(league_id, season, max_events=100)` | List[Dict] | Seasonal events |
| `get_event_by_id(event_id)` | Dict\|None | Event details |
| `get_league_info(league_id)` | Dict\|None | League info |
| `get_league_teams(league_id, max_teams=50)` | List[Dict] | Teams in league |
| `match_channel_to_event(channel_name, league_id=None)` | Dict\|None | Matched event |
| `find_events_for_date(date_str, league_id=None)` | List[Dict] | Events on date |
| `is_event_live(event)` | bool | Currently playing |
| `is_event_upcoming(event, hours_ahead=24)` | bool | Scheduled soon |
| `clear_cache()` | None | Clear service cache |

---

## Links

- **Full Documentation:** `docs/THESPORTSDB_INTEGRATION.md`
- **Implementation Summary:** `docs/THESPORTSDB_IMPLEMENTATION_SUMMARY.md`
- **Test Suite:** `tests/test_thesportsdb_service.py`
- **Source Code:** `services/thesportsdb_service.py`
- **TheSportsDB:** https://www.thesportsdb.com/

---

**Ready to use!** Start with the basic examples above and refer to the full documentation for advanced usage.
