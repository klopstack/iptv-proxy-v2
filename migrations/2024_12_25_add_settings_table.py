"""
Add settings table for global application configuration

This migration creates the settings table which stores key-value pairs
for global application settings like proxy_hostname.
"""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Create settings table if it doesn't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if settings table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='settings'")
        if cursor.fetchone():
            return True, "settings table already exists, skipping"

        # Create settings table
        cursor.execute(
            """
            CREATE TABLE settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL UNIQUE,
                value TEXT NOT NULL,
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        conn.commit()
        logger.info("Created settings table")
        return True, "Created settings table successfully"

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False, f"Error creating settings table: {e}"
    finally:
        conn.close()
