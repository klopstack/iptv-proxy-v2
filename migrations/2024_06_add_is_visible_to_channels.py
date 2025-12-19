"""Add is_visible column to channels table

This migration adds an is_visible column to store pre-computed filter results.
This avoids recomputing filter matches on every request.

Migration: 2024_06_add_is_visible_to_channels
Created: 2024-12-19
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db


def upgrade():
    """Add is_visible column to channels table"""
    
    # SQLite doesn't support ALTER TABLE ADD COLUMN with constraints easily,
    # but we can add a simple column with default value
    with db.engine.connect() as conn:
        # Add is_visible column (default True - visible until filters are applied)
        conn.execute(db.text(
            "ALTER TABLE channels ADD COLUMN is_visible BOOLEAN DEFAULT 1"
        ))
        conn.commit()
        
        print(f"✓ Added is_visible column to channels table")


def downgrade():
    """Remove is_visible column from channels table"""
    
    # SQLite doesn't support DROP COLUMN directly, would need table recreation
    # For now, just document that downgrade requires manual intervention
    raise NotImplementedError(
        "SQLite doesn't support DROP COLUMN. "
        "To downgrade, recreate the channels table without is_visible column."
    )


if __name__ == "__main__":
    import os
    
    # Set DATABASE_URL to local path if not set
    if not os.getenv("DATABASE_URL"):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "iptv_proxy.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"
    
    from app import app
    
    with app.app_context():
        print("Running migration: Add is_visible to channels")
        upgrade()
        print("Migration completed successfully!")
