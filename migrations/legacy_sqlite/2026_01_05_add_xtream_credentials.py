"""Add xtream_credentials table for Xtream Codes API output

This migration adds a new table to store credentials for the Xtream Codes API
output format. This allows users to access their filtered playlists using
Xtream Codes-compatible clients and apps.

Migration: 2026_01_05_add_xtream_credentials
Created: 2026-01-05
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add xtream_credentials table"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if the table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='xtream_credentials'")
        if cursor.fetchone():
            return True, "xtream_credentials table already exists, skipping"

        logger.info("Creating xtream_credentials table")

        # Create the table
        cursor.execute(
            """
            CREATE TABLE xtream_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username VARCHAR(100) NOT NULL UNIQUE,
                password VARCHAR(100) NOT NULL,
                account_id INTEGER,
                playlist_config_id INTEGER,
                use_filters BOOLEAN DEFAULT 1,
                collapse_duplicates BOOLEAN DEFAULT 0,
                enabled BOOLEAN DEFAULT 1,
                description TEXT,
                created_at DATETIME,
                updated_at DATETIME,
                FOREIGN KEY (account_id) REFERENCES accounts (id),
                FOREIGN KEY (playlist_config_id) REFERENCES playlist_configs (id)
            )
        """
        )

        # Create indexes for performance
        cursor.execute("CREATE INDEX idx_xtream_credentials_username ON xtream_credentials (username)")
        cursor.execute("CREATE INDEX idx_xtream_credentials_account_id ON xtream_credentials (account_id)")
        cursor.execute(
            "CREATE INDEX idx_xtream_credentials_playlist_config_id ON xtream_credentials (playlist_config_id)"
        )

        conn.commit()
        return True, "Created xtream_credentials table with indexes"

    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating xtream_credentials table: {e}")
        return False, f"Error: {str(e)}"
    finally:
        conn.close()


if __name__ == "__main__":
    import os
    import sys

    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")

    success, message = migrate(db_path)
    if success:
        print(f"✓ {message}")
        sys.exit(0)
    else:
        print(f"✗ {message}")
        sys.exit(1)
