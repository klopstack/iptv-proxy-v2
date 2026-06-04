"""Repair foreign keys left pointing at *_old tables after table-rebuild migrations."""

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

_REPAIRS = (
    ("accounts_old", "accounts"),
    ("epg_sources_old", "epg_sources"),
)


def migrate(db_path):
    repair = _fk_repair()
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        needed = [pair for pair in _REPAIRS if repair.has_fk_reference_to(cursor, pair[0])]
        if not needed:
            return True, "Stale foreign key references already repaired, skipping"

        messages = []
        for old_table, new_table in needed:
            count = repair.fix_foreign_key_table_references(cursor, old_table, new_table)
            messages.append(f"{old_table}->{new_table} ({count} schema rows)")

        conn.commit()

        cursor.execute("PRAGMA foreign_key_check")
        violations = cursor.fetchall()
        if violations:
            return False, f"foreign_key_check failed after repair: {violations}"

        return True, "Repaired stale foreign keys: " + "; ".join(messages)
    except Exception as e:
        conn.rollback()
        logger.error("Error repairing stale foreign key references: %s", e)
        return False, f"Error: {e}"
    finally:
        conn.close()
