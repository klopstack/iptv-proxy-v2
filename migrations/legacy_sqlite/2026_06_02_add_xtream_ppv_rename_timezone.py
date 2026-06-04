"""Add ppv_rename_timezone to xtream_credentials for per-client PPV naming."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add ppv_rename_timezone column to xtream_credentials."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(xtream_credentials)")
        columns = [row[1] for row in cursor.fetchall()]

        if "ppv_rename_timezone" not in columns:
            cursor.execute("ALTER TABLE xtream_credentials ADD COLUMN ppv_rename_timezone TEXT")
            logger.info("Added ppv_rename_timezone to xtream_credentials")
        else:
            logger.info("ppv_rename_timezone already exists in xtream_credentials, skipping")

        conn.commit()
        return True, "Added ppv_rename_timezone column to xtream_credentials"
    finally:
        conn.close()
