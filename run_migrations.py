#!/usr/bin/env python3
"""
Run all database migrations in order.

This script:
1. Discovers all migration files in the migrations/ directory
2. Runs them in alphabetical order (by filename)
3. Each migration is idempotent and can be run multiple times safely
4. Reports success/failure for each migration

Usage:
    python run_migrations.py
    
Environment Variables:
    DATABASE_URL: Path to database (default: sqlite:///data/iptv_proxy.db)
"""

import os
import sys
import importlib.util
from pathlib import Path


def get_database_path():
    """Get database path from environment or use default."""
    db_path = os.getenv("DATABASE_URL", "sqlite:///data/iptv_proxy.db")

    # Normalize SQLite URLs
    if db_path.startswith("sqlite:///"):
        db_path = db_path.replace("sqlite:///", "")
    elif db_path.startswith("sqlite://"):
        db_path = db_path.replace("sqlite://", "")

    return db_path


def discover_migrations():
    """Find all migration files in the migrations directory."""
    migrations_dir = Path(__file__).parent / "migrations"

    if not migrations_dir.exists():
        return []

    # Find all Python files except __init__.py
    migration_files = sorted(
        [f for f in migrations_dir.glob("*.py") if f.name != "__init__.py" and not f.name.startswith(".")]
    )

    return migration_files


def load_migration(migration_file):
    """Load a migration module from file."""
    spec = importlib.util.spec_from_file_location(migration_file.stem, migration_file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migrations():
    """Run all migrations in order."""
    db_path = get_database_path()

    # Check if database exists
    if not os.path.exists(db_path):
        print(f"⚠️  Database not found at: {db_path}")
        print("   Database will be created on first app startup")
        return True

    print("=" * 60)
    print("IPTV Proxy v2 - Database Migrations")
    print("=" * 60)
    print(f"Database: {db_path}")
    print()

    # Discover migrations
    migrations = discover_migrations()

    if not migrations:
        print("ℹ️  No migrations found")
        return True

    print(f"Found {len(migrations)} migration(s)")
    print()

    # Run each migration
    success_count = 0
    skip_count = 0
    fail_count = 0

    for migration_file in migrations:
        migration_name = migration_file.stem
        print(f"Running migration: {migration_name}")

        try:
            # Load and execute migration
            migration_module = load_migration(migration_file)

            if not hasattr(migration_module, "migrate"):
                print(f"  ⚠️  Skipping: No migrate() function found")
                skip_count += 1
                continue

            success, message = migration_module.migrate(db_path)

            if success:
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
    print(f"Summary: {success_count} applied, {skip_count} skipped, {fail_count} failed")
    print("=" * 60)

    return fail_count == 0


if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)
