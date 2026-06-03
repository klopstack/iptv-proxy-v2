"""Tests for TODO 66: detail worker session hygiene and enrichment post-hooks."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from models import Event, db
from services.ppv.enrichment.detail_fetch import DetailFetchWorker
from services.ppv.enrichment import PPVCalendarEnrichmentService
from services.ppv.enrichment_post_hooks import EnrichmentPostHooks, get_enrichment_post_hooks, set_enrichment_post_hooks


class TestDetailWorkerSessionHygiene:
    def test_process_detail_item_uses_fresh_session_lifecycle(self, app):
        remove_calls = []

        def fetch_handler(external_id, source, force_refresh):
            return False

        with app.app_context():
            worker = DetailFetchWorker(app, fetch_handler=fetch_handler)
            with patch.object(db.session, "remove", side_effect=lambda: remove_calls.append(1)):
                worker._process_detail_item("123", Event.SOURCE_THESPORTSDB)

        assert len(remove_calls) >= 1

    def test_worker_drains_one_detail_item_from_queue(self, app, db):
        with app.app_context():
            event = Event(
                external_id="worker-1",
                source=Event.SOURCE_THESPORTSDB,
                home_team_id="1",
                home_team_name="Home",
                away_team_id="2",
                away_team_name="Away",
                scheduled_at=datetime(2026, 1, 5, 22, 0),
                status=Event.STATUS_SCHEDULED,
                data_completeness="basic",
            )
            db.session.add(event)
            db.session.commit()

            service = PPVCalendarEnrichmentService(app)
            with patch.object(service.thesportsdb, "get_event_by_id") as mock_api:
                mock_api.return_value = {
                    "strHomeTeam": "Home",
                    "strAwayTeam": "Away",
                    "idHomeTeam": "1",
                    "idAwayTeam": "2",
                    "strTimestamp": "2026-01-05T22:00:00Z",
                    "dateEvent": "2026-01-05",
                    "strTime": "22:00:00",
                    "strStatus": "Scheduled",
                }
                service._detail_worker.queue_detail("worker-1", Event.SOURCE_THESPORTSDB)
                service._detail_worker._process_detail_item("worker-1", Event.SOURCE_THESPORTSDB)

            db.session.refresh(event)
            assert event.data_completeness == "full"
            mock_api.assert_called_once()


class TestEnrichmentNoopPostHooks:
    def test_enrich_channels_without_epg_side_effects(self, app):
        original = get_enrichment_post_hooks()
        try:
            set_enrichment_post_hooks(EnrichmentPostHooks.noop())
            with app.app_context():
                service = PPVCalendarEnrichmentService(app)
                ch = MagicMock()
                ch.name = "UFC Test"
                ch.ppv_enrichment_status = None

                with patch.object(service, "_extract_all_channels") as mock_extract, patch.object(
                    service, "_group_by_date", return_value={}
                ), patch.object(service, "_update_stats"), patch(
                    "services.ppv.enrichment.sync_enrichment_status_from_links"
                ), patch(
                    "services.ppv.cleanup.sync_ppv_epg_after_enrichment"
                ) as mock_sync, patch(
                    "services.ppv.cleanup.prune_orphan_ppv_events"
                ) as mock_prune:
                    mock_extract.return_value = [
                        (
                            ch,
                            {
                                "is_placeholder": False,
                                "is_inactive": False,
                                "competitors": ("A", "B"),
                                "date": datetime.now(timezone.utc),
                            },
                        )
                    ]
                    service.enrich_channels([ch], fetch_details=False)

                mock_sync.assert_not_called()
                mock_prune.assert_not_called()
        finally:
            set_enrichment_post_hooks(original)

    def test_default_hooks_invoke_epg_sync_when_matched(self, app):
        with app.app_context():
            results = {"matched": 2, "processed": 2}
            with patch(
                "services.ppv.cleanup.sync_ppv_epg_after_enrichment",
                return_value={"epg_mappings": 1},
            ) as mock_sync:
                get_enrichment_post_hooks().run(results)
            mock_sync.assert_called_once_with(2)


class TestLlmDoesNotBlockApiQueue:
    def test_llm_runs_only_when_api_queues_idle(self, app):
        def fetch_handler(external_id, source, force_refresh):
            return True

        def llm_handler(external_id):
            pass

        worker = DetailFetchWorker(
            app,
            fetch_handler=fetch_handler,
            llm_handler=llm_handler,
        )
        worker._llm_queue.put("llm-1")
        worker._detail_queue.put(("api-1", Event.SOURCE_THESPORTSDB))

        with patch.object(worker, "_process_llm_item") as mock_llm:
            worker._drain_llm_when_idle()
            mock_llm.assert_not_called()

        worker._detail_queue.get_nowait()
        with patch.object(worker, "_process_llm_item") as mock_llm:
            worker._drain_llm_when_idle()
            mock_llm.assert_called_once_with("llm-1")
