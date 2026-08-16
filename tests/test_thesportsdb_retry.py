"""Tests for TheSportsDB retry/backoff helpers."""

from unittest.mock import MagicMock, patch

import requests

from services.thesportsdb_retry import (
    BACKOFF_MULTIPLIER,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
    backoff_delay,
    call_thesportsdb_api,
    fetch_per_source,
    fetch_url_with_retry,
    is_retryable_html_page,
    is_retryable_http_status,
    is_retryable_thesportsdb_result,
)


class TestRetryableDetection:
    def test_non_dict_api_result_is_retryable(self):
        assert is_retryable_thesportsdb_result("<html></html>") is True
        assert is_retryable_thesportsdb_result({"events": []}) is False

    def test_http_status_retryable(self):
        assert is_retryable_http_status(429) is True
        assert is_retryable_http_status(503) is True
        assert is_retryable_http_status(404) is False

    def test_html_block_page(self):
        assert is_retryable_html_page("<html>Just a moment...</html>") is True
        assert is_retryable_html_page("<html><table><a href='/event/1'>Game</a></table></html>") is False


class TestFetchPerSource:
    def test_all_sources_succeed(self):
        items, failed = fetch_per_source(["a", "b"], lambda source: [f"{source}1", f"{source}2"])
        assert items == ["a1", "a2", "b1", "b2"]
        assert failed == []

    def test_one_source_failing_keeps_the_others(self):
        def fetch_one(source):
            if source == "b":
                raise requests.ConnectionError("boom")
            return [source]

        items, failed = fetch_per_source(["a", "b", "c"], fetch_one)
        assert items == ["a", "c"]
        assert failed == ["b"]

    def test_on_error_receives_source_and_exception(self):
        seen = []

        def fetch_one(source):
            raise ValueError(f"bad {source}")

        items, failed = fetch_per_source(
            ["x", "y"], fetch_one, on_error=lambda source, exc: seen.append((source, str(exc)))
        )
        assert items == []
        assert failed == ["x", "y"]
        assert seen == [("x", "bad x"), ("y", "bad y")]

    def test_empty_sources(self):
        items, failed = fetch_per_source([], lambda source: [source])
        assert items == []
        assert failed == []


class TestCallThesportsdbApi:
    @patch("services.thesportsdb_retry._sleep")
    @patch("services.thesportsdb_service.configure_thesportsdb_api_key")
    def test_retries_on_html_then_succeeds(self, mock_configure, mock_sleep):
        fn = MagicMock(
            side_effect=[
                "<!doctype html><html>Just a moment</html>",
                {"events": [{"idEvent": "1"}]},
            ]
        )

        result = call_thesportsdb_api(fn, "2026-05-31", s="Baseball")

        assert result == {"events": [{"idEvent": "1"}]}
        assert fn.call_count == 2
        mock_sleep.assert_called_once()

    @patch("services.thesportsdb_retry._sleep")
    @patch("services.thesportsdb_service.configure_thesportsdb_api_key")
    def test_returns_last_html_after_retries_exhausted(self, mock_configure, mock_sleep):
        fn = MagicMock(return_value="<html>blocked</html>")

        result = call_thesportsdb_api(fn, max_retries=2)

        assert result == "<html>blocked</html>"
        assert fn.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("services.thesportsdb_retry._sleep")
    @patch("services.thesportsdb_service.configure_thesportsdb_api_key")
    def test_retries_on_exception(self, mock_configure, mock_sleep):
        fn = MagicMock(side_effect=[requests.Timeout("timed out"), {"events": []}])

        result = call_thesportsdb_api(fn)

        assert result == {"events": []}
        assert fn.call_count == 2


class TestFetchUrlWithRetry:
    @patch("services.thesportsdb_retry._sleep")
    def test_retries_on_429(self, mock_sleep):
        session = MagicMock()
        bad = MagicMock(status_code=429, text="rate limited")
        good = MagicMock(status_code=200, text="<html><table><a href='/event/1'>Game</a></table></html>")
        good.raise_for_status = MagicMock()
        session.get.side_effect = [bad, good]

        response = fetch_url_with_retry(session, "https://example.com/calendar", timeout=10)

        assert response is good
        assert session.get.call_count == 2
        mock_sleep.assert_called_once()


class TestBackoffDelay:
    def test_backoff_grows_with_attempt(self):
        assert backoff_delay(0) <= backoff_delay(1) * 2

    @patch("services.thesportsdb_retry.random.uniform", return_value=1.0)
    def test_backoff_uses_configured_base_and_multiplier(self, _mock_jitter):
        assert backoff_delay(0) == INITIAL_BACKOFF_SECONDS
        assert backoff_delay(1) == INITIAL_BACKOFF_SECONDS * BACKOFF_MULTIPLIER
        assert backoff_delay(2) == INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER**2)

    @patch("services.thesportsdb_retry.random.uniform", return_value=1.0)
    def test_backoff_is_capped(self, _mock_jitter):
        assert backoff_delay(20) == MAX_BACKOFF_SECONDS
