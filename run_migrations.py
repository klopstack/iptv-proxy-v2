#!/usr/bin/env python3
"""
Run all database migrations in order.

This script:
1. Ensures schema_migrations tracking table exists
2. Discovers migration files in migrations/ (alphabetical order)
3. Skips migrations already recorded in schema_migrations
4. Records each successful migration (including idempotent skips)

Usage:
    python run_migrations.py

Environment Variables:
    DATABASE_URL: Path to database (default: sqlite:///data/iptv_proxy.db)
"""

import importlib.util
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def get_database_path():
    """Get database path from environment or use default."""
    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")

    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")

    return db_path


def ensure_schema_migrations_table(db_path: str) -> None:
    """Create schema_migrations table if it does not exist."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name VARCHAR(255) UNIQUE NOT NULL,
                applied_at DATETIME NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def get_applied_migrations(db_path: str) -> set:
    """Return set of migration names already applied."""
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT migration_name FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        return set()
    finally:
        conn.close()


def record_migration(db_path: str, migration_name: str) -> None:
    """Record a migration as applied."""
    conn = sqlite3.connect(db_path)
    try:
        applied_at = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
        conn.execute(
            "INSERT OR IGNORE INTO schema_migrations (migration_name, applied_at) VALUES (?, ?)",
            (migration_name, applied_at),
        )
        conn.commit()
    finally:
        conn.close()


def discover_migrations():
    """Find all migration files in the migrations directory."""
    migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        return []

    return sorted(
        [
            f
            for f in migrations_dir.glob("*.py")
            if f.name != "__init__.py" and not f.name.startswith(".") and not f.name.startswith("_")
        ]
    )


def load_migration(migration_file):
    """Load a migration module from file."""
    spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations(db_path: str | None = None):
    """Run pending migrations in order."""
    if db_path is None:
        db_path = get_database_path()

    if not os.path.exists(db_path):
        print(f"⚠️  Database not found at: {db_path}")
        print("   Database will be created on first app startup")
        return True

    ensure_schema_migrations_table(db_path)
    applied = get_applied_migrations(db_path)

    print("=" * 60)
    print("IPTV Proxy v2 - Database Migrations")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Already applied: {len(applied)} migration(s)")
    print()

    migrations = discover_migrations()
    if not migrations:
        print("ℹ️  No migrations found")
        return True

    print(f"Found {len(migrations)} migration file(s)")
    print()

    success_count = 0
    skip_count = 0
    fail_count = 0
    tracked_skip_count = 0

    for migration_file in migrations:
        migration_name = migration_file.stem

        if migration_name in applied:
            tracked_skip_count += 1
            continue

        print(f"Running migration: {migration_name}")

        try:
            migration_module = load_migration(migration_file)

            if not hasattr(migration_module, "migrate"):
                print("  ⚠️  Skipping: No migrate() function found")
                skip_count += 1
                continue

            success, message = migration_module.migrate(db_path)

            if success:
                record_migration(db_path, migration_name)
                if "skipping" in message.lower() or "already" in message.lower():
                    print(f"  ⏭️  {message}")
                    skip_count += 1
                else:
                    print(f"  ✅ {message}")
                    success_count += 1
            else:
                print(f"  ❌ {message}")
                fail_count += 1

        except Exception as e:
            print(f"  ❌ Error: {e}")
            fail_count += 1

    print()
    print("=" * 60)
    print(
        f"Summary: {success_count} applied, {skip_count} skipped (idempotent), "
        f"{tracked_skip_count} skipped (tracked), {fail_count} failed"
    )
    print("=" * 60)

    return fail_count == 0


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
