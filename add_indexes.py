#!/usr/bin/env python3
"""
DEPRECATED: Use `python run_migrations.py` instead.

This script duplicated migrations/2024_01_add_indexes.py.
Kept as a thin wrapper for backward compatibility.
"""

import sys

from run_migrations import run_migrations

if __name__ == "__main__":
    print("Note: add_indexes.py is deprecated. Running run_migrations.py instead.")
    sys.exit(0 if run_migrations() else 1)
