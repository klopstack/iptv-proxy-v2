"""Replace events.external_id single-column unique with composite (external_id, source)."""

import importlib.util
import logging
import sqlite3
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

COMPOSITE_INDEX = "idx_event_external_id_source"


def _fk_repair():
    path = Path(__file__).resolve().parent / "_sqlite_fk_repair.py"
    spec = importlib.util.spec_from_file_location("_sqlite_fk_repair", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _has_composite_unique(cursor: sqlite3.Cursor) -> bool:
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=? LIMIT 1",
        (COMPOSITE_INDEX,),
    )
    return cursor.fetchone() is not None


def _table_columns(cursor: sqlite3.Cursor, table: str) -> List[Tuple]:
    cursor.execute(f"PRAGMA table_info({table})")
    return cursor.fetchall()


def migrate(db_path):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'")
        if not cursor.fetchone():
            return True, "events table does not exist, skipping"

        if _has_composite_unique(cursor):
            return True, "Composite external_id+source unique index already exists, skipping"

        columns = _table_columns(cursor, "events")
        if not columns:
            return True, "events table has no columns, skipping"

        col_defs = []
        col_names = []
        for _cid, name, col_type, notnull, default, pk in columns:
            col_names.append(name)
            definition = f"{name} {col_type or 'TEXT'}"
            if pk:
                definition += " PRIMARY KEY AUTOINCREMENT" if "INT" in (col_type or "").upper() else " PRIMARY KEY"
            elif notnull:
                definition += " NOT NULL"
            if default is not None:
                definition += f" DEFAULT {default}"
            if name == "external_id" and "UNIQUE" in definition.upper():
                definition = definition.replace(" UNIQUE", "")
            col_defs.append(definition)

        cursor.execute("ALTER TABLE events RENAME TO events_old")
        cursor.execute(f"CREATE TABLE events ({', '.join(col_defs)})")

        cols_csv = ", ".join(col_names)
        cursor.execute(f"INSERT INTO events ({cols_csv}) SELECT {cols_csv} FROM events_old")
        cursor.execute("DROP TABLE events_old")

        repair = _fk_repair()
        repair.fix_foreign_key_table_references(cursor, "events_old", "events")

        cursor.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS {COMPOSITE_INDEX} ON events(external_id, source)")

        conn.commit()
        return True, "Rebuilt events table with composite unique on (external_id, source)"
    except Exception as e:
        conn.rollback()
        logger.error("Migration failed: %s", e)
        return False, f"Failed to add composite unique on events: {e}"
    finally:
        conn.close()
