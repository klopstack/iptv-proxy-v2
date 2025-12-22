"""
Migration: Add EPG (Electronic Program Guide) tables
Date: 2024

This migration adds tables for managing EPG data from multiple sources:
- epg_sources: EPG data sources (provider XMLTV, Schedules Direct, etc.)
- epg_channels: Parsed channel data from XMLTV files
- channel_epg_mappings: Mappings between our channels and EPG channels
"""

import sqlite3


def get_description():
    return "Add EPG tables for guide data management"


def migrate(db_path):
    """
    Add EPG-related tables.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if epg_sources table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='epg_sources'")
        if cursor.fetchone():
            conn.close()
            return (True, "EPG tables already exist, skipping")

        # Create epg_sources table
        cursor.execute(
            """
            CREATE TABLE epg_sources (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                source_type VARCHAR(50) NOT NULL,
                account_id INTEGER,
                url VARCHAR(500),
                sd_username VARCHAR(100),
                sd_password VARCHAR(100),
                sd_lineup VARCHAR(100),
                priority INTEGER DEFAULT 100,
                enabled BOOLEAN DEFAULT 1,
                last_sync TIMESTAMP,
                last_sync_status VARCHAR(50),
                last_sync_message TEXT,
                channel_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        """
        )
        cursor.execute("CREATE INDEX idx_epg_sources_account ON epg_sources(account_id)")
        cursor.execute("CREATE INDEX idx_epg_sources_type ON epg_sources(source_type)")

        # Create epg_channels table
        cursor.execute(
            """
            CREATE TABLE epg_channels (
                id INTEGER PRIMARY KEY,
                source_id INTEGER NOT NULL,
                channel_id VARCHAR(100) NOT NULL,
                display_name VARCHAR(200),
                display_names_json TEXT,
                icon_url VARCHAR(500),
                url VARCHAR(500),
                matched_channels_json TEXT,
                program_count INTEGER DEFAULT 0,
                first_program TIMESTAMP,
                last_program TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (source_id) REFERENCES epg_sources(id) ON DELETE CASCADE,
                UNIQUE (source_id, channel_id)
            )
        """
        )
        cursor.execute("CREATE INDEX idx_epg_channels_source ON epg_channels(source_id)")
        cursor.execute("CREATE INDEX idx_epg_channels_channel_id ON epg_channels(channel_id)")

        # Create channel_epg_mappings table
        cursor.execute(
            """
            CREATE TABLE channel_epg_mappings (
                id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                epg_channel_id INTEGER NOT NULL,
                mapping_type VARCHAR(50) NOT NULL,
                confidence REAL DEFAULT 1.0,
                is_override BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
                FOREIGN KEY (epg_channel_id) REFERENCES epg_channels(id) ON DELETE CASCADE,
                UNIQUE (channel_id, epg_channel_id)
            )
        """
        )
        cursor.execute("CREATE INDEX idx_channel_epg_mappings_channel ON channel_epg_mappings(channel_id)")
        cursor.execute("CREATE INDEX idx_channel_epg_mappings_epg ON channel_epg_mappings(epg_channel_id)")

        conn.commit()
        conn.close()

        return (True, "EPG tables created successfully")

    except Exception as e:
        return (False, f"Migration failed: {str(e)}")


def rollback(db_path):
    """
    Remove EPG tables.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS channel_epg_mappings")
        cursor.execute("DROP TABLE IF EXISTS epg_channels")
        cursor.execute("DROP TABLE IF EXISTS epg_sources")

        conn.commit()
        conn.close()

        return (True, "EPG tables removed")

    except Exception as e:
        return (False, f"Rollback failed: {str(e)}")
