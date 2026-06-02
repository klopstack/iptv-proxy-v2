"""Tests for ESPN fighter record context."""

from unittest.mock import patch

from services.ppv.context.providers.espn import ESPNProvider, _fetch_espn_fighter_record


class TestFetchEspnFighterRecord:
    def test_parses_record_items_summary(self):
        with patch("services.ppv.context.providers.espn.requests.get") as mock_get:
            mock_get.return_value.json.return_value = {"record": {"items": [{"type": "total", "summary": "27-1-0"}]}}
            mock_get.return_value.raise_for_status = lambda: None
            assert _fetch_espn_fighter_record("mma", "ufc", "12345") == "27-1-0"


class TestEspnFighterRecordProvider:
    @patch(
        "services.ppv.context.providers.espn._fetch_espn_fighter_record",
        return_value="27-1",
    )
    @patch(
        "services.ppv.context.providers.espn._find_espn_athlete_id",
        return_value="2335639",
    )
    def test_get_fighter_record_returns_record(self, _mock_find, _mock_fetch):
        provider = ESPNProvider()
        record = provider.get_fighter_record("Jon Jones", "MMA")
        assert record == "27-1"
