"""Add description column to events table for LLM-generated EPG descriptions."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add description column to events table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(events)")
        columns = [row[1] for row in cursor.fetchall()]

        if "description" not in columns:
            cursor.execute("ALTER TABLE events ADD COLUMN description TEXT")
            conn.commit()
            return True, "Added description column to events table"
        else:
            return True, "description column already exists, skipping"
    except Exception as e:
        conn.rollback()
        return False, f"Failed to add description column: {e}"
    finally:
        conn.close()
