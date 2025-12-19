"""
Add index on Tag.name for faster tag search/autocomplete

This migration adds an index to the tags.name column to speed up
LIKE/ILIKE queries used in the tag search autocomplete feature.

Added index:
- ix_tags_name: Index on tags.name column for autocomplete searches
"""

import sqlite3
import os
import sys


def migrate(db_path):
    """
    Add index to tags.name column if it doesn't exist.
    
    Args:
        db_path: Path to the SQLite database
        
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check existing indexes on tags table
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='index' AND tbl_name='tags'
        """)
        existing_indexes = {row[0] for row in cursor.fetchall()}
        
        if "ix_tags_name" in existing_indexes:
            return True, "Index on tags.name already exists, skipping"
        
        # Create index on tags.name for faster autocomplete
        cursor.execute("CREATE INDEX IF NOT EXISTS ix_tags_name ON tags(name)")
        
        conn.commit()
        conn.close()
        
        return True, "Created index on tags.name successfully"
        
    except Exception as e:
        return False, f"Failed to add tag name index: {e}"


if __name__ == "__main__":
    # For standalone execution
    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")
    
    if not os.path.exists(db_path):
        print(f"❌ Database not found at: {db_path}")
        sys.exit(1)
    
    success, message = migrate(db_path)
    print(f"{'✅' if success else '❌'} {message}")
    sys.exit(0 if success else 1)
