"""
Migration: Add FCC facilities table for TV station lookup
Date: 2024-12

This table stores TV station registration data from the FCC's LMS database.
It provides authoritative mapping between callsigns and their licensed
cities/markets, enabling better EPG-to-channel matching.

Data source: https://enterpriseefiling.fcc.gov/dataentry/public/tv/lmsDatabase.html
"""

import sqlite3


def get_description():
    return "Add FCC facilities table for TV station callsign/city lookup"


def migrate(db_path):
    """
    Add fcc_facilities table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if fcc_facilities table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='fcc_facilities'")
        if cursor.fetchone():
            conn.close()
            return (True, "fcc_facilities table already exists, skipping")

        # Create fcc_facilities table
        cursor.execute(
            """
            CREATE TABLE fcc_facilities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                facility_id INTEGER UNIQUE,
                callsign VARCHAR(20) NOT NULL,
                service_code VARCHAR(10),
                station_type VARCHAR(10),
                community_city VARCHAR(100),
                community_state VARCHAR(10),
                channel VARCHAR(10),
                tv_virtual_channel VARCHAR(10),
                network_affiliation VARCHAR(100),
                nielsen_dma VARCHAR(100),
                nielsen_dma_rank INTEGER,
                active BOOLEAN DEFAULT 1,
                facility_status VARCHAR(20),
                last_update DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Create indexes for efficient lookups
        cursor.execute("CREATE INDEX idx_fcc_facility_id ON fcc_facilities(facility_id)")
        cursor.execute("CREATE INDEX idx_fcc_callsign ON fcc_facilities(callsign)")
        cursor.execute("CREATE INDEX idx_fcc_callsign_service ON fcc_facilities(callsign, service_code)")
        cursor.execute("CREATE INDEX idx_fcc_city_state ON fcc_facilities(community_city, community_state)")
        cursor.execute("CREATE INDEX idx_fcc_network ON fcc_facilities(network_affiliation)")
        cursor.execute("CREATE INDEX idx_fcc_dma ON fcc_facilities(nielsen_dma)")

        conn.commit()
        conn.close()

        return (True, "Created fcc_facilities table with indexes")

    except Exception as e:
        return (False, f"Failed to create fcc_facilities table: {e}")
