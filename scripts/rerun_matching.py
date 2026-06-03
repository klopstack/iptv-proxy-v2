#!/usr/bin/env python3
"""
Re-run PPV channel matching or re-queue channels for enrichment.

Modes:
- Default: re-match all PPV channels via calendar enrichment (legacy behavior).
- --status no_match: re-queue no_match channels without clearing links (post-deploy workflow).
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import app
from models import Channel, EventChannelLink, db
from services.ppv.enrichment import get_calendar_enrichment_service
from services.ppv.requeue import requeue_ppv_channels


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


def requeue_channels(
    account_id=None,
    prefix=None,
    dry_run=True,
    since_last_deploy=False,
    include_skipped=False,
):
    """Re-queue PPV channels by enrichment status (default: no_match)."""
    print("=" * 80)
    print("PPV CHANNEL RE-QUEUE")
    print("=" * 80)
    print()

    result = requeue_ppv_channels(
        account_id=account_id,
        prefix=prefix,
        dry_run=dry_run,
        since_last_deploy=since_last_deploy,
        include_skipped=include_skipped,
    )

    label = "Would queue" if dry_run else "Queued"
    print(f"{label} {result['queued']} channel(s) with status(es): {', '.join(result['statuses'])}")
    if since_last_deploy:
        print("(filtered to channels last attempted before deploy)")
    if dry_run:
        print()
        print("DRY RUN - No changes made. Run with --execute to apply.")
    else:
        print()
        print("Run enrichment processing to drain the queue:")
        print("  curl -X POST http://127.0.0.1:8000/api/ppv-enrichment/process")
    print()
    return result["queued"]


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
    parser = argparse.ArgumentParser(description="Re-run PPV channel matching or re-queue channels")
    parser.add_argument("--account-id", type=int, help="Limit to a specific account ID")
    parser.add_argument(
        "--clear-existing",
        action="store_true",
        help="Clear existing matches before re-matching (default is to keep and add new)",
    )
    parser.add_argument("--execute", action="store_true", help="Apply changes (default is dry run)")
    parser.add_argument(
        "--status",
        choices=["no_match"],
        help="Re-queue channels with this enrichment status instead of full re-match",
    )
    parser.add_argument(
        "--prefix",
        help="Only re-queue channels whose name starts with this prefix (e.g. 'Tennis:')",
    )
    parser.add_argument(
        "--since-last-deploy",
        action="store_true",
        help="Only re-queue channels last attempted before ppv_last_deploy_at setting",
    )
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        help="Also re-queue skipped channels (use with --status no_match)",
    )

    args = parser.parse_args()
    dry_run = not args.execute

    with app.app_context():
        if args.status == "no_match":
            requeue_channels(
                account_id=args.account_id,
                prefix=args.prefix,
                dry_run=dry_run,
                since_last_deploy=args.since_last_deploy,
                include_skipped=args.include_skipped,
            )
        else:
            rerun_matching(args.account_id, args.clear_existing, dry_run=dry_run)


if __name__ == "__main__":
    main()
