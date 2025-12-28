"""Add sync_in_progress field to Account model"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add sync_in_progress column to accounts table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in cursor.fetchall()]

        if "sync_in_progress" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN sync_in_progress BOOLEAN DEFAULT 0")
            conn.commit()
            logger.info("Added sync_in_progress column to accounts table")
            return True, "Added sync_in_progress column"
        else:
            return True, "sync_in_progress column already exists, skipping"
    except Exception as e:
        logger.error(f"Error adding sync_in_progress column: {e}")
        conn.rollback()
        return False, f"Error: {str(e)}"
    finally:
        conn.close()
