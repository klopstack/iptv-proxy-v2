"""
Migration: Add credentials table and active_streams table for stream multiplexing
Date: 2024

This migration enables multiple credentials per account for DVR/PIP support.
Each credential can have its own connection limit, allowing stream multiplexing.
"""

import sqlite3


def get_description():
    return "Add credentials table and active_streams table for stream multiplexing"


def migrate(db_path):
    """
    Add credentials and active_streams tables, migrate existing account credentials.

    Args:
        db_path: Path to the SQLite database

    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if credentials table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='credentials'")
        if cursor.fetchone():
            conn.close()
            return (True, "credentials table already exists, skipping")

        # Create credentials table
        cursor.execute(
            """
            CREATE TABLE credentials (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL,
                username VARCHAR(100) NOT NULL,
                password VARCHAR(100) NOT NULL,
                max_connections INTEGER DEFAULT 1,
                active_connections INTEGER DEFAULT 0,
                status VARCHAR(50),
                exp_date VARCHAR(50),
                enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE
            )
        """
        )

        # Create index on account_id
        cursor.execute("CREATE INDEX idx_credentials_account ON credentials(account_id)")

        # Create active_streams table for connection tracking
        cursor.execute(
            """
            CREATE TABLE active_streams (
                id INTEGER PRIMARY KEY,
                credential_id INTEGER NOT NULL,
                stream_id VARCHAR(50) NOT NULL,
                client_ip VARCHAR(45),
                session_token VARCHAR(64) UNIQUE NOT NULL,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (credential_id) REFERENCES credentials(id) ON DELETE CASCADE
            )
        """
        )

        # Create index on credential_id
        cursor.execute("CREATE INDEX idx_active_streams_credential ON active_streams(credential_id)")

        # Migrate existing credentials from accounts table
        cursor.execute("SELECT id, username, password FROM accounts WHERE username IS NOT NULL")
        accounts = cursor.fetchall()

        for account_id, username, password in accounts:
            if username and password:
                cursor.execute(
                    """
                    INSERT INTO credentials (account_id, username, password, max_connections, enabled)
                    VALUES (?, ?, ?, 1, 1)
                """,
                    (account_id, username, password),
                )

        conn.commit()
        conn.close()

        migrated_count = len(accounts)
        return (True, f"credentials and active_streams tables created. Migrated {migrated_count} existing credentials.")

    except Exception as e:
        return (False, f"Migration failed: {str(e)}")
