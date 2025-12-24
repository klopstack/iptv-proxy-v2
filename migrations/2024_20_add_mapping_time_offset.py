"""Add time_offset_hours column to channel_epg_mappings table

This migration adds support for time offsets on EPG mappings, allowing
users to adjust EPG times for time-shifted channels (e.g., -3 hours
for west coast feeds from east coast sources).
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add time_offset_hours column to channel_epg_mappings table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(channel_epg_mappings)")
        columns = [row[1] for row in cursor.fetchall()]

        if "time_offset_hours" not in columns:
            cursor.execute("ALTER TABLE channel_epg_mappings ADD COLUMN time_offset_hours INTEGER DEFAULT 0")
            conn.commit()
            return True, "Added time_offset_hours column to channel_epg_mappings"
        else:
            return True, "time_offset_hours column already exists, skipping"
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False, str(e)
    finally:
        conn.close()
