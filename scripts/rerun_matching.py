#!/usr/bin/env python3
"""
Re-run PPV channel matching.

Re-matches PPV channels to events. Optionally clears existing matches first.
Useful for:
- After improving matching algorithms
- After adding new events to the database
- After improving text extraction
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel, EventChannelLink, db
from services.ppv.enrichment import get_calendar_enrichment_service


def clear_existing_matches(account_id=None, dry_run=True):
    """Clear existing PPV channel matches."""
    query = EventChannelLink.query.join(Channel).filter(Channel.is_ppv == True)  # noqa: E712

    if account_id:
        query = query.filter(Channel.account_id == account_id)

    links = query.all()

    if not links:
        print("No matches to clear.")
        return 0

    print(f"Found {len(links)} existing matches to clear")

    if dry_run:
        print("DRY RUN - No changes made")
        print("Run with --clear-existing to delete these matches")
        return 0

    for link in links:
        db.session.delete(link)

    db.session.commit()
    print(f"✅ Cleared {len(links)} existing matches")
    return len(links)


def rerun_matching(account_id=None, clear_existing=False, dry_run=True):
    """Re-run PPV matching for an account or all accounts."""

    print("=" * 80)
    print("PPV CHANNEL RE-MATCHING")
    print("=" * 80)
    print()

    # Clear existing matches if requested
    cleared = 0
    if clear_existing:
        print("Step 1: Clearing existing matches...")
        cleared = clear_existing_matches(account_id, dry_run)
        print()

    if dry_run:
        print("DRY RUN MODE - Showing what would be done")
        print()

    # Get PPV channels
    query = Channel.query.filter(Channel.is_ppv == True)  # noqa: E712
    if account_id:
        query = query.filter_by(account_id=account_id)

    channels = query.all()

    if not channels:
        print("No PPV channels found.")
        return

    print(f"Step 2: Re-matching {len(channels)} PPV channels...")

    if dry_run:
        print(f"Would match {len(channels)} channels")
        return

    # Run matching
    with app.app_context():
        service = get_calendar_enrichment_service(app)
        results = service.enrich_channels(channels, fetch_details=True)

    # Parse results
    matched = results.get("matched", 0)
    unmatched = results.get("unmatched", 0)
    errors = results.get("errors", 0)

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print(f"Matched:       {matched:5d}")
    print(f"Unmatched:     {unmatched:5d}")
    print(f"Errors:        {errors:5d}")
    print(f"Total:         {matched + unmatched + errors:5d}")

    if matched > 0:
        match_pct = matched / (matched + unmatched) * 100 if (matched + unmatched) > 0 else 0
        print(f"Match rate:    {match_pct:5.1f}%")

    if cleared > 0:
        print(f"\nCleared {cleared} old matches during this run")

    print()


def main():
    parser = argparse.ArgumentParser(description="Re-run PPV channel matching")
    parser.add_argument("--account-id", type=int, help="Match only for specific account ID")
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing matches before re-matching (default is to keep and add new)",
    )
    parser.add_argument("--execute", action="store_true", help="Actually run matching (default is dry run)")

    args = parser.parse_args()

    with app.app_context():
        rerun_matching(args.account_id, args.clear_existing, dry_run=not args.execute)


if __name__ == "__main__":
    main()
