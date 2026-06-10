"""Tests for PPV enrichability classification."""

import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from services.ppv import enrichability
from services.ppv.enrichability import (
    classify_ppv_enrichment,
    is_ppv_section_header,
    is_unsupported_college_sport_title,
    is_unsupported_league_title,
    stale_archive_date_from_title,
)
from services.ppv.detection import is_bogus_extracted_competitors, is_studio_show_title
from services.ppv.enrichment import PPVCalendarEnrichmentService
from services.ppv.extraction import PPVEventExtractor

STALE_FIXTURE = Path(__file__).parent / "fixtures" / "stale_espn_play.json"
BOXING_FIXTURE = Path(__file__).parent / "fixtures" / "boxing_channels.json"
CHAMPIONSHIP_FIXTURE = Path(__file__).parent / "fixtures" / "championship_playoff.json"
WCWS_FIXTURE = Path(__file__).parent / "fixtures" / "wcws_channels.json"


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


class TestStaleArchive:
    @pytest.fixture
    def stale_channels(self):
        return json.loads(STALE_FIXTURE.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "fixture_id",
        ["espn_play_2023", "espn_play_2024"],
    )
    def test_espn_play_archive_titles_skipped(self, stale_channels, fixture_id):
        row = next(r for r in stale_channels if r["id"] == fixture_id)
        assert classify_ppv_enrichment(row["name"]) == "stale_archive"
        assert classify_ppv_enrichment(row["name"], cheap_only=True) == "stale_archive"

    def test_stale_archive_parses_us_date(self, stale_channels):
        row = next(r for r in stale_channels if r["id"] == "espn_play_2023")
        parsed = stale_archive_date_from_title(row["name"])
        assert parsed is not None
        assert parsed.year == 2023
        assert parsed.month == 11
        assert parsed.day == 9

    def test_current_event_not_stale_archive(self, stale_channels):
        row = next(r for r in stale_channels if r["id"] == "current_peacock")
        assert classify_ppv_enrichment(row["name"]) is None


class TestBoxingNoEventDate:
    @pytest.fixture
    def boxing_channels(self):
        return json.loads(BOXING_FIXTURE.read_text(encoding="utf-8"))

    def test_boxing_without_date_skipped(self, boxing_channels):
        row = next(r for r in boxing_channels if r["id"] == "usyk_verhoeven")
        assert classify_ppv_enrichment(row["name"]) == "no_event_date"

    def test_boxing_with_date_still_enrichable(self, boxing_channels):
        row = next(r for r in boxing_channels if r["id"] == "boxing_with_date")
        assert classify_ppv_enrichment(row["name"]) is None

    def test_non_boxing_without_date_not_skipped(self, boxing_channels):
        row = next(r for r in boxing_channels if r["id"] == "non_boxing_no_date")
        assert classify_ppv_enrichment(row["name"]) is None


class TestTrackBUnsupportedLeague:
    @pytest.fixture
    def championship_channels(self):
        return json.loads(CHAMPIONSHIP_FIXTURE.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "fixture_id",
        ["sierra_leone_premier", "aruba_league"],
    )
    def test_obscure_dazn_leagues_skipped(self, championship_channels, fixture_id):
        row = next(r for r in championship_channels if r["id"] == fixture_id)
        assert classify_ppv_enrichment(row["name"]) == "unsupported_league"
        assert classify_ppv_enrichment(row["name"], cheap_only=True) == "unsupported_league"

    def test_major_league_region_not_skipped(self, championship_channels):
        row = next(r for r in championship_channels if r["id"] == "english_premier_not_skipped")
        assert classify_ppv_enrichment(row["name"]) is None
        assert is_unsupported_league_title(row["name"]) is False

    def test_charlton_leicester_still_enrichable(self, championship_channels):
        """Championship playoff absent from TSDB; remain enrichable for future requeue."""
        row = next(r for r in championship_channels if r["id"] == "charlton_leicester")
        assert classify_ppv_enrichment(row["name"]) is None
        assert is_unsupported_league_title(row["name"]) is False


class TestStudioShowSkip:
    """Studio/analysis programs should skip enrichment, not no_match."""

    @pytest.mark.parametrize(
        "name",
        [
            "NHL Tonight @ Jun 10 12:00 PM :Viaplay SE  01",
            "Jays Talk Plus June 10 @ Jun 10 10:00 AM :Sportsnet+  04",
            "NBA Today A @ Jun 10 3:00 PM :TSN+  51",
            "US | Sport News Live @ Jun 10 6:00 PM",
        ],
    )
    def test_studio_show_titles_skipped(self, name):
        assert is_studio_show_title(name) is True
        assert classify_ppv_enrichment(name) == "no_competitors"

    def test_bogus_competitor_pair_detection(self):
        assert is_bogus_extracted_competitors(("Tonight", "Jun")) is True
        assert is_bogus_extracted_competitors(("Jays Talk Plus June", "Jun")) is True
        assert is_bogus_extracted_competitors(("Arsenal", "Brighton")) is False

    def test_real_vs_event_not_studio_show(self):
        name = "UK: DAZN PPV 1 - Arsenal vs Brighton | 2026-06-15 | 17:15"
        assert is_studio_show_title(name) is False
        assert classify_ppv_enrichment(name) is None


class TestTrackAUnsupportedCollegeSport:
    @pytest.fixture
    def wcws_channels(self):
        return json.loads(WCWS_FIXTURE.read_text(encoding="utf-8"))

    @pytest.mark.parametrize(
        "fixture_id",
        ["wcws_texas_tech", "btn_plus_baseball"],
    )
    def test_wcws_and_btn_plus_skipped(self, wcws_channels, fixture_id):
        row = next(r for r in wcws_channels if r["id"] == fixture_id)
        assert classify_ppv_enrichment(row["name"]) == "unsupported_sport"
        assert classify_ppv_enrichment(row["name"], cheap_only=True) == "unsupported_sport"

    def test_wcws_ranking_prefix_stripped_from_competitors(self, wcws_channels):
        row = next(r for r in wcws_channels if r["id"] == "wcws_texas_tech")
        extractor = PPVEventExtractor()
        result = extractor.extract_all(row["name"])
        assert result["competitors"] == tuple(row["expect_competitors"])

    def test_ncaa_football_not_unsupported_sport(self, wcws_channels):
        row = next(r for r in wcws_channels if r["id"] == "ncaa_football_still_enrichable")
        assert is_unsupported_college_sport_title(row["name"]) is False
        assert classify_ppv_enrichment(row["name"], cheap_only=True) is None


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

            from services.ppv.enrichment_post_hooks import (
                EnrichmentPostHooks,
                get_enrichment_post_hooks,
                set_enrichment_post_hooks,
            )

            original_hooks = get_enrichment_post_hooks()
            set_enrichment_post_hooks(EnrichmentPostHooks.noop())
            try:
                with patch.object(
                    service.extractor,
                    "extract_all",
                    wraps=service.extractor.extract_all,
                ) as mock_extract, patch.object(service, "_group_by_date", return_value={}), patch.object(
                    service, "_update_stats"
                ), patch(
                    "services.ppv.enrichment.sync_enrichment_status_from_links"
                ):
                    result = service.enrich_channels(channels, fetch_details=False)
            finally:
                set_enrichment_post_hooks(original_hooks)

            assert mock_extract.call_count <= len(channels)
            assert result["no_extraction"] >= 1
