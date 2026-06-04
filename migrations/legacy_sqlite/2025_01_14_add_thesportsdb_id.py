"""Add thesportsdb_id field to Channel model for TheSportsDB integration"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """
    Add thesportsdb_id column to channels table.

    This field stores the TheSportsDB event ID for PPV channels,
    enabling integration with TheSportsDB for sports event data.
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(channels)")
        columns = [row[1] for row in cursor.fetchall()]

        if "thesportsdb_id" not in columns:
            cursor.execute(
                """
                ALTER TABLE channels 
                ADD COLUMN thesportsdb_id VARCHAR(50) NULL
                """
            )

            # Create index on thesportsdb_id for faster lookups
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_channel_thesportsdb_id 
                ON channels(thesportsdb_id)
                """
            )

            conn.commit()
            logger.info("Successfully added thesportsdb_id column to channels table")
            return True, "Added thesportsdb_id column and index to channels table"
        else:
            logger.info("thesportsdb_id column already exists")
            return True, "thesportsdb_id column already exists, skipping"

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        return False, f"Failed to add thesportsdb_id column: {e}"
    finally:
        conn.close()
