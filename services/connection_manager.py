"""
Connection Manager Service - handles stream multiplexing across multiple credentials

This service is responsible for:
1. Tracking active stream connections per credential
2. Selecting the best available credential for new streams
3. Managing connection lifecycle (acquire/release)
4. Cleaning up stale connections
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Tuple

from models import Account, ActiveStream, Credential, db
from services.datetime_utils import serialize_utc_iso

logger = logging.getLogger(__name__)

# Timeout for considering a stream "stale" (no activity).
# Active streams now emit a heartbeat (ConnectionManager.update_activity) while
# data flows, so this only reaps genuinely abandoned rows. Configurable via env;
# default is generous (5 min) to avoid reaping live sessions during brief stalls.
STREAM_TIMEOUT_SECONDS = int(os.environ.get("STREAM_TIMEOUT_SECONDS", "300"))


class ConnectionManager:
    """Manages stream connections across multiple credentials for an account."""

    @staticmethod
    def get_available_credential(account_id: int) -> Optional[Any]:
        """
        Get an available credential for a new stream connection.

        Args:
            account_id: The account to get a credential for

        Returns:
            Credential with available connection slots, or None if all are busy.
        """
        # First, clean up stale connections
        ConnectionManager.cleanup_stale_connections(account_id)

        # Get account with credentials
        account = db.session.get(Account, account_id)
        if not account or not account.enabled:
            logger.warning(f"Account {account_id} not found or disabled")
            return None

        # Get credentials with available slots
        credentials = Credential.query.filter_by(account_id=account_id, enabled=True).all()

        if not credentials:
            return None

        # Count actual active streams per credential
        for cred in credentials:
            active_count = ActiveStream.query.filter_by(credential_id=cred.id).count()
            cred.active_connections = active_count  # Update for selection logic

        # Sort by load (prefer credentials with fewer active connections)
        available = [c for c in credentials if c.is_available()]
        if not available:
            logger.warning(f"No available credentials for account {account_id}")
            return None

        # Return credential with lowest utilization
        available.sort(key=lambda c: c.active_connections)
        selected = available[0]
        logger.debug(
            f"Selected credential {selected.id} for account {account_id} "
            f"({selected.active_connections}/{selected.max_connections} connections)"
        )
        return selected

    @staticmethod
    def acquire_connection(
        credential_id: int, stream_id: str, client_ip: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """
        Acquire a connection slot for a stream.

        Args:
            credential_id: The credential to use
            stream_id: The stream being requested
            client_ip: Optional client IP address

        Returns:
            Tuple of (session_token, error_message). Token is None on failure.
        """
        # Verify credential is still available
        credential = db.session.get(Credential, credential_id)
        if not credential:
            return (None, "Credential not found")

        if not credential.enabled:
            return (None, "Credential is disabled")

        # Count current connections
        active_count = ActiveStream.query.filter_by(credential_id=credential_id).count()
        if active_count >= (credential.max_connections or 1):
            return (None, "No available connection slots")

        # Create active stream record
        session_token = secrets.token_hex(32)
        active_stream = ActiveStream(
            credential_id=credential_id,
            stream_id=stream_id,
            client_ip=client_ip,
            session_token=session_token,
            started_at=datetime.now(timezone.utc).replace(tzinfo=None),
            last_activity=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        db.session.add(active_stream)

        # Update credential's active connection count
        credential.active_connections = active_count + 1
        db.session.commit()

        logger.info(
            f"Acquired connection for credential {credential_id}, stream {stream_id} "
            f"(session: {session_token[:8]}...)"
        )
        return (session_token, "")

    @staticmethod
    def release_connection(session_token: str) -> bool:
        """
        Release a connection slot when a stream ends.

        Args:
            session_token: The session token from acquire_connection

        Returns:
            True if released successfully, False otherwise
        """
        if not session_token:
            return False

        active_stream = ActiveStream.query.filter_by(session_token=session_token).first()
        if not active_stream:
            logger.warning(f"No active stream found for session {session_token[:8]}...")
            return False

        credential_id = active_stream.credential_id
        db.session.delete(active_stream)

        # Update credential's active connection count
        credential = db.session.get(Credential, credential_id)
        if credential:
            active_count = ActiveStream.query.filter_by(credential_id=credential_id).count()
            credential.active_connections = active_count

        db.session.commit()
        logger.info(f"Released connection for session {session_token[:8]}...")
        return True

    @staticmethod
    def reassign_connection(session_token: str, stream_id: str, client_ip: Optional[str] = None) -> bool:
        """
        Retarget an existing connection slot to a new stream without releasing it.

        Used when the same client switches channels during an idle-pending window.
        """
        if not session_token:
            return False

        active_stream = ActiveStream.query.filter_by(session_token=session_token).first()
        if not active_stream:
            logger.warning(f"No active stream found to reassign for session {session_token[:8]}...")
            return False

        active_stream.stream_id = stream_id
        if client_ip is not None:
            active_stream.client_ip = client_ip
        active_stream.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)
        db.session.commit()

        logger.info(
            f"Reassigned connection session {session_token[:8]}... to stream {stream_id} " f"(client: {client_ip})"
        )
        return True

    @staticmethod
    def update_activity(session_token: str) -> bool:
        """
        Update last activity timestamp for a stream (heartbeat).

        Args:
            session_token: The session token from acquire_connection

        Returns:
            True if updated successfully
        """
        if not session_token:
            return False

        active_stream = ActiveStream.query.filter_by(session_token=session_token).first()
        if active_stream:
            active_stream.last_activity = datetime.now(timezone.utc).replace(tzinfo=None)
            db.session.commit()
            return True
        return False

    @staticmethod
    def cleanup_stale_connections(
        account_id: Optional[int] = None, timeout_seconds: int = STREAM_TIMEOUT_SECONDS
    ) -> None:
        """
        Clean up stale connections that haven't had activity recently.

        Args:
            account_id: Optional account to clean up (None = all accounts)
            timeout_seconds: Seconds since last activity to consider stale
        """
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=timeout_seconds)

        query = db.session.query(ActiveStream).filter(ActiveStream.last_activity < cutoff)

        if account_id:
            # Filter to specific account's credentials
            credential_ids = [c.id for c in Credential.query.filter_by(account_id=account_id).all()]
            if credential_ids:
                query = query.filter(ActiveStream.credential_id.in_(credential_ids))

        stale_streams = query.all()
        if stale_streams:
            logger.info(f"Cleaning up {len(stale_streams)} stale connections")
            for stream in stale_streams:
                credential: Optional[Credential] = stream.credential  # type: ignore[assignment]
                db.session.delete(stream)
                if credential:
                    active_count = ActiveStream.query.filter_by(credential_id=credential.id).count()
                    credential.active_connections = max(0, active_count - 1)

            db.session.commit()

    @staticmethod
    def clear_orphaned_streams_on_startup() -> int:
        """Remove all ActiveStream rows after a container restart.

        In-memory upstream connections do not survive a process restart, so any
        persisted rows are ghosts that block credential slots until
        STREAM_TIMEOUT_SECONDS elapses.  Intended to run from entrypoint.sh on
        startup; split deployments should set SKIP_ORPHAN_STREAM_CLEANUP=true
        on the API-only container so live sessions in the stream container are
        not cleared when the API container restarts alone.
        """
        count = db.session.query(ActiveStream).delete(synchronize_session=False)
        if count == 0:
            return 0

        for credential in Credential.query.all():
            credential.active_connections = 0

        db.session.commit()
        logger.info("Cleared %s orphaned ActiveStream row(s) from prior container run", count)
        return count

    @staticmethod
    def get_connection_status(account_id: int) -> dict:
        """
        Get connection status for an account.

        Args:
            account_id: The account to check

        Returns:
            Dictionary with connection statistics
        """
        account = db.session.get(Account, account_id)
        if not account:
            return {"error": "Account not found"}

        credentials = Credential.query.filter_by(account_id=account_id).all()

        if not credentials:
            return {
                "total_max_connections": 0,
                "total_active_connections": 0,
                "available_connections": 0,
                "credentials": [],
            }

        # Calculate totals
        total_max = sum(c.max_connections or 1 for c in credentials)
        total_active = sum(ActiveStream.query.filter_by(credential_id=c.id).count() for c in credentials)

        credential_details = []
        for cred in credentials:
            active_count = ActiveStream.query.filter_by(credential_id=cred.id).count()
            credential_details.append(
                {
                    "id": cred.id,
                    "username": cred.username,
                    "max_connections": cred.max_connections or 1,
                    "active_connections": active_count,
                    "enabled": cred.enabled,
                    "status": cred.status,
                    "exp_date": cred.exp_date,
                }
            )

        return {
            "total_max_connections": total_max,
            "total_active_connections": total_active,
            "available_connections": total_max - total_active,
            "credentials": credential_details,
        }

    @staticmethod
    def get_active_streams(account_id: Optional[int] = None) -> list:
        """
        Get list of active streams.

        Args:
            account_id: Optional account to filter by

        Returns:
            List of active stream dictionaries
        """
        query = db.session.query(ActiveStream).join(Credential)

        if account_id:
            query = query.filter(Credential.account_id == account_id)

        streams = query.all()
        return [
            {
                "session_token": s.session_token,
                "stream_id": s.stream_id,
                "credential_id": s.credential_id,
                "client_ip": s.client_ip,
                "started_at": serialize_utc_iso(s.started_at),
                "last_activity": serialize_utc_iso(s.last_activity),
            }
            for s in streams
        ]
