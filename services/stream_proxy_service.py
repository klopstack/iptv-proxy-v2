"""
Stream Proxy Service - Decomposed logic from routes/streams.py

This service contains the business logic for stream proxying, separated from
Flask route handlers to make it independently testable.
"""

import logging
import time
from typing import Any, Dict, Optional, Tuple

import requests

from models import Account
from services.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class StreamProxyService:
    """Handles stream proxy logic without Flask dependencies."""

    @staticmethod
    def handle_credential_shortage(account_id: int, stream_service) -> Optional[Any]:
        """
        Attempt to acquire a credential by releasing idle streams.

        When no credentials are available, this tries to free up a slot
        by releasing streams that have no active subscribers.

        Args:
            account_id: The account ID
            stream_service: The stream service instance

        Returns:
            Available credential, or None if none could be acquired
        """
        idle_count = stream_service.get_idle_stream_count(account_id)
        if idle_count > 0:
            logger.info(
                f"No credentials available for account {account_id}, "
                f"attempting to release {idle_count} idle stream(s)"
            )
            released = stream_service.release_idle_streams_for_account(account_id)
            if released > 0:
                # Give a moment for the connection to be released
                time.sleep(0.1)
                # Try again to get a credential
                credential = ConnectionManager.get_available_credential(account_id)
                if credential:
                    return credential

        return None

    @staticmethod
    def build_stream_response_headers(
        session_token: str,
        subscriber_id: str,
        is_shared: bool,
        *,
        source_index: int = 0,
        source_role: str = "primary",
    ) -> Dict[str, str]:
        """
        Build response headers for stream proxy.

        Args:
            session_token: The session token for this connection
            subscriber_id: The subscriber ID
            is_shared: Whether this is a shared stream
            source_index: Active fallback source index (0 = primary)
            source_role: "primary" or "backup"

        Returns:
            Dict of HTTP headers
        """
        return {
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
            "X-Session-Token": session_token,
            "X-Stream-Shared": "true" if is_shared else "false",
            "X-Subscriber-Id": subscriber_id[:8],
            "X-Stream-Source": source_role,
            "X-Stream-Source-Index": str(source_index),
        }


class StreamConnectivityTester:
    """Handles stream connectivity testing logic."""

    @staticmethod
    def build_test_result(
        account_id: int, stream_id: str, success: bool = False, error: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Build a stream test result dictionary.

        Args:
            account_id: The account ID
            stream_id: The stream ID
            success: Whether the test passed
            error: Error message if test failed

        Returns:
            Result dictionary
        """
        return {
            "account_id": account_id,
            "stream_id": stream_id,
            "success": success,
            "checks": {},
            "error": error,
        }

    @staticmethod
    def check_account_prerequisites(account: Optional[Account]) -> Tuple[bool, Optional[str], int]:
        """
        Check account prerequisites for streaming.

        Args:
            account: The Account instance

        Returns:
            Tuple of (is_valid, error_message, http_status)
        """
        if not account:
            return False, "Account not found", 404

        if not account.enabled:
            return False, "Account is disabled", 403

        return True, None, 200

    @staticmethod
    def check_credential_prerequisites(credential: Optional[Any]) -> Tuple[bool, Optional[str], int]:
        """
        Check credential prerequisites for streaming.

        Args:
            credential: The credential instance or None

        Returns:
            Tuple of (is_valid, error_message, http_status)
        """
        if not credential:
            return False, "No available credentials", 503

        return True, None, 200

    @staticmethod
    def test_upstream_head(
        upstream_url: str, user_agent: str, timeout: Tuple[int, int] = (10, 10)
    ) -> Tuple[Optional[int], Optional[Dict[str, str]], Optional[str]]:
        """
        Test upstream server with HEAD request.

        Args:
            upstream_url: The upstream URL to test
            user_agent: User agent header
            timeout: Request timeout (connect, read)

        Returns:
            Tuple of (status_code, headers, error_message)
        """
        try:
            response = requests.head(
                upstream_url,
                headers={"User-Agent": user_agent},
                timeout=timeout,
                allow_redirects=True,
            )
            return response.status_code, dict(response.headers), None
        except requests.exceptions.Timeout:
            return None, None, "Connection timed out"
        except requests.exceptions.ConnectionError:
            return None, None, "Connection failed"
        except Exception as e:
            return None, None, str(e)

    @staticmethod
    def test_upstream_get(
        upstream_url: str, user_agent: str, timeout: Tuple[int, int] = (10, 10), chunk_size: int = 1024
    ) -> Tuple[Optional[int], Optional[Dict[str, str]], int, Optional[str]]:
        """
        Test upstream server with GET request.

        Args:
            upstream_url: The upstream URL to test
            user_agent: User agent header
            timeout: Request timeout (connect, read)
            chunk_size: Chunk size to read from stream

        Returns:
            Tuple of (status_code, headers, data_size, error_message)
        """
        try:
            response = requests.get(
                upstream_url,
                headers={"User-Agent": user_agent},
                timeout=timeout,
                stream=True,
            )
            headers = dict(response.headers)

            # Read just a small chunk to verify streaming works
            chunk = next(response.iter_content(chunk_size=chunk_size), None)
            data_size = len(chunk) if chunk else 0
            response.close()

            return response.status_code, headers, data_size, None
        except requests.exceptions.Timeout:
            return None, None, 0, "Connection timed out"
        except requests.exceptions.ConnectionError:
            return None, None, 0, "Connection failed"
        except Exception as e:
            return None, None, 0, str(e)

    @staticmethod
    def determine_test_success_and_error(
        head_status: Optional[int], head_error: Optional[str], get_status: Optional[int], get_error: Optional[str]
    ) -> Tuple[bool, Optional[str]]:
        """
        Determine test success based on HTTP responses.

        HEAD request succeeded → Success
        HEAD returned 405 (not allowed) and GET succeeded → Success
        Otherwise → Error

        Args:
            head_status: HTTP status from HEAD request
            head_error: Error from HEAD request
            get_status: HTTP status from GET request (if HEAD failed)
            get_error: Error from GET request (if HEAD failed)

        Returns:
            Tuple of (success, error_message)
        """
        # If HEAD succeeded
        if head_status == 200:
            return True, None

        # If HEAD not allowed, check GET
        if head_status == 405 and get_status == 200:
            return True, None

        # Determine error message
        if head_error:
            return False, f"HEAD request failed: {head_error}"
        if get_error:
            return False, f"GET request failed: {get_error}"

        # HTTP error from HEAD
        if head_status:
            return False, f"Upstream returned HTTP {head_status}"

        # HTTP error from GET
        if get_status:
            return False, f"Upstream returned HTTP {get_status}"

        return False, "Unknown error"
