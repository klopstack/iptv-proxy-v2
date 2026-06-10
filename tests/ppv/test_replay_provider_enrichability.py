"""Tests for Flo/FLSP replay provider enrichability (TODO 129 Track A)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from services.ppv.enrichability import classify_ppv_enrichment
from services.ppv.extraction import PPVEventExtractor
from services.ppv.replay_providers import is_replay_archive_provider

FLOSP_FIXTURE = Path(__file__).parent / "fixtures" / "flosp_replay_channels.json"
STALE_FIXTURE = Path(__file__).parent / "fixtures" / "stale_espn_play.json"


@pytest.fixture(scope="module")
def flosp_channels():
    return json.loads(FLOSP_FIXTURE.read_text(encoding="utf-8"))["channels"]


@pytest.fixture(scope="module")
def stale_channels():
    return json.loads(STALE_FIXTURE.read_text(encoding="utf-8"))


class TestReplayProviderDetection:
    @pytest.mark.parametrize(
        "channel",
        [
            "Flo (FLSP) 110: 2025 Occidental vs Chapman - Mens - 22/10 19:00",
            "US (Flo 481) | [Hockey|2025 Sherbrooke Phoenix vs Chicoutimi Sagueneens Home] (2025-11-01 16:02:30)",
        ],
    )
    def test_detects_flo_providers(self, channel):
        assert is_replay_archive_provider(channel) is True

    def test_espn_play_not_replay_provider(self, stale_channels):
        row = next(r for r in stale_channels if r["id"] == "espn_play_2023")
        assert is_replay_archive_provider(row["name"]) is False


class TestFloEnrichability:
    @pytest.mark.parametrize(
        "row", json.loads(FLOSP_FIXTURE.read_text(encoding="utf-8"))["channels"], ids=lambda r: r["id"]
    )
    def test_flosp_channels_enrichable_not_stale_archive(self, row):
        assert classify_ppv_enrichment(row["channel"]) is None

    @pytest.mark.parametrize(
        "row", json.loads(FLOSP_FIXTURE.read_text(encoding="utf-8"))["channels"], ids=lambda r: r["id"]
    )
    def test_flosp_extraction_tags_replay_archive(self, row):
        extraction = PPVEventExtractor().extract_all(row["channel"])
        assert extraction.get("replay_archive") is True
        assert extraction.get("replay_provider") in ("flosp", "flo")
        assert extraction.get("competitors")
        assert extraction.get("date") is not None

    @pytest.mark.parametrize(
        "row", json.loads(FLOSP_FIXTURE.read_text(encoding="utf-8"))["channels"], ids=lambda r: r["id"]
    )
    def test_flosp_date_parsing(self, row):
        extraction = PPVEventExtractor().extract_all(row["channel"])
        expected = datetime.fromisoformat(row["expect_date"])
        assert extraction["date"] == expected

    def test_espn_play_still_stale_archive(self, stale_channels):
        row = next(r for r in stale_channels if r["id"] == "espn_play_2023")
        assert classify_ppv_enrichment(row["name"]) == "stale_archive"
