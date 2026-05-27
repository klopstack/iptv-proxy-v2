"""Remove legacy epg_sources.sd_lineup column (rebuild table)."""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("PRAGMA table_info(epg_sources)")
        cols = [row[1] for row in cursor.fetchall()]
        if "sd_lineup" not in cols:
            return True, "epg_sources.sd_lineup already removed, skipping"

        # Rebuild table without sd_lineup (SQLite doesn't support DROP COLUMN).
        cursor.execute("ALTER TABLE epg_sources RENAME TO epg_sources_old")

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

        # Preserve any newer columns added by later migrations (best-effort).
        cursor.execute("PRAGMA table_info(epg_sources_old)")
        old_cols = [row[1] for row in cursor.fetchall()]
        extra_cols = [
            c
            for c in old_cols
            if c
            not in {
                "id",
                "name",
                "source_type",
                "account_id",
                "url",
                "sd_username",
                "sd_password",
                "sd_lineup",
                "priority",
                "enabled",
                "last_sync",
                "last_sync_status",
                "last_sync_message",
                "channel_count",
                "created_at",
                "updated_at",
            }
        ]
        for c in extra_cols:
            # Infer type from old schema.
            cursor.execute("PRAGMA table_info(epg_sources_old)")
            info = {row[1]: row[2] for row in cursor.fetchall()}
            col_type = info.get(c) or "TEXT"
            cursor.execute(f"ALTER TABLE epg_sources ADD COLUMN {c} {col_type}")

        # Copy data (excluding sd_lineup)
        base_cols = [
            "id",
            "name",
            "source_type",
            "account_id",
            "url",
            "sd_username",
            "sd_password",
            "priority",
            "enabled",
            "last_sync",
            "last_sync_status",
            "last_sync_message",
            "channel_count",
            "created_at",
            "updated_at",
        ] + extra_cols

        cols_csv = ", ".join(base_cols)
        cursor.execute(f"INSERT INTO epg_sources ({cols_csv}) SELECT {cols_csv} FROM epg_sources_old")

        cursor.execute("DROP TABLE epg_sources_old")

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_epg_sources_account ON epg_sources(account_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_epg_sources_type ON epg_sources(source_type)")

        conn.commit()
        return True, "Rebuilt epg_sources without sd_lineup"
    except Exception as e:
        conn.rollback()
        logger.error("Error removing epg_sources.sd_lineup: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()

