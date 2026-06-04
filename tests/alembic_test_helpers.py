"""Helpers for Alembic migration tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def alembic_upgrade_sqlite(db_path: str | Path) -> None:
    """Apply Alembic migrations to a SQLite file in an isolated subprocess."""
    uri = f"sqlite:///{db_path}"
    env = os.environ.copy()
    env["DATABASE_URL"] = uri
    env.setdefault("DISABLE_IN_WORKER_SCHEDULER", "true")
    result = subprocess.run(
        [sys.executable, "-m", "flask", "db", "upgrade"],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"flask db upgrade failed for {uri}:\nstdout: {result.stdout}\nstderr: {result.stderr}")
