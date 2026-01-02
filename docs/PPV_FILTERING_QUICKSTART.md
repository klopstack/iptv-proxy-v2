# PPV Filtering Implementation - Quick Start Guide

This guide helps you implement the PPV filtering system step-by-step.

## Documents to Read (in order)

1. **[PPV_FILTERING_ANALYSIS.md](../PPV_FILTERING_ANALYSIS.md)** (5 min) - Executive summary
2. **[PPV_FILTERING_SUMMARY.md](PPV_FILTERING_SUMMARY.md)** (10 min) - Problem & solution overview  
3. **[PPV_FILTERING_DESIGN.md](PPV_FILTERING_DESIGN.md)** (30 min) - Full technical design
4. **[PPV_PATTERNS_REFERENCE.md](PPV_PATTERNS_REFERENCE.md)** (reference) - Provider patterns library

## Code Starting Point

**Existing:** [services/ppv_filter_service.py](../../services/ppv_filter_service.py)
- ✅ Core filtering logic (100% complete)
- ✅ Datetime extraction & parsing (100% complete)
- ✅ Event metadata generation (100% complete)
- ✅ Test suite (6/6 tests passing)
- ✅ Predefined rules for 5 major US providers
- 🔲 **Not yet:** Database integration, caching, admin UI

---

## Implementation Timeline

### Week 1: Core Backend

**Day 1-2: Database Setup**
```python
# 1. Create PPVEventFilter model (models.py)
class PPVEventFilter(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(255), unique=True)
    provider_name = db.Column(db.String(100))
    filter_type = db.Column(db.String(50))  # ISO_DATETIME, TEXT_BASED, etc.
    date_field_pattern = db.Column(db.String(500))
    placeholder_date = db.Column(db.String(50))
    placeholder_text = db.Column(db.String(500))
    always_show_pattern = db.Column(db.String(500))
    enabled = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)

# 2. Create migration file
# migrations/2025_XX_add_ppv_event_filter.py
```

**Day 2-3: Integration & Testing**
```python
# 1. Update FilterService to use PPVFilterService
class FilterService:
    def apply_filters(self, channels):
        # ... existing code ...
        
        # NEW: Apply PPV filtering early
        channels = self.apply_ppv_filter(channels, account_id)
        
        # ... rest of filters ...
    
    def apply_ppv_filter(self, channels, account_id):
        ppv_service = PPVFilterService(db)
        filtered = []
        for channel in channels:
            rule = PPVEventFilter.query.filter_by(
                category=channel.category
            ).first()
            should_show, event_meta = ppv_service.should_show_channel(
                channel.name, channel.category, rule.to_dict() if rule else None
            )
            if should_show:
                # Store event metadata for EPG generation
                if event_meta:
                    cache_event_metadata(channel.id, event_meta)
                filtered.append(channel)
        return filtered

# 2. Write integration tests
pytest tests/test_ppv_filtering_integration.py
```

**Day 3-4: Caching**
```python
# 1. Add simple Redis/in-memory caching
class PPVFilterService:
    def __init__(self, db=None, cache=None):
        self.cache = cache or {}  # Simple dict cache for MVP
    
    def should_show_channel(self, channel_name, category, rule):
        cache_key = f"ppv:{category}:{hash(channel_name)}"
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        result = self._compute_visibility(channel_name, category, rule)
        self.cache[cache_key] = result
        return result
```

### Week 2: Testing & UI

**Day 5-6: Comprehensive Testing**
```bash
# 1. Create test file: tests/test_ppv_filtering.py
# - Unit tests for each filter type
# - Integration tests (full pipeline)
# - Performance tests (1K, 10K channels)
# - Edge case tests

pytest tests/test_ppv_filtering.py -v --cov=services.ppv_filter_service

# 2. Seed test data in database
# Create fixtures with sample channels from each provider
```

**Day 7: Admin UI**
```python
# 1. New routes in app.py
@app.route('/api/ppv-filters', methods=['GET', 'POST'])
def manage_ppv_filters():
    """CRUD for PPV filter rules"""

@app.route('/api/ppv-filters/<category>/test', methods=['POST'])
def test_ppv_filter(category):
    """Test a filter against sample channel names"""

# 2. New template: templates/admin/ppv_filters.html
# - List all rules with enable/disable
# - Test interface (paste channel name, see result)
# - Edit modal for each rule
```

### Week 3: Documentation & Rollout

**Day 8-9: Documentation & Beta**
```bash
# 1. Create user-facing documentation
# docs/PPV_CHANNEL_FILTERING_USER_GUIDE.md

# 2. Announce beta testing
# - Send to select power users
# - Gather feedback on accuracy
# - Monitor error logs

# 3. Adjust patterns based on feedback
```

**Day 10: Production Rollout**
```bash
# 1. Feature flag (disable by default)
PPV_FILTERING_ENABLED = config.get('PPV_FILTERING_ENABLED', False)

# 2. Rollout strategy
#    Week 1: Opt-in via settings
#    Week 2: Default on for new accounts
#    Week 3: Default on for all accounts
```

---

## Step-by-Step: Database Setup

### 1. Create the Model

**File:** `models.py`

```python
from datetime import datetime

class PPVEventFilter(db.Model):
    """Rules for filtering PPV channels by provider."""
    
    __tablename__ = 'ppv_event_filter'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Category from IPTV provider (e.g., "US| ESPN+ PPV")
    category = db.Column(db.String(255), unique=True, nullable=False, index=True)
    
    # Provider name for reference
    provider_name = db.Column(db.String(100), nullable=False)
    
    # Filter strategy: ISO_DATETIME, TEXT_BASED, ALWAYS_SHOW, ALWAYS_HIDE
    filter_type = db.Column(db.String(50), nullable=False)
    
    # For ISO_DATETIME filters
    date_field_pattern = db.Column(db.String(500))  # Regex pattern
    placeholder_date = db.Column(db.String(50))     # e.g., "2098-12-31"
    
    # For TEXT_BASED filters
    placeholder_text = db.Column(db.String(500))    # Hide if contains
    always_show_pattern = db.Column(db.String(500)) # Show if contains
    
    # For future use
    requires_epg_lookup = db.Column(db.Boolean, default=False)
    
    # Admin control
    enabled = db.Column(db.Boolean, default=True)
    
    # Metadata
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, onupdate=datetime.utcnow)
    
    def to_dict(self):
        """Convert to dict for serialization."""
        return {
            'id': self.id,
            'category': self.category,
            'provider_name': self.provider_name,
            'filter_type': self.filter_type,
            'date_field_pattern': self.date_field_pattern,
            'placeholder_date': self.placeholder_date,
            'placeholder_text': self.placeholder_text,
            'always_show_pattern': self.always_show_pattern,
            'enabled': self.enabled,
        }
    
    def __repr__(self):
        return f'<PPVEventFilter {self.category} - {self.filter_type}>'
```

### 2. Create the Migration

**File:** `migrations/2025_02_add_ppv_event_filter.py`

```python
"""Add PPVEventFilter table for PPV channel filtering."""

import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def migrate(db_path):
    """Add PPVEventFilter table with seed data."""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Create table if not exists
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
        
        # Seed default filter rules for major providers
        default_rules = [
            {
                'category': 'US| ESPN+ PPV',
                'provider_name': 'ESPN+',
                'filter_type': 'ISO_DATETIME',
                'date_field_pattern': r'\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)',
                'placeholder_date': '2098-12-31',
            },
            {
                'category': 'US| B1G+ PPV',
                'provider_name': 'B1G+',
                'filter_type': 'ISO_DATETIME',
                'date_field_pattern': r'\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)',
                'placeholder_date': None,
            },
            # ... more rules ...
        ]
        
        for rule in default_rules:
            cursor.execute("""
                INSERT OR IGNORE INTO ppv_event_filter 
                (category, provider_name, filter_type, date_field_pattern, placeholder_date)
                VALUES (?, ?, ?, ?, ?)
            """, (
                rule['category'],
                rule['provider_name'],
                rule['filter_type'],
                rule['date_field_pattern'],
                rule['placeholder_date'],
            ))
        
        conn.commit()
        return True, f"Added PPVEventFilter table and seeded {len(default_rules)} rules"
    
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, str(e)
    
    finally:
        conn.close()
```

### 3. Run Migration

```bash
# In app.py startup or run_migrations.py
python run_migrations.py
```

---

## Step-by-Step: Integration

### 1. Update FilterService

**File:** `services/filter_service.py`

```python
from services.ppv_filter_service import PPVFilterService

class FilterService:
    
    def apply_filters(self, channels, account_id, filters=None):
        """Apply all filters to channels."""
        
        # Apply PPV filtering first (removes most channels)
        channels = self._apply_ppv_filter(channels, account_id)
        
        # Then apply other filters
        if filters:
            channels = self._apply_category_filters(channels, filters)
            channels = self._apply_name_filters(channels, filters)
        
        return channels
    
    def _apply_ppv_filter(self, channels, account_id):
        """Filter PPV channels based on scheduled events."""
        
        ppv_service = PPVFilterService(db)
        filtered = []
        
        for channel in channels:
            # Check if this is a PPV channel
            if not self._is_ppv_category(channel.category):
                filtered.append(channel)
                continue
            
            # Get filter rule for this category
            rule = PPVEventFilter.query.filter_by(
                category=channel.category,
                enabled=True
            ).first()
            
            # Apply filter
            should_show, event_meta = ppv_service.should_show_channel(
                channel.name,
                channel.category,
                rule.to_dict() if rule else None
            )
            
            if should_show:
                filtered.append(channel)
                
                # Cache event metadata for EPG generation
                if event_meta:
                    self._cache_event_metadata(channel.id, event_meta)
        
        return filtered
    
    def _is_ppv_category(self, category):
        """Check if category is PPV-related."""
        return 'PPV' in category.upper()
    
    def _cache_event_metadata(self, channel_id, event_meta):
        """Store event metadata for later EPG generation."""
        # Simple cache in memory or Redis
        cache_key = f"ppv_event:{channel_id}"
        # TODO: Implement caching
        pass
```

### 2. Update Routes

**File:** `app.py` (or new blueprint)

```python
from models import PPVEventFilter

@app.route('/api/ppv-filters', methods=['GET'])
def get_ppv_filters():
    """Get all PPV filter rules."""
    filters = PPVEventFilter.query.all()
    return jsonify({
        'filters': [f.to_dict() for f in filters],
        'total': len(filters),
    })

@app.route('/api/ppv-filters/<int:filter_id>', methods=['POST'])
def update_ppv_filter(filter_id):
    """Update a PPV filter rule."""
    data = request.json
    filter_rule = PPVEventFilter.query.get_or_404(filter_id)
    
    if 'enabled' in data:
        filter_rule.enabled = data['enabled']
    if 'placeholder_text' in data:
        filter_rule.placeholder_text = data['placeholder_text']
    # ... update other fields ...
    
    db.session.commit()
    return jsonify(filter_rule.to_dict())

@app.route('/api/ppv-filters/<category>/test', methods=['POST'])
def test_ppv_filter(category):
    """Test a filter against sample channel names."""
    from services.ppv_filter_service import PPVFilterService
    
    data = request.json
    sample_names = data.get('sample_names', [])
    
    rule = PPVEventFilter.query.filter_by(category=category).first_or_404()
    service = PPVFilterService()
    
    results = []
    for name in sample_names:
        should_show, meta = service.should_show_channel(name, category, rule.to_dict())
        results.append({
            'name': name,
            'should_show': should_show,
            'event': meta,
        })
    
    return jsonify(results)
```

---

## Testing Strategy

### 1. Unit Tests

**File:** `tests/test_ppv_filter_service.py`

```python
import pytest
from datetime import datetime
from services.ppv_filter_service import PPVFilterService, DEFAULT_FILTER_RULES

class TestPPVFilterService:
    
    @pytest.fixture
    def service(self):
        """Create service with fixed current_time for testing."""
        return PPVFilterService(current_time=datetime(2025, 12, 27))
    
    def test_espnplus_future_event(self, service):
        """ESPN+ channel with future event should show."""
        rule = DEFAULT_FILTER_RULES['US| ESPN+ PPV']
        channel = 'US (ESPN+ 001) | Game (2025-12-27 03:35:06)'
        
        should_show, meta = service.should_show_channel(channel, 'US| ESPN+ PPV', rule)
        
        assert should_show == True
        assert meta is not None
        assert meta['event_name'] == 'Game'
    
    def test_espnplus_placeholder_date(self, service):
        """ESPN+ channel with placeholder date should hide."""
        rule = DEFAULT_FILTER_RULES['US| ESPN+ PPV']
        channel = 'US (ESPN+ 046) |  (2098-12-31 08:00:01)'
        
        should_show, meta = service.should_show_channel(channel, 'US| ESPN+ PPV', rule)
        
        assert should_show == False
        assert meta is None
    
    def test_dazn_no_event_marker(self, service):
        """DAZN with NO EVENT marker should hide."""
        rule = {
            'filter_type': 'TEXT_BASED',
            'placeholder_text': 'NO EVENT STREAMING',
        }
        channel = 'AT: DAZN PPV 1 - NO EVENT STREAMING - | 8K'
        
        should_show, meta = service.should_show_channel(channel, 'AT| DAZN PPV', rule)
        
        assert should_show == False
    
    def test_24_7_entertainment(self, service):
        """24/7 channels should always show."""
        rule = {
            'filter_type': 'TEXT_BASED',
            'always_show_pattern': '24/7',
        }
        channel = 'US: 24/7 COMEDY MOVIES'
        
        should_show, meta = service.should_show_channel(
            channel, 'US| 24/7 PPV', rule
        )
        
        assert should_show == True
```

### 2. Integration Tests

```python
def test_ppv_filtering_in_playlist_generation():
    """Full flow: Filter PPV channels in playlist generation."""
    # Setup
    account = Account(url='...', username='...', password='...')
    db.session.add(account)
    db.session.commit()
    
    # Mock IPTV service to return channels
    # - 100 ESPN+ slots (5 with events, 95 with 2098-12-31)
    # - 50 DAZN slots (all with NO EVENT)
    # - 10 with real events
    
    filter_service = FilterService(db)
    
    # Apply filters
    filtered = filter_service.apply_filters(channels, account.id)
    
    # Assert
    assert len(filtered) == 15  # Only channels with real events
    assert all('2098-12-31' not in c.name for c in filtered)
    assert all('NO EVENT' not in c.name for c in filtered)
```

---

## Monitoring & Maintenance

### Key Metrics to Track

```python
# In logging/metrics
- Total PPV channels processed
- % Shown vs. Hidden per provider
- Filter accuracy (compared to user feedback)
- Performance (ms to filter 1K channels)
- Cache hit rate
```

### Regular Maintenance

1. **Weekly:** Check for new provider patterns in real IPTV data
2. **Monthly:** Review accuracy metrics, adjust patterns if needed
3. **Quarterly:** Update pattern documentation with new learnings

---

## Quick Reference

### Filter Type Cheat Sheet

| Type | Use When | Pattern Key |
|------|----------|-------------|
| `ISO_DATETIME` | Datetime embedded in name | Extract datetime, compare to now |
| `TEXT_BASED` | No event or "24/7" marker | Search for text pattern |
| `ALWAYS_SHOW` | Traditional channels | Return true always |
| `ALWAYS_HIDE` | Headers/placeholders | Return false always |

### Common Regex Patterns

```python
# Extract ISO datetime in parentheses
r'\((\d{4}-\d{2}-\d{2}\s[\d:]+)\)'

# Extract datetime with optional seconds
r'\((\d{4}-\d{2}-\d{2}\s\d{2}:\d{2}(?::\d{2})?)\)'

# Extract event name before datetime
r'\|([^(]+)\s*\('
```

---

## Next Steps

1. **Read** PPV_FILTERING_DESIGN.md in full
2. **Review** ppv_filter_service.py code
3. **Plan** your Week 1 work (database + integration)
4. **Start** with Step 1 (create PPVEventFilter model)
5. **Test** as you go (write tests alongside code)

Good luck! 🚀
