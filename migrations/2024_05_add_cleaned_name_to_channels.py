"""Add cleaned_name column to channels table

This migration adds a cleaned_name column to store the processed channel name
after tag extraction rules have been applied. This avoids recomputing cleaned
names on every request.

Migration: 2024_05_add_cleaned_name_to_channels
Created: 2024-12-19
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import db


def upgrade():
    """Add cleaned_name column to channels table"""

    # SQLite doesn't support ALTER TABLE ADD COLUMN with constraints easily,
    # but we can add a simple column
    with db.engine.connect() as conn:
        # Add cleaned_name column (nullable initially for existing rows)
        conn.execute(db.text("ALTER TABLE channels ADD COLUMN cleaned_name VARCHAR(500)"))
        conn.commit()

        print(f"✓ Added cleaned_name column to channels table")


def downgrade():
    """Remove cleaned_name column from channels table"""

    # SQLite doesn't support DROP COLUMN directly, would need table recreation
    # For now, just document that downgrade requires manual intervention
    raise NotImplementedError(
        "SQLite doesn't support DROP COLUMN. " "To downgrade, recreate the channels table without cleaned_name column."
    )


if __name__ == "__main__":
    import os

    # Set DATABASE_URL to local path if not set
    if not os.getenv("DATABASE_URL"):
        db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "iptv_proxy.db")
        os.environ["DATABASE_URL"] = f"sqlite:///{db_path}"

    from app import app

    with app.app_context():
        print("Running migration: Add cleaned_name to channels")
        upgrade()
        print("Migration completed successfully!")
