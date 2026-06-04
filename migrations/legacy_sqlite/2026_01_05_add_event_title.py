"""Add title field to events table for non-vs event matching"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add title column to events table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(events)")
        columns = [row[1] for row in cursor.fetchall()]

        if "title" not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN title VARCHAR(500)")

            # Create index for title lookups
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_event_title ON events(title)")

            conn.commit()
            return True, "Added title column and index to events table"
        else:
            return True, "title column already exists, skipping"
    except Exception as e:
        conn.rollback()
        return False, f"Failed to add title column: {e}"
    finally:
        conn.close()
