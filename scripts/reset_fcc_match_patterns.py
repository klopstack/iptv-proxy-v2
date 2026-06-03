#!/usr/bin/env python3
"""Reset FCC match patterns to migration defaults (operator CLI).

Usage (from repo root with app context):
    flask reset-fcc-patterns

Or:
    python scripts/reset_fcc_match_patterns.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    from app import app

    with app.app_context():
        from flask import current_app

        current_app.cli.main(args=["reset-fcc-patterns"], standalone_mode=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
