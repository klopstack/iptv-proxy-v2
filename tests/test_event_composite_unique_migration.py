"""Tests for events composite (external_id, source) unique migration."""

import importlib.util
import sqlite3

import pytest


def _load_migration():
    spec = importlib.util.spec_from_file_location(
        "mig_event_composite_unique",
        "migrations/legacy_sqlite/2026_06_05_event_composite_external_id_source.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _create_legacy_events_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            external_id VARCHAR(50) NOT NULL UNIQUE,
            source VARCHAR(20) DEFAULT 'thesportsdb' NOT NULL,
            home_team_id VARCHAR(50) NOT NULL,
            home_team_name VARCHAR(200) NOT NULL,
            away_team_id VARCHAR(50) NOT NULL,
            away_team_name VARCHAR(200) NOT NULL,
            scheduled_at DATETIME NOT NULL
        )
        """
    )
    conn.commit()


@pytest.mark.migrations
class TestEventCompositeUniqueMigration:
    def test_allows_same_external_id_across_sources(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        _create_legacy_events_table(conn)
        conn.execute(
            "INSERT INTO events (external_id, source, home_team_id, home_team_name, away_team_id, away_team_name, scheduled_at) "
            "VALUES ('123', 'thesportsdb', '1', 'A', '2', 'B', '2026-01-01')"
        )
        conn.commit()
        conn.close()

        mod = _load_migration()
        ok, _msg = mod.migrate(str(db_path))
        assert ok is True

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO events (external_id, source, home_team_id, home_team_name, away_team_id, away_team_name, scheduled_at) "
            "VALUES ('123', 'mlb_stats_api', '3', 'C', '4', 'D', '2026-01-01')"
        )
        conn.commit()
        count = conn.execute("SELECT COUNT(*) FROM events WHERE external_id='123'").fetchone()[0]
        conn.close()
        assert count == 2

    def test_migration_idempotent(self, tmp_path):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(db_path)
        _create_legacy_events_table(conn)
        conn.execute("CREATE UNIQUE INDEX idx_event_external_id_source ON events(external_id, source)")
        conn.commit()
        conn.close()

        mod = _load_migration()
        ok, msg = mod.migrate(str(db_path))
        assert ok is True
        assert "already exists" in msg
