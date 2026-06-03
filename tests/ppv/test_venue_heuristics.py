"""Tests for neutral-site heuristics validation."""

import json

from services.ppv.venue_inference import (
    clear_heuristics_cache,
    detect_venue_inference_mode,
    validate_neutral_site_heuristics,
)


def test_validate_neutral_site_heuristics_ok():
    ok, message = validate_neutral_site_heuristics()
    assert ok is True
    assert message == "ok"


def test_validate_neutral_site_heuristics_bad_json(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    ok, message = validate_neutral_site_heuristics(bad)
    assert ok is False
    assert "invalid" in message.lower()


def test_invalid_heuristics_logs_and_uses_empty_config(tmp_path, caplog):
    bad = tmp_path / "bad.json"
    bad.write_text('["not", "an", "object"]', encoding="utf-8")

    import logging

    import services.ppv.venue_inference as vi

    original = vi._CONFIG_PATH
    vi._CONFIG_PATH = bad
    clear_heuristics_cache()
    try:
        with caplog.at_level(logging.ERROR):
            mode = detect_venue_inference_mode("UFC 312: Jones vs Miocic")
        assert "invalid" in caplog.text.lower() or mode.mode == "team_home"
    finally:
        vi._CONFIG_PATH = original
        clear_heuristics_cache()


def test_clear_heuristics_cache_allows_reload(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(
        json.dumps(
            {
                "tier1_keywords": ["world cup"],
                "tier1_regex": [],
                "bowl_game_names": [],
                "national_teams": [],
                "tier2_keywords": [],
                "metadata_only_leagues": [],
            }
        ),
        encoding="utf-8",
    )

    import services.ppv.venue_inference as vi

    original = vi._CONFIG_PATH
    vi._CONFIG_PATH = good
    clear_heuristics_cache()
    try:
        mode = detect_venue_inference_mode("World Cup: Brazil vs Germany")
        assert mode.mode == "metadata_only"
    finally:
        vi._CONFIG_PATH = original
        clear_heuristics_cache()
