"""Tests for Alembic migrations and schema tracking."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from tests.alembic_test_helpers import alembic_upgrade_sqlite


@pytest.fixture
def temp_db():
    """Temporary SQLite database initialized via Alembic upgrade (matches production boot)."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name

    alembic_upgrade_sqlite(path)

    yield path

    for suffix in ("", "-wal", "-shm"):
        p = Path(f"{path}{suffix}")
        if p.exists():
            p.unlink()


def _sqlite_connect(db_path: str) -> sqlite3.Connection:
    """Open SQLite with foreign key enforcement (matches app runtime)."""
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


class TestAlembicMigrations:
    @pytest.mark.sqlite_only
    def test_upgrade_creates_alembic_version(self, temp_db):
        conn = sqlite3.connect(temp_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'")
        assert cursor.fetchone() is not None
        conn.close()

    @pytest.mark.sqlite_only
    def test_upgrade_creates_core_tables(self, temp_db):
        conn = sqlite3.connect(temp_db)
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "accounts" in tables
        assert "channels" in tables
        assert "playlist_configs" in tables
        assert "epg_programs" in tables

        cursor = conn.execute("PRAGMA table_info(playlist_configs)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "slug" in columns

        conn.close()

        fk_conn = _sqlite_connect(temp_db)
        try:
            assert fk_conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            violations = fk_conn.execute("PRAGMA foreign_key_check").fetchall()
            assert violations == [], f"foreign_key_check violations: {violations}"
        finally:
            fk_conn.close()

    @pytest.mark.sqlite_only
    def test_second_upgrade_is_idempotent(self, temp_db):
        alembic_upgrade_sqlite(temp_db)
        alembic_upgrade_sqlite(temp_db)

        conn = sqlite3.connect(temp_db)
        version_count = conn.execute("SELECT COUNT(*) FROM alembic_version").fetchone()[0]
        head = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        conn.close()
        assert version_count == 1
        assert head == "d5e6f7a8b9c0"

    @pytest.mark.sqlite_only
    def test_upgrade_adds_accounts_column_with_foreign_key_children(self):
        """Legacy production DBs reference accounts via FK; ADD COLUMN must not DROP TABLE."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name

        try:
            alembic_upgrade_sqlite(path, revision="6e7d8c9b0a1f")

            conn = _sqlite_connect(path)
            conn.execute(
                "INSERT INTO accounts (name, server, ppv_visibility) VALUES ('staging', 'http://example', 'show_all')"
            )
            account_id = conn.execute("SELECT id FROM accounts").fetchone()[0]
            conn.execute(
                "INSERT INTO credentials (account_id, username, password) VALUES (?, 'user', 'pass')",
                (account_id,),
            )
            conn.commit()
            conn.close()

            alembic_upgrade_sqlite(path)

            conn = sqlite3.connect(path)
            columns = {row[1] for row in conn.execute("PRAGMA table_info(accounts)").fetchall()}
            head = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            conn.close()
            assert "ppv_show_unmatched_live" in columns
            assert head == "d5e6f7a8b9c0"
        finally:
            for suffix in ("", "-wal", "-shm"):
                p = Path(f"{path}{suffix}")
                if p.exists():
                    p.unlink()

    @pytest.mark.sqlite_only
    def test_upgrade_is_idempotent_when_legacy_columns_already_exist(self):
        """DBs manually patched via legacy_sqlite must survive flask db upgrade."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name

        try:
            alembic_upgrade_sqlite(path, revision="40ca71c79446")

            conn = sqlite3.connect(path)
            conn.execute("ALTER TABLE accounts ADD COLUMN category_tag_grouping TEXT")
            conn.execute("ALTER TABLE accounts ADD COLUMN ppv_show_replay BOOLEAN DEFAULT 1 NOT NULL")
            conn.execute("ALTER TABLE accounts ADD COLUMN ppv_show_historical BOOLEAN DEFAULT 1 NOT NULL")
            conn.execute("ALTER TABLE playlist_configs ADD COLUMN category_tag_grouping TEXT")
            conn.commit()
            conn.close()

            alembic_upgrade_sqlite(path)

            conn = sqlite3.connect(path)
            head = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            conn.close()
            assert head == "d5e6f7a8b9c0"
        finally:
            for suffix in ("", "-wal", "-shm"):
                p = Path(f"{path}{suffix}")
                if p.exists():
                    p.unlink()


@pytest.mark.legacy_migrations
@pytest.mark.sqlite_only
class TestLegacyMigrationRunner:
    """Legacy sqlite3 runner archived in migrations/legacy_sqlite/."""

    def test_schema_migrations_table_from_legacy_runner(self):
        from migrations.legacy_sqlite.run_migrations import ensure_schema_migrations_table

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        try:
            ensure_schema_migrations_table(path)
            conn = sqlite3.connect(path)
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
            assert cursor.fetchone() is not None
            conn.close()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_legacy_migration_chain_after_create_all(self):
        """Legacy path: create_all + run_migrations — kept for parity with pre-113 upgrades."""
        from sqlalchemy import create_engine

        from migrations.legacy_sqlite.run_migrations import get_applied_migrations, run_migrations
        from models import db as _db

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name

        engine = create_engine(f"sqlite:///{path}")
        _db.metadata.create_all(engine)
        engine.dispose()

        try:
            assert run_migrations(path) is True
            applied = get_applied_migrations(path)
            assert len(applied) >= 40
        finally:
            for suffix in ("", "-wal", "-shm"):
                p = Path(f"{path}{suffix}")
                if p.exists():
                    p.unlink(missing_ok=True)
