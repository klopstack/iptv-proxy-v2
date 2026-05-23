"""Add sync_started_at column for stale sync lock recovery."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(accounts)")
        columns = {row[1] for row in cursor.fetchall()}
        if "sync_started_at" in columns:
            return True, "accounts.sync_started_at already exists, skipping"

        logger.info("Adding sync_started_at column to accounts")
        cursor.execute("ALTER TABLE accounts ADD COLUMN sync_started_at DATETIME")

        conn.commit()
        return True, "Added sync_started_at column to accounts"
    except Exception as e:
        conn.rollback()
        logger.error("Error adding sync_started_at: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()
