"""Helpers to fix SQLite foreign keys still pointing at renamed *_old tables."""

import sqlite3


def fix_foreign_key_table_references(cursor: sqlite3.Cursor, old_table: str, new_table: str) -> int:
    """
    Rewrite sqlite_master DDL so FOREIGN KEY ... REFERENCES old_table -> new_table.

    SQLite keeps the original referenced table name when a parent table is renamed
    and rebuilt; child tables must be patched in sqlite_master.

    Returns:
        Number of schema objects updated.
    """
    cursor.execute("PRAGMA writable_schema=ON")
    updated = 0
    for needle, replacement in (
        (f'"{old_table}"', f'"{new_table}"'),
        (old_table, new_table),
    ):
        cursor.execute(
            "UPDATE sqlite_master SET sql = replace(sql, ?, ?) WHERE sql IS NOT NULL AND instr(sql, ?) > 0",
            (needle, replacement, old_table),
        )
        updated += cursor.rowcount
    cursor.execute("PRAGMA writable_schema=OFF")
    return updated


def has_fk_reference_to(cursor: sqlite3.Cursor, table_name: str) -> bool:
    """Return True if any table DDL still references table_name in a FOREIGN KEY."""
    cursor.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND sql IS NOT NULL AND instr(sql, ?) > 0 LIMIT 1",
        (table_name,),
    )
    return cursor.fetchone() is not None
