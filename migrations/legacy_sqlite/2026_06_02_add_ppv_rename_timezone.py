"""Add ppv_rename_timezone to accounts for localized PPV channel naming."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add ppv_rename_timezone column to accounts."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(accounts)")
        account_columns = [row[1] for row in cursor.fetchall()]

        if "ppv_rename_timezone" not in account_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN ppv_rename_timezone TEXT")
            logger.info("Added ppv_rename_timezone to accounts")
        else:
            logger.info("ppv_rename_timezone already exists in accounts, skipping")

        conn.commit()
        return True, "Added ppv_rename_timezone column"
    finally:
        conn.close()
