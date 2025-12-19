"""
Migration: Add channels and categories tables
Date: 2024-03-01
"""

import sqlite3


def get_description():
    return "Add channels and categories tables for local storage"


def migrate(db_path):
    """
    Add channels and categories tables.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if already applied
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='channels'")
        if cursor.fetchone():
            conn.close()
            return (True, "Tables already exist, skipping")

        # Create categories table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                category_id VARCHAR(50) NOT NULL,
                category_name VARCHAR(200) NOT NULL,
                parent_id INTEGER,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                CONSTRAINT _account_category_uc UNIQUE (account_id, category_id)
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_category_account ON categories(account_id)")

        # Create channels table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                stream_id VARCHAR(50) NOT NULL,
                name VARCHAR(500) NOT NULL,
                category_id INTEGER,
                stream_type VARCHAR(20),
                stream_icon VARCHAR(500),
                epg_channel_id VARCHAR(100),
                added VARCHAR(50),
                custom_sid VARCHAR(50),
                tv_archive INTEGER,
                direct_source VARCHAR(500),
                tv_archive_duration INTEGER,
                last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE SET NULL,
                CONSTRAINT _account_stream_uc UNIQUE (account_id, stream_id)
            )
        """
        )

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel_account ON channels(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel_name ON channels(name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_channel_category ON channels(category_id)")

        conn.commit()
        conn.close()

        return (True, "Created channels and categories tables successfully")

    except Exception as e:
        if conn:
            conn.close()
        return (False, f"Error creating tables: {str(e)}")
