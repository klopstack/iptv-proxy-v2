"""Tests for PPV enrichability classification."""

from unittest.mock import Mock, patch

from services.ppv import enrichability
from services.ppv.enrichability import classify_ppv_enrichment, is_ppv_section_header
from services.ppv.enrichment import PPVCalendarEnrichmentService


class TestSectionHeader:
    def test_hash_wrapped_header(self):
        assert is_ppv_section_header("##### DAZN PPV #####") is True
        assert classify_ppv_enrichment("##### DAZN PPV #####") == "section_header"

    def test_vip_header(self):
        assert classify_ppv_enrichment("###### ES| DAZN PPV VIP ######") == "section_header"


class TestEnrichability:
    def test_generic_ppv_slot(self):
        assert classify_ppv_enrichment("PPV 1") == "generic_name"

    def test_no_event_streaming(self):
        assert classify_ppv_enrichment("UK: DAZN PPV 1 - NO EVENT STREAMING") == "placeholder_name"

    def test_real_event(self):
        assert classify_ppv_enrichment("UK: DAZN PPV 1 - Arsenal vs Brighton | 2026-06-15 | 17:15") is None

    def test_wnba_event(self):
        name = "US (WNBA 03) | Portland Fire at Golden State Valkyries (2026-06-03 02:00:00)"
        assert classify_ppv_enrichment(name) is None

    def test_cheap_only_skips_extract_all(self):
        with patch.object(enrichability._extractor, "extract_all") as mock_extract:
            assert classify_ppv_enrichment("PPV 1", cheap_only=True) == "generic_name"
            assert (
                classify_ppv_enrichment(
                    "UK: DAZN PPV 1 - Arsenal vs Brighton | 2026-06-15 | 17:15",
                    cheap_only=True,
                )
                is None
            )
            mock_extract.assert_not_called()

    def test_precomputed_extraction_skips_extract_all(self):
        extraction = {
            "competitors": ("Arsenal", "Brighton"),
            "date": None,
            "inferred_how": None,
        }
        with patch.object(enrichability._extractor, "extract_all") as mock_extract:
            assert classify_ppv_enrichment("UK: DAZN PPV 1 - Arsenal vs Brighton", extraction) is None
            mock_extract.assert_not_called()


class TestSingleExtractionPerEnrichmentBatch:
    """Regression: extract_all runs at most once per channel per enrich_channels batch."""

    def test_extract_all_call_count_bounded(self, app):
        with app.app_context():
            service = PPVCalendarEnrichmentService(app)
            ch_generic = Mock(ppv_enrichment_status=None)
            ch_generic.name = "PPV 1"
            ch_event = Mock(ppv_enrichment_status=None)
            ch_event.name = "UK: DAZN PPV 1 - Arsenal vs Brighton | 2026-06-15 | 17:15"
            channels = [ch_generic, ch_event]

            with patch.object(
                service.extractor,
                "extract_all",
                wraps=service.extractor.extract_all,
            ) as mock_extract, patch.object(service, "_group_by_date", return_value={}), patch.object(
                service, "_update_stats"
            ), patch(
                "services.ppv.enrichment.sync_enrichment_status_from_links"
            ), patch(
                "services.ppv.enrichment.prune_orphan_ppv_events"
            ):
                result = service.enrich_channels(channels, fetch_details=False)

            assert mock_extract.call_count <= len(channels)
            assert result["no_extraction"] >= 1
