#!/usr/bin/env python3
"""CLI wrapper for PPV enrichment queue cleanup."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from services.ppv.queue_cleanup import cleanup_ppv_queue


def main() -> None:
    parser = argparse.ArgumentParser(description="Mark non-enrichable PPV channels as skipped")
    parser.add_argument("--dry-run", action="store_true", help="Report counts without updating DB")
    parser.add_argument("--account-id", type=int, default=None)
    args = parser.parse_args()

    with app.app_context():
        result = cleanup_ppv_queue(dry_run=args.dry_run, account_id=args.account_id)

    mode = "DRY RUN" if result["dry_run"] else "APPLIED"
    print(f"[{mode}] marked_skipped={result['marked_skipped']} still_enrichable={result['still_enrichable']}")
    for reason, count in sorted(result["by_reason"].items(), key=lambda x: -x[1]):
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
