"""
Migration: Add cached_images table for icon/logo caching
Date: 2024-11
"""

import sqlite3


def get_description():
    return "Add cached_images table for icon/logo caching"


def migrate(db_path):
    """
    Add cached_images table.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if cached_images table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='cached_images'")
        if cursor.fetchone():
            conn.close()
            return (True, "cached_images table already exists, skipping")

        # Create cached_images table
        cursor.execute(
            """
            CREATE TABLE cached_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash VARCHAR(64) UNIQUE NOT NULL,
                original_url VARCHAR(2000) NOT NULL,
                content_type VARCHAR(100),
                file_size INTEGER,
                file_path VARCHAR(500),
                status VARCHAR(20) DEFAULT 'pending',
                error_message VARCHAR(500),
                fetch_count INTEGER DEFAULT 0,
                hit_count INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                fetched_at DATETIME,
                expires_at DATETIME,
                last_accessed_at DATETIME
            )
            """
        )

        # Create indexes
        cursor.execute("CREATE UNIQUE INDEX idx_cached_image_hash ON cached_images(url_hash)")
        cursor.execute("CREATE INDEX idx_cached_image_status ON cached_images(status)")
        cursor.execute("CREATE INDEX idx_cached_image_expires ON cached_images(expires_at)")

        conn.commit()
        conn.close()

        return (True, "Created cached_images table with indexes")

    except Exception as e:
        return (False, f"Failed to create cached_images table: {e}")
