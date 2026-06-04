"""Add location registry fields to sports_teams."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add state, country, venue, coordinates, and location_source to sports_teams."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(sports_teams)")
        columns = {row[1] for row in cursor.fetchall()}

        new_columns = {
            "state": "TEXT",
            "country": "TEXT",
            "venue_name": "TEXT",
            "latitude": "REAL",
            "longitude": "REAL",
            "location_source": "TEXT",
        }

        added = []
        for name, col_type in new_columns.items():
            if name not in columns:
                cursor.execute(f"ALTER TABLE sports_teams ADD COLUMN {name} {col_type}")
                added.append(name)

        conn.commit()
        if added:
            logger.info("Added sports_teams columns: %s", ", ".join(added))
            return True, f"Added columns to sports_teams: {', '.join(added)}"
        return True, "Sports team location columns already exist, skipping"
    finally:
        conn.close()
