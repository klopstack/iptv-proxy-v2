"""Add sports_teams table for sportsipy team data storage"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add sports_teams table for storing team data from sportsipy."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sports_teams'")
        if cursor.fetchone():
            return True, "sports_teams table already exists, skipping"

        # Create sports_teams table
        cursor.execute(
            """
            CREATE TABLE sports_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sport VARCHAR(20) NOT NULL,
                abbreviation VARCHAR(50) NOT NULL,
                name VARCHAR(200) NOT NULL,
                aliases TEXT,
                city VARCHAR(100),
                conference VARCHAR(100),
                division VARCHAR(100),
                source VARCHAR(50) DEFAULT 'sportsipy',
                last_updated_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_sports_team_sport_abbrev UNIQUE (sport, abbreviation)
            )
        """
        )

        # Create indexes
        cursor.execute("CREATE INDEX idx_sports_team_sport ON sports_teams (sport)")
        cursor.execute("CREATE INDEX idx_sports_team_name ON sports_teams (name)")

        conn.commit()
        return True, "Created sports_teams table with indexes"

    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating sports_teams table: {e}")
        return False, f"Error: {e}"

    finally:
        conn.close()
