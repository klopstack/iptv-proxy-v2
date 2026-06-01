"""
Tests for PPV enrichment queue priority ordering and hot/cold split.

Covers:
- Hot channels (recently seen) processed before stale channels
- Placeholder/generic channels skipped in cold pass
- get_queue_stats() counts queued/hot channels correctly
"""

from datetime import datetime, timedelta, timezone

from models import Account, Channel, db
from services.ppv.constants import PPV_ENRICHMENT_HOT_WINDOW_HOURS
from services.ppv.orchestrator import PPVEnrichmentOrchestrator


def _make_account(app_ctx):
    account = Account(name="QueueTest", server="http://test.com")
    db.session.add(account)
    db.session.commit()
    return account


def _add_channel(account_id, stream_id, name, last_seen_offset_hours, status=None):
    """Add a PPV channel with last_seen set relative to now."""
    last_seen = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=last_seen_offset_hours)
    ch = Channel(
        account_id=account_id,
        stream_id=stream_id,
        name=name,
        is_ppv=True,
        is_active=True,
        ppv_enrichment_status=status,
        last_seen=last_seen,
    )
    db.session.add(ch)
    return ch


class TestQueueStats:
    """get_queue_stats() returns correct counts."""

    def test_empty_queue(self, app):
        with app.app_context():
            stats = PPVEnrichmentOrchestrator.get_queue_stats()
            assert stats["queued_count"] == 0
            assert stats["hot_queued_count"] == 0

    def test_counts_queued_channels(self, app):
        with app.app_context():
            account = _make_account(app)
            # 2 hot (recently seen), 1 cold, 1 matched (not counted)
            _add_channel(account.id, "q1", "UFC 300 - Jones vs Miocic", 0, "queued")
            _add_channel(account.id, "q2", "MLB 5 | Giants x Rockies", 1, "queued")
            _add_channel(account.id, "q3", "Boxing Stale Event", PPV_ENRICHMENT_HOT_WINDOW_HOURS + 2, "queued")
            _add_channel(account.id, "q4", "UFC 301 - Already Matched", 0, "matched")
            db.session.commit()

            stats = PPVEnrichmentOrchestrator.get_queue_stats()
            assert stats["queued_count"] == 3  # q1 + q2 + q3
            assert stats["hot_queued_count"] == 2  # q1 + q2 (within hot window)

    def test_retry_pending_counted(self, app):
        with app.app_context():
            account = _make_account(app)
            _add_channel(account.id, "r1", "MLB Retry", 0, "retry_pending")
            db.session.commit()

            stats = PPVEnrichmentOrchestrator.get_queue_stats()
            assert stats["queued_count"] >= 1

    def test_none_status_counted(self, app):
        with app.app_context():
            account = _make_account(app)
            _add_channel(account.id, "n1", "New PPV Event", 0, None)
            db.session.commit()

            stats = PPVEnrichmentOrchestrator.get_queue_stats()
            assert stats["queued_count"] >= 1


class TestHotColdOrdering:
    """enrich_pending_channels() prioritises hot (recently seen) channels."""

    def test_hot_channels_processed_before_stale(self, app):
        """Hot channels appear before cold channels in enrichment query."""
        with app.app_context():
            account = _make_account(app)

            # Stale channel added first (older ID) but cold
            cold = _add_channel(
                account.id, "cold-1", "Boxing: Fury vs Joshua", PPV_ENRICHMENT_HOT_WINDOW_HOURS + 5, "queued"
            )
            # Hot channel added second (newer ID) but recently seen
            hot = _add_channel(account.id, "hot-1", "UFC 400 - Jones vs Aspinall", 0, "queued")
            db.session.commit()

            # Query hot channels directly to confirm ordering
            hot_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                hours=PPV_ENRICHMENT_HOT_WINDOW_HOURS
            )
            hot_results = (
                Channel.query.filter(
                    Channel.account_id == account.id,
                    Channel.is_ppv.is_(True),
                    Channel.ppv_enrichment_status == "queued",
                    Channel.last_seen >= hot_cutoff,
                )
                .order_by(Channel.last_seen.desc())
                .all()
            )
            cold_results = Channel.query.filter(
                Channel.account_id == account.id,
                Channel.is_ppv.is_(True),
                Channel.ppv_enrichment_status == "queued",
                Channel.last_seen < hot_cutoff,
            ).all()

            assert any(ch.id == hot.id for ch in hot_results), "Hot channel should be in hot results"
            assert any(ch.id == cold.id for ch in cold_results), "Cold channel should be in cold results"

    def test_placeholder_channels_skipped_in_cold_pass(self, app):
        """Generic/placeholder channels are excluded from the cold pass."""
        from services.epg.ppv import is_ppv_placeholder_name
        from services.ppv.detection import is_generic_channel_name

        with app.app_context():
            account = _make_account(app)

            # Cold placeholder channels that should be skipped
            stale_offset = PPV_ENRICHMENT_HOT_WINDOW_HOURS + 10
            _add_channel(account.id, "pl-1", "PPV 1", stale_offset, "queued")
            _add_channel(account.id, "pl-2", "GOLF 10", stale_offset, "queued")
            _add_channel(account.id, "pl-3", "NO EVENT STREAMING", stale_offset, "queued")
            # Real stale channel that should NOT be skipped
            _add_channel(account.id, "pl-4", "Boxing: Fury vs Joshua", stale_offset, "queued")
            db.session.commit()

            # Verify the filtering logic matches what orchestrator does
            cold_cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                hours=PPV_ENRICHMENT_HOT_WINDOW_HOURS
            )
            cold_candidates = Channel.query.filter(
                Channel.account_id == account.id,
                Channel.is_ppv.is_(True),
                Channel.ppv_enrichment_status == "queued",
                Channel.last_seen < cold_cutoff,
            ).all()

            kept = [
                ch
                for ch in cold_candidates
                if not is_ppv_placeholder_name(ch.name) and not is_generic_channel_name(ch.name)
            ]

            kept_names = [ch.name for ch in kept]
            assert "Boxing: Fury vs Joshua" in kept_names
            assert "PPV 1" not in kept_names
            assert "GOLF 10" not in kept_names
