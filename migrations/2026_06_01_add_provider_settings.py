"""Create provider_settings table for per-provider plugin configuration."""
import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Create provider_settings table if it does not yet exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='provider_settings'")
        if cursor.fetchone():
            return True, "provider_settings table already exists, skipping"

        cursor.execute(
            """
            CREATE TABLE provider_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                provider_name VARCHAR(100) NOT NULL,
                key VARCHAR(100) NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                description TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_provider_settings_name_key UNIQUE (provider_name, key)
            )
            """
        )
        cursor.execute("CREATE INDEX ix_provider_settings_provider_name ON provider_settings (provider_name)")
        conn.commit()
        logger.info("Created provider_settings table")
        return True, "Created provider_settings table successfully"

    except Exception as e:
        conn.rollback()
        return False, f"Failed to create provider_settings table: {e}"
    finally:
        conn.close()
