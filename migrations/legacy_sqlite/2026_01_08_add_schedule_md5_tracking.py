"""Add MD5 tracking fields to EpgChannel for Schedules Direct caching"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add schedule_md5 and schedule_last_modified fields to epg_channels table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if columns already exist
        cursor.execute("PRAGMA table_info(epg_channels)")
        columns = [row[1] for row in cursor.fetchall()]

        changes_made = []

        if "schedule_md5" not in columns:
            cursor.execute("ALTER TABLE epg_channels ADD COLUMN schedule_md5 VARCHAR(32)")
            changes_made.append("schedule_md5")

        if "schedule_last_modified" not in columns:
            cursor.execute("ALTER TABLE epg_channels ADD COLUMN schedule_last_modified DATETIME")
            changes_made.append("schedule_last_modified")

        conn.commit()

        if changes_made:
            return True, f"Added columns to epg_channels: {', '.join(changes_made)}"
        else:
            return True, "MD5 tracking columns already exist, skipping"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, f"Failed to add MD5 tracking columns: {e}"
    finally:
        conn.close()
