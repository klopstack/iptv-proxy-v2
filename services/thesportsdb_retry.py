"""Backoff and retry helpers for TheSportsDB API and HTML fetches."""

from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Iterable, List, Optional, Tuple, TypeVar, cast

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")
S = TypeVar("S")

MAX_RETRIES = 4
INITIAL_BACKOFF_SECONDS = 2.0
BACKOFF_MULTIPLIER = 2.5
MAX_BACKOFF_SECONDS = 90.0

# Substrings common in Cloudflare / rate-limit HTML error pages
HTML_BLOCK_INDICATORS = (
    "cf-browser-verification",
    "just a moment",
    "attention required",
    "rate limit",
    "too many requests",
    "403 forbidden",
    "access denied",
    "challenge-platform",
)


def _sleep(seconds: float) -> None:
    """Thin wrapper around time.sleep so tests can patch backoff without affecting global sleep."""
    time.sleep(seconds)


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter for retry attempt index (0-based)."""
    delay = min(MAX_BACKOFF_SECONDS, INITIAL_BACKOFF_SECONDS * (BACKOFF_MULTIPLIER**attempt))
    return delay * random.uniform(0.9, 1.3)


def is_retryable_thesportsdb_result(result: Any) -> bool:
    """True when the SDK returned HTML or another non-JSON transient failure."""
    return not isinstance(result, dict)


def is_retryable_http_status(status_code: int) -> bool:
    """True for HTTP statuses that are worth retrying."""
    return status_code == 429 or status_code >= 500


def is_retryable_html_page(html: str) -> bool:
    """True when HTML looks like a block/challenge page rather than calendar content."""
    if not html:
        return True

    lower = html.lower()
    if any(indicator in lower for indicator in HTML_BLOCK_INDICATORS):
        return True

    # Calendar pages include browse links; bare error shells usually do not
    if ("<!doctype html" in lower or "<html" in lower) and "browse_calendar" not in lower:
        if "event/" not in lower and "<table" not in lower:
            return True

    return False


def fetch_per_source(
    sources: Iterable[S],
    fetch_one: Callable[[S], List[T]],
    *,
    on_error: Optional[Callable[[S, Exception], None]] = None,
) -> Tuple[List[T], List[S]]:
    """
    Run ``fetch_one`` for each source, collecting successes and recording failures.

    One source failing never discards another source's results. Returns
    ``(items, failed_sources)`` so the caller decides what a partial result
    means (serve stale data, skip caching, log and move on, ...).
    """
    items: List[T] = []
    failed: List[S] = []
    for source in sources:
        try:
            items.extend(fetch_one(source))
        except Exception as exc:
            failed.append(source)
            if on_error is not None:
                on_error(source, exc)
    return items, failed


def call_thesportsdb_api(
    fn: Callable[..., T],
    *args: Any,
    max_retries: int = MAX_RETRIES,
    before_attempt: Optional[Callable[[], None]] = None,
    **kwargs: Any,
) -> T:
    """
    Call a thesportsdb SDK function with exponential backoff on transient failures.

    Retries when the SDK returns non-JSON (HTML rate-limit pages) or raises network errors.
    """
    from services.thesportsdb_api import try_v2_sdk_call
    from services.thesportsdb_service import configure_thesportsdb_api_key

    configure_thesportsdb_api_key()
    last_result: Any = None
    last_error: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        try:
            if before_attempt:
                before_attempt()
            v2_result = try_v2_sdk_call(fn, *args, **kwargs)
            if v2_result is None:
                result: T = fn(*args, **kwargs)
            else:
                result = cast(T, v2_result)
            if is_retryable_thesportsdb_result(result):
                last_result = result
                if attempt >= max_retries:
                    break
                delay = backoff_delay(attempt)
                logger.info(
                    f"TheSportsDB API non-JSON response (attempt {attempt + 1}/{max_retries + 1}), "
                    f"retrying in {delay:.1f}s"
                )
                _sleep(delay)
                continue
            return result
        except Exception as exc:
            last_error = exc
            if attempt >= max_retries:
                raise
            delay = backoff_delay(attempt)
            logger.info(
                f"TheSportsDB API error (attempt {attempt + 1}/{max_retries + 1}): {exc}, " f"retrying in {delay:.1f}s"
            )
            _sleep(delay)

    if last_error is not None:
        raise last_error
    return cast(T, last_result)


def fetch_url_with_retry(
    session: requests.Session,
    url: str,
    *,
    timeout: float,
    max_retries: int = MAX_RETRIES,
    before_attempt: Optional[Callable[[], None]] = None,
    validate_response: Optional[Callable[[requests.Response], bool]] = None,
) -> requests.Response:
    """
    GET a URL with exponential backoff on HTTP 429/5xx or retryable HTML bodies.
    """
    last_response: Optional[requests.Response] = None

    for attempt in range(max_retries + 1):
        if before_attempt:
            before_attempt()

        response = session.get(url, timeout=timeout)
        last_response = response

        should_retry = is_retryable_http_status(response.status_code)
        if validate_response is not None and validate_response(response):
            should_retry = True

        if not should_retry:
            response.raise_for_status()
            return response

        if attempt >= max_retries:
            response.raise_for_status()
            return response

        delay = backoff_delay(attempt)
        logger.info(
            f"HTTP fetch retry for {url} (status={response.status_code}, "
            f"attempt {attempt + 1}/{max_retries + 1}) in {delay:.1f}s"
        )
        _sleep(delay)

    assert last_response is not None
    last_response.raise_for_status()
    return last_response
