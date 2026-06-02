"""Tests for PPV enrichment batch drain loop."""

from unittest.mock import MagicMock, patch

from services.jobs.ppv_enrichment import run_ppv_enrichment


class TestEnrichmentDrainLoop:
    def test_drains_queue_in_one_run(self, app):
        orchestrator = MagicMock()
        orchestrator.enrich_pending_channels.side_effect = [
            {"channels_processed": 500, "channels_matched": 10, "channels_no_match": 490, "accounts_processed": 1},
            {"channels_processed": 200, "channels_matched": 5, "channels_no_match": 195, "accounts_processed": 1},
        ]
        orchestrator.get_queue_stats.side_effect = [
            {"queued_count": 700},
            {"queued_count": 0},
        ]
        orchestrator.run_enhanced_fallback.return_value = {}

        service = MagicMock()
        with patch("services.ppv.orchestrator.get_ppv_orchestrator", return_value=orchestrator), patch(
            "services.ppv.enrichment.get_calendar_enrichment_service", return_value=service
        ):
            with app.app_context():
                stats = run_ppv_enrichment(app)

        assert orchestrator.enrich_pending_channels.call_count == 2
        assert stats["batches_run"] == 2
        assert stats["channels_processed"] == 700
        service.start_detail_fetcher.assert_called_once()

    def test_stops_when_batch_processes_nothing(self, app):
        orchestrator = MagicMock()
        orchestrator.enrich_pending_channels.return_value = {
            "channels_processed": 0,
            "channels_matched": 0,
            "channels_no_match": 0,
            "accounts_processed": 0,
        }
        orchestrator.get_queue_stats.return_value = {"queued_count": 100}

        with patch("services.ppv.orchestrator.get_ppv_orchestrator", return_value=orchestrator), patch(
            "services.ppv.enrichment.get_calendar_enrichment_service"
        ):
            with app.app_context():
                stats = run_ppv_enrichment(app)

        assert orchestrator.enrich_pending_channels.call_count == 1
        assert stats["batches_run"] == 1
