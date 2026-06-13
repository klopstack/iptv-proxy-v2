"""Tests for TheSportsDB V2 API routing."""

from unittest.mock import MagicMock, patch

from services.thesportsdb_api import normalize_v2_to_v1, resolve_thesportsdb_api_key, try_v2_sdk_call, uses_v2_api


class TestUsesV2Api:
    def test_free_keys_use_v1(self):
        assert uses_v2_api("") is False
        assert uses_v2_api("3") is False
        assert uses_v2_api("123") is False

    def test_premium_key_uses_v2(self):
        assert uses_v2_api("385561") is True


class TestNormalizeV2ToV1:
    def test_lookup_to_teams(self):
        data = {"lookup": [{"idTeam": "1", "strTeam": "Arsenal"}]}
        assert normalize_v2_to_v1(data, "teams") == {"teams": [{"idTeam": "1", "strTeam": "Arsenal"}]}

    def test_list_to_teams(self):
        data = {"list": [{"idTeam": "2"}]}
        assert normalize_v2_to_v1(data, "teams") == {"teams": [{"idTeam": "2"}]}

    def test_schedule_to_events(self):
        data = {"schedule": [{"idEvent": "99"}]}
        assert normalize_v2_to_v1(data, "events") == {"events": [{"idEvent": "99"}]}

    def test_filter_to_events(self):
        data = {"filter": [{"idEvent": "100"}]}
        assert normalize_v2_to_v1(data, "events") == {"events": [{"idEvent": "100"}]}

    def test_message_only_returns_empty_list(self):
        assert normalize_v2_to_v1({"Message": "No team found"}, "teams") == {"teams": []}


class TestTryV2SdkCall:
    @patch("services.thesportsdb_api.v2_get")
    @patch("services.thesportsdb_api.resolve_thesportsdb_api_key", return_value="385561")
    def test_routes_league_teams(self, _mock_key, mock_v2_get):
        mock_v2_get.return_value = {"list": [{"idTeam": "1", "strTeam": "Chelsea"}]}
        fn = MagicMock()
        fn.__module__ = "thesportsdb.teams"
        fn.__name__ = "leagueTeams"

        result = try_v2_sdk_call(fn, "4328")

        assert result == {"teams": [{"idTeam": "1", "strTeam": "Chelsea"}]}
        mock_v2_get.assert_called_once_with("list/teams/4328", "385561")
        fn.assert_not_called()

    @patch("services.thesportsdb_api.resolve_thesportsdb_api_key", return_value="")
    def test_free_tier_falls_back_to_v1(self, _mock_key):
        fn = MagicMock()
        fn.__module__ = "thesportsdb.teams"
        fn.__name__ = "leagueTeams"

        assert try_v2_sdk_call(fn, "4328") is None

    @patch("services.thesportsdb_api.v2_get")
    @patch("services.thesportsdb_api.resolve_thesportsdb_api_key", return_value="385561")
    def test_routes_events_day_with_sport(self, _mock_key, mock_v2_get):
        mock_v2_get.return_value = {"filter": [{"idEvent": "1"}]}
        fn = MagicMock()
        fn.__module__ = "thesportsdb.events"
        fn.__name__ = "eventsDay"

        result = try_v2_sdk_call(fn, "2026-06-02", s="Baseball")

        assert result == {"events": [{"idEvent": "1"}]}
        mock_v2_get.assert_called_once_with(
            "filter/events/day/2026-06-02?s=Baseball",
            "385561",
        )


class TestResolveApiKey:
    @patch.dict("os.environ", {"THESPORTSDB_API_KEY": "from-env"}, clear=False)
    def test_env_takes_precedence(self):
        assert resolve_thesportsdb_api_key() == "from-env"


class TestCallThesportsdbApiV2Integration:
    @patch("services.thesportsdb_retry._sleep")
    @patch("services.thesportsdb_api.try_v2_sdk_call")
    @patch("services.thesportsdb_service.configure_thesportsdb_api_key")
    def test_retry_uses_v2_without_calling_sdk(self, _mock_configure, mock_v2, _mock_sleep):
        from services.thesportsdb_retry import call_thesportsdb_api

        mock_v2.return_value = {"teams": [{"idTeam": "1"}]}
        fn = MagicMock()
        fn.__module__ = "thesportsdb.teams"
        fn.__name__ = "leagueTeams"

        result = call_thesportsdb_api(fn, "4328")

        assert result == {"teams": [{"idTeam": "1"}]}
        fn.assert_not_called()
