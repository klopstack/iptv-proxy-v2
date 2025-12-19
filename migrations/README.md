# Database Migrations

This directory contains database migration scripts that are run automatically on container startup.

## How It Works

1. **Idempotent**: All migrations check if changes are needed before applying them
2. **Sequential**: Migrations run in alphabetical order by filename
3. **Automatic**: Run on every container start via `entrypoint.sh`
4. **Safe**: Each migration handles errors gracefully

## Naming Convention

Migrations should be named: `YYYY_description.py`

Example:
- `2024_01_add_indexes.py`
- `2024_02_add_column.py`

## Creating a Migration

```python
"""
Description of what this migration does
"""
import sqlite3
import os
import sys


def migrate(db_path):
    """
    Apply migration if needed.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if migration is needed
        # ... your check logic ...
        
        # Apply changes
        # ... your migration logic ...
        
        conn.commit()
        conn.close()
        
        return True, "Migration applied successfully"
        
    except Exception as e:
        return False, f"Migration failed: {e}"


if __name__ == "__main__":
    # For standalone execution
    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    
    success, message = migrate(db_path)
    print(message)
    sys.exit(0 if success else 1)
```

## Testing a Migration

```bash
# Test standalone
python migrations/2024_01_add_indexes.py

# Test full migration runner
python run_migrations.py
```

## Rollback

These migrations don't support automatic rollback. If a migration fails:
1. Restore from backup
2. Fix the migration script
3. Run again (migrations are idempotent)
