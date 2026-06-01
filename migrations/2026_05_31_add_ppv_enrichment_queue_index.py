"""Add composite index on channels(is_ppv, ppv_enrichment_status, last_seen)

Speeds up the hot/cold priority ordering in PPVEnrichmentOrchestrator
when scanning large channel tables (10k+ rows).
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


def migrate(db_path):
    """Add composite PPV enrichment queue index."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('channels', 'channel')")
        table_names = {row[0] for row in cursor.fetchall()}
        if "channels" in table_names:
            table_name = "channels"
        elif "channel" in table_names:
            # Backward-compat fallback for non-standard legacy schemas.
            table_name = "channel"
        else:
            return True, "No channel table found, skipping"

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS ix_channel_ppv_queue
            ON {table_name} (is_ppv, ppv_enrichment_status, last_seen)
            """.format(
                table_name=table_name
            )
        )
        conn.commit()
        return True, f"Created ix_channel_ppv_queue index on {table_name} (or already existed)"
    except Exception as e:
        conn.rollback()
        return False, f"Failed to create index: {e}"
    finally:
        conn.close()
