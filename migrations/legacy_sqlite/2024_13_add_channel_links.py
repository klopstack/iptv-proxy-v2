"""
Migration: Add channel_links table for explicit channel relationships
Date: 2024-12

This table enables:
- Time-shifted channels (East/West coast feeds with time offset)
- Simulcast channels (same content on different streams)
- HD/SD pairs (same content, different quality)

When generating EPG, if a channel has no direct EPG mapping but has a
ChannelLink, the source channel's EPG is used with optional time offset.
"""

import sqlite3


def get_description():
    return "Add channel_links table for explicit channel relationships"


def migrate(db_path):
    """
    Add channel_links table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if channel_links table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channel_links'")
        if cursor.fetchone():
            conn.close()
            return (True, "channel_links table already exists, skipping")

        # Create channel_links table
        cursor.execute(
            """
            CREATE TABLE channel_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                time_offset_hours INTEGER DEFAULT 0,
                link_type VARCHAR(50) DEFAULT 'time_shifted',
                auto_detected BOOLEAN DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(id) ON DELETE CASCADE,
                FOREIGN KEY (source_channel_id) REFERENCES channels(id) ON DELETE CASCADE,
                UNIQUE (channel_id, source_channel_id)
            )
            """
        )

        # Create indexes for efficient lookups
        cursor.execute("CREATE INDEX idx_channel_link_channel ON channel_links(channel_id)")
        cursor.execute("CREATE INDEX idx_channel_link_source ON channel_links(source_channel_id)")

        conn.commit()
        conn.close()
        return (True, "Successfully created channel_links table with indexes")

    except Exception as e:
        return (False, f"Migration failed: {str(e)}")


def rollback(db_path):
    """
    Remove channel_links table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("DROP TABLE IF EXISTS channel_links")

        conn.commit()
        conn.close()
        return (True, "Successfully dropped channel_links table")

    except Exception as e:
        return (False, f"Rollback failed: {str(e)}")
