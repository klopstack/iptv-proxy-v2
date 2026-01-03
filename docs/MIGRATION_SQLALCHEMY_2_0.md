# SQLAlchemy 2.0 Migration Roadmap

## Current Status
- **Framework**: Flask-SQLAlchemy 3.1.1
- **Legacy Pattern**: `Model.query` (50+ occurrences)
- **Deprecation Status**: Informational warning only (not breaking yet)
- **Warning Suppression**: Active in `pyproject.toml`

## Migration Strategy

### Phase 1: Foundation (Completed)
- [x] Suppress deprecation warnings in test output
- [x] Document legacy patterns
- [x] Update critical routes to use `db.session.query()` directly

### Phase 2: Systematic Migration (Planned)
When migrating to SQLAlchemy 2.0 style, follow this precedence:

**Preferred (Modern):** SQLAlchemy 2.0 with `db.session.execute(select(...))`
```python
from sqlalchemy import select
stmt = select(Account).filter(Account.id == account_id)
result = db.session.execute(stmt).scalar_one_or_none()
```

**Acceptable (Legacy-Modern Hybrid):** `db.session.query()`
```python
account = db.session.query(Account).filter(Account.id == account_id).first()
```

**Discouraged (Legacy):** `Model.query` (current pattern in 50+ places)
```python
account = Account.query.get(account_id)  # ← Still works but deprecated
```

### Migration Count by Module
- `routes/accounts.py` - 15+ queries
- `routes/epg.py` - 20+ queries
- `routes/rulesets.py` - 10+ queries
- `routes/filters.py` - 5+ queries
- `routes/playlists.py` - 8+ queries
- `services/` - 10+ queries
- `models.py` - Various property methods and hybrid expressions

### Timeline
1. **Now**: Keep warning suppressed, continue development
2. **Immediate**: Migrate queries as they're touched during feature development
3. **Future**: Plan dedicated migration sprint when feature work stabilizes

### Notes
- Flask-SQLAlchemy 3.0+ still fully supports `Model.query`
- No breaking changes expected in near-term releases
- Migration can be done incrementally without rush
- New code should preferentially use `db.session.execute(select(...))` pattern
- Batch operations and performance-critical code should be prioritized

### Related Configuration
```toml
# pyproject.toml - Suppresses Flask-SQLAlchemy deprecation warning
filterwarnings = [
    "ignore:.*'Model.query' is deprecated.*:DeprecationWarning",
]
```
