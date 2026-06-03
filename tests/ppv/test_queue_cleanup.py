"""Tests for PPV queue cleanup."""

from models import Account, Channel, db
from services.ppv.queue_cleanup import cleanup_ppv_queue


class TestCleanupPpvQueue:
    def test_dry_run_counts_without_persisting(self, app):
        with app.app_context():
            account = Account(name="QC", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            ch = Channel(
                account_id=account.id,
                stream_id="dry1",
                name="PPV 1",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add(ch)
            db.session.commit()

            result = cleanup_ppv_queue(dry_run=True)
            assert result["dry_run"] is True
            assert result["marked_skipped"] >= 1
            db.session.refresh(ch)
            assert ch.ppv_enrichment_status == "queued"

    def test_commit_marks_skipped(self, app):
        with app.app_context():
            account = Account(name="QC2", server="http://t", username="u", password="p", enabled=True)
            db.session.add(account)
            db.session.commit()

            placeholder = Channel(
                account_id=account.id,
                stream_id="c1",
                name="PPV 2",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            event_ch = Channel(
                account_id=account.id,
                stream_id="c2",
                name="NBA: Lakers vs Celtics | 2026-06-15 19:00",
                is_ppv=True,
                ppv_enrichment_status="queued",
            )
            db.session.add_all([placeholder, event_ch])
            db.session.commit()

            result = cleanup_ppv_queue(dry_run=False, account_id=account.id)
            assert result["dry_run"] is False
            assert result["marked_skipped"] >= 1
            assert result["still_enrichable"] >= 1

            db.session.refresh(placeholder)
            db.session.refresh(event_ch)
            assert placeholder.ppv_enrichment_status == "skipped"
            assert event_ch.ppv_enrichment_status == "queued"

    def test_account_filter_limits_scope(self, app):
        with app.app_context():
            acc1 = Account(name="A1", server="http://t", username="u", password="p", enabled=True)
            acc2 = Account(name="A2", server="http://t", username="u2", password="p", enabled=True)
            db.session.add_all([acc1, acc2])
            db.session.commit()

            ch1 = Channel(account_id=acc1.id, stream_id="a1", name="PPV 1", is_ppv=True, ppv_enrichment_status="queued")
            ch2 = Channel(account_id=acc2.id, stream_id="a2", name="PPV 1", is_ppv=True, ppv_enrichment_status="queued")
            db.session.add_all([ch1, ch2])
            db.session.commit()

            cleanup_ppv_queue(dry_run=False, account_id=acc1.id)

            db.session.refresh(ch1)
            db.session.refresh(ch2)
            assert ch1.ppv_enrichment_status == "skipped"
            assert ch2.ppv_enrichment_status == "queued"
