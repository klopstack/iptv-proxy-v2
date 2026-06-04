"""Remove legacy accounts.username/password columns (rebuild table)."""

import importlib.util
import logging
import sqlite3
from pathlib import Path


def _fk_repair():
    path = Path(__file__).resolve().parent / "_sqlite_fk_repair.py"
    spec = importlib.util.spec_from_file_location("_sqlite_fk_repair", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


logger = logging.getLogger(__name__)


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA table_info(accounts)")
        cols = [row[1] for row in cursor.fetchall()]
        if "username" not in cols and "password" not in cols:
            return True, "accounts legacy username/password already removed, skipping"

        cursor.execute("ALTER TABLE accounts RENAME TO accounts_old")

        cursor.execute(
            """
            CREATE TABLE accounts (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                server VARCHAR(255) NOT NULL,
                user_agent VARCHAR(255),
                enabled BOOLEAN DEFAULT 1,
                last_sync DATETIME,
                last_sync_status VARCHAR(50),
                sync_in_progress BOOLEAN DEFAULT 0,
                sync_started_at DATETIME,
                ppv_visibility VARCHAR(20) DEFAULT 'hide_inactive' NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute("PRAGMA table_info(accounts_old)")
        old_cols = [row[1] for row in cursor.fetchall()]
        extra_cols = [
            c
            for c in old_cols
            if c
            not in {
                "id",
                "name",
                "server",
                "username",
                "password",
                "user_agent",
                "enabled",
                "last_sync",
                "last_sync_status",
                "sync_in_progress",
                "sync_started_at",
                "ppv_visibility",
                "created_at",
                "updated_at",
            }
        ]
        for c in extra_cols:
            cursor.execute("PRAGMA table_info(accounts_old)")
            info = {row[1]: row[2] for row in cursor.fetchall()}
            col_type = info.get(c) or "TEXT"
            cursor.execute(f"ALTER TABLE accounts ADD COLUMN {c} {col_type}")

        base_cols = [
            "id",
            "name",
            "server",
            "user_agent",
            "enabled",
            "last_sync",
            "last_sync_status",
            "sync_in_progress",
            "sync_started_at",
            "ppv_visibility",
            "created_at",
            "updated_at",
        ] + extra_cols
        cols_csv = ", ".join(base_cols)
        cursor.execute(f"INSERT INTO accounts ({cols_csv}) SELECT {cols_csv} FROM accounts_old")

        cursor.execute("DROP TABLE accounts_old")

        repair = _fk_repair()
        repair.fix_foreign_key_table_references(cursor, "accounts_old", "accounts")

        conn.commit()
        return True, "Rebuilt accounts without legacy username/password"
    except Exception as e:
        conn.rollback()
        logger.error("Error removing accounts legacy username/password: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()
