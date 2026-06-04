"""Add PPV and FCC rename format templates to accounts, and fcc_facility_id to channels."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add ppv_rename_format and fcc_rename_format to accounts; fcc_facility_id to channels."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Add ppv_rename_format to accounts
        cursor.execute("PRAGMA table_info(accounts)")
        account_columns = [row[1] for row in cursor.fetchall()]

        if "ppv_rename_format" not in account_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN ppv_rename_format TEXT")
            logger.info("Added ppv_rename_format to accounts")
        else:
            logger.info("ppv_rename_format already exists in accounts, skipping")

        if "fcc_rename_format" not in account_columns:
            cursor.execute("ALTER TABLE accounts ADD COLUMN fcc_rename_format TEXT")
            logger.info("Added fcc_rename_format to accounts")
        else:
            logger.info("fcc_rename_format already exists in accounts, skipping")

        # Add fcc_facility_id to channels
        cursor.execute("PRAGMA table_info(channels)")
        channel_columns = [row[1] for row in cursor.fetchall()]

        if "fcc_facility_id" not in channel_columns:
            cursor.execute("ALTER TABLE channels ADD COLUMN fcc_facility_id INTEGER REFERENCES fcc_facilities(id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel_fcc_facility ON channels(fcc_facility_id)")
            logger.info("Added fcc_facility_id to channels")
        else:
            logger.info("fcc_facility_id already exists in channels, skipping")

        conn.commit()
        return True, "Added ppv_rename_format, fcc_rename_format, and fcc_facility_id columns"
    finally:
        conn.close()
