"""
Migration: Add Schedules Direct tables
Date: 2024-10
"""
import sqlite3


def get_description():
    return "Add Schedules Direct lineup and station tables"


def migrate(db_path):
    """
    Add Schedules Direct tables.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if sd_lineups table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='sd_lineups'")
        if cursor.fetchone():
            conn.close()
            return (True, "SD tables already exist, skipping")

        # Create sd_lineups table
        cursor.execute(
            """
            CREATE TABLE sd_lineups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                epg_source_id INTEGER NOT NULL,
                lineup_id VARCHAR(100) NOT NULL,
                name VARCHAR(200),
                location VARCHAR(200),
                lineup_type VARCHAR(50),
                transport VARCHAR(50),
                channel_count INTEGER DEFAULT 0,
                last_sync DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (epg_source_id) REFERENCES epg_sources(id),
                UNIQUE (epg_source_id, lineup_id)
            )
            """
        )
        cursor.execute("CREATE INDEX idx_sd_lineups_source ON sd_lineups(epg_source_id)")

        # Create sd_stations table
        cursor.execute(
            """
            CREATE TABLE sd_stations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lineup_id INTEGER NOT NULL,
                station_id VARCHAR(50) NOT NULL,
                channel_number VARCHAR(20),
                callsign VARCHAR(50),
                name VARCHAR(200),
                affiliate VARCHAR(100),
                broadcast_language VARCHAR(100),
                logo_url VARCHAR(500),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (lineup_id) REFERENCES sd_lineups(id),
                UNIQUE (lineup_id, station_id)
            )
            """
        )
        cursor.execute("CREATE INDEX idx_sd_stations_lineup ON sd_stations(lineup_id)")
        cursor.execute("CREATE INDEX idx_sd_station_callsign ON sd_stations(callsign)")
        cursor.execute("CREATE INDEX idx_sd_station_name ON sd_stations(name)")

        conn.commit()
        conn.close()

        return (True, "Created sd_lineups and sd_stations tables")

    except Exception as e:
        return (False, f"Failed to create SD tables: {e}")
