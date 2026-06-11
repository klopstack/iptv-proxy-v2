"""Add ppv_show_unmatched_live column to accounts (default True)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add ppv_show_unmatched_live column (default True)."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(accounts)")
        columns = {row[1] for row in cursor.fetchall()}

        if "ppv_show_unmatched_live" not in columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN ppv_show_unmatched_live BOOLEAN DEFAULT 1 NOT NULL")
            message = "Added ppv_show_unmatched_live column"
        else:
            message = "ppv_show_unmatched_live column already exists, skipping"

        conn.commit()
        return True, message
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False, f"Failed to add ppv_show_unmatched_live: {str(e)}"
    finally:
        conn.close()
