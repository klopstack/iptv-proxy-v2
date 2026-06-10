"""TODO 130 spike fixture contract tests — no live HTTP."""

import json
from pathlib import Path

SPIKE_SAMPLE = Path(__file__).parent / "fixtures" / "spike" / "flo_spike_sample_channels.json"
ICE_HOCKEY_1022 = Path(__file__).parent / "fixtures" / "sofascore" / "ice_hockey_2025-10-22.json"
ICE_HOCKEY_1023 = Path(__file__).parent / "fixtures" / "sofascore" / "ice_hockey_2025-10-23.json"
SPIKE_DOC = Path(__file__).parents[2] / "docs" / "architecture" / "ncaa-college-calendar-source-spike.md"


def test_spike_sample_has_minimum_channels_and_hockey_hits():
    data = json.loads(SPIKE_SAMPLE.read_text())
    channels = data["channels"]
    assert len(channels) >= 20
    hockey = [c for c in channels if c.get("sofascore_slug") == "ice-hockey"]
    hockey_hits = [c for c in hockey if c["result"] in ("match", "partial")]
    assert len(hockey_hits) >= 4
    assert data["summary"]["sofascore_college_basketball_hit_rate"].startswith("0%")


def test_ice_hockey_fixtures_include_ahl_and_ohl_samples():
    for path in (ICE_HOCKEY_1022, ICE_HOCKEY_1023):
        payload = json.loads(path.read_text())
        events = payload["events"]
        assert events
        tournaments = {(e.get("tournament") or {}).get("name") for e in events}
        assert "AHL" in tournaments or "OHL" in tournaments


def test_spike_architecture_doc_exists():
    assert SPIKE_DOC.is_file()
    text = SPIKE_DOC.read_text()
    assert "REPLAY_CALENDAR_DAYS_BACK" in text
    assert "ice-hockey" in text
