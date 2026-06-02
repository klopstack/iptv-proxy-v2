"""Add iana_timezone column to sports_teams."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add iana_timezone to sports_teams."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(sports_teams)")
        columns = [row[1] for row in cursor.fetchall()]

        if "iana_timezone" not in columns:
            cursor.execute("ALTER TABLE sports_teams ADD COLUMN iana_timezone TEXT")
            logger.info("Added iana_timezone to sports_teams")
        else:
            logger.info("iana_timezone already exists in sports_teams, skipping")

        conn.commit()
        return True, "Added iana_timezone column to sports_teams"
    finally:
        conn.close()
