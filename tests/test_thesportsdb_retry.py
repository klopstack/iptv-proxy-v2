"""Tests for TheSportsDB retry/backoff helpers."""

from unittest.mock import MagicMock, patch

import requests

from services.thesportsdb_retry import (
    backoff_delay,
    call_thesportsdb_api,
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


class TestCallThesportsdbApi:
    @patch("services.thesportsdb_retry.time.sleep")
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

    @patch("services.thesportsdb_retry.time.sleep")
    @patch("services.thesportsdb_service.configure_thesportsdb_api_key")
    def test_returns_last_html_after_retries_exhausted(self, mock_configure, mock_sleep):
        fn = MagicMock(return_value="<html>blocked</html>")

        result = call_thesportsdb_api(fn, max_retries=2)

        assert result == "<html>blocked</html>"
        assert fn.call_count == 3
        assert mock_sleep.call_count == 2

    @patch("services.thesportsdb_retry.time.sleep")
    @patch("services.thesportsdb_service.configure_thesportsdb_api_key")
    def test_retries_on_exception(self, mock_configure, mock_sleep):
        fn = MagicMock(side_effect=[requests.Timeout("timed out"), {"events": []}])

        result = call_thesportsdb_api(fn)

        assert result == {"events": []}
        assert fn.call_count == 2


class TestFetchUrlWithRetry:
    @patch("services.thesportsdb_retry.time.sleep")
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
