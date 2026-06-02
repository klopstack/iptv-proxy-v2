"""Tests for PPV enrichability classification."""

from services.ppv.enrichability import classify_ppv_enrichment, is_ppv_section_header


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
