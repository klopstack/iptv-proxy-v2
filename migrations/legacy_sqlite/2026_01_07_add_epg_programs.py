"""
Add EPG Programs table for storing program data in the database.

This migration creates the epg_programs table which stores EPG program
information to enable:
1. Efficient EPG generation without re-parsing large XML files
2. Display of current/upcoming programs in the UI for EPG matching verification
3. Search by program title when creating manual EPG mappings
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add epg_programs table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='epg_programs'")
        if cursor.fetchone():
            return True, "epg_programs table already exists, skipping"

        # Create the epg_programs table
        cursor.execute(
            """
            CREATE TABLE epg_programs (
                id INTEGER PRIMARY KEY,
                epg_channel_id INTEGER NOT NULL,
                start_time DATETIME NOT NULL,
                stop_time DATETIME NOT NULL,
                title VARCHAR(500) NOT NULL,
                sub_title VARCHAR(500),
                description TEXT,
                categories TEXT,
                season INTEGER,
                episode INTEGER,
                episode_id VARCHAR(100),
                rating VARCHAR(20),
                rating_system VARCHAR(50),
                original_air_date DATE,
                is_new BOOLEAN DEFAULT 0,
                is_live BOOLEAN DEFAULT 0,
                is_premiere BOOLEAN DEFAULT 0,
                sport VARCHAR(100),
                team_home VARCHAR(200),
                team_away VARCHAR(200),
                icon_url VARCHAR(500),
                last_updated DATETIME,
                created_at DATETIME,
                FOREIGN KEY (epg_channel_id) REFERENCES epg_channels(id) ON DELETE CASCADE
            )
        """
        )

        # Create indexes for efficient queries
        cursor.execute(
            "CREATE INDEX idx_epg_program_channel_time ON epg_programs(epg_channel_id, start_time, stop_time)"
        )
        cursor.execute("CREATE INDEX idx_epg_program_title ON epg_programs(title)")
        cursor.execute("CREATE INDEX idx_epg_program_start ON epg_programs(start_time)")
        cursor.execute("CREATE INDEX idx_epg_program_stop ON epg_programs(stop_time)")
        cursor.execute("CREATE UNIQUE INDEX idx_epg_program_channel_start ON epg_programs(epg_channel_id, start_time)")

        conn.commit()
        return True, "Created epg_programs table with indexes"

    except Exception as e:
        conn.rollback()
        return False, f"Error creating epg_programs table: {e}"
    finally:
        conn.close()
