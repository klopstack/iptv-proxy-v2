"""Add PPV visibility preference to accounts table"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add ppv_visibility column to accounts table with default 'hide_inactive'"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists (idempotent)
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [row[1] for row in cursor.fetchall()]

        if "ppv_visibility" not in columns:
            cursor.execute(
                "ALTER TABLE accounts ADD COLUMN ppv_visibility VARCHAR(20) DEFAULT 'hide_inactive' NOT NULL"
            )
            conn.commit()
            return True, "Added ppv_visibility column to accounts table"
        else:
            return True, "ppv_visibility column already exists, skipping"
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False, f"Failed to add ppv_visibility: {str(e)}"
    finally:
        conn.close()
