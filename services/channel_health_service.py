"""
Channel Health Service - Monitors and tracks channel stream health.

This service is responsible for:
1. Scanning channels to detect non-working streams
2. Detecting black screens and connection failures
3. Tracking failure history and determining permanently down channels
4. Managing connection usage to not interfere with client streams
5. Providing health status data for the UI
"""

import json
import logging
import re
import subprocess
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from models import (
    Account,
    ActiveStream,
    Channel,
    ChannelEpgMapping,
    ChannelHealthCheck,
    ChannelHealthConfig,
    ChannelHealthStatus,
    Credential,
    EpgChannel,
    db,
)
from services.connection_manager import ConnectionManager

logger = logging.getLogger(__name__)


class ChannelHealthService:
    """Service for monitoring channel health and detecting non-working streams."""

    @staticmethod
    def get_available_scan_connections(account_id: int) -> int:
        """
        Get the number of connections available for scanning.

        Always reserves at least `reserved_connections` for client requests.

        Args:
            account_id: The account to check

        Returns:
            Number of connections available for scanning
        """
        account = db.session.get(Account, account_id)
        if not account or not account.enabled:
            return 0

        total_connections = account.get_total_max_connections()
        reserved = ChannelHealthConfig.get_int("reserved_connections", 1)

        # Count active client connections
        credentials = Credential.query.filter_by(account_id=account_id, enabled=True).all()
        active_count = 0
        for cred in credentials:
            active_count += ActiveStream.query.filter_by(credential_id=cred.id).count()

        available = total_connections - active_count - reserved
        return max(0, available)

    @staticmethod
    def check_channel_health(channel: Channel, credential: Any, timeout_seconds: int = 10) -> Dict[str, Any]:
        """
        Check the health of a single channel using ffprobe.

        Args:
            channel: The channel to check
            credential: The credential to use for the check
            timeout_seconds: How long to analyze the stream

        Returns:
            Dict with check results including:
            - result: Result type (success, connection_failed, black_screen, etc.)
            - http_status_code: HTTP status if applicable
            - error_message: Error details
            - analysis_details: Stream analysis data
            - check_duration_ms: How long the check took
        """
        account = db.session.get(Account, channel.account_id)
        if not account:
            return {
                "result": ChannelHealthCheck.RESULT_CONNECTION_FAILED,
                "error_message": "Account not found",
                "check_duration_ms": 0,
            }

        # Build stream URL
        stream_url = (
            f"http://{account.server}/live/{credential.username}/" f"{credential.password}/{channel.stream_id}.ts"
        )

        start_time = time.time()
        result = ChannelHealthService._analyze_stream_with_ffprobe(
            stream_url, timeout_seconds, account.user_agent or "okhttp/3.14.9"
        )
        result["check_duration_ms"] = int((time.time() - start_time) * 1000)

        return result

    @staticmethod
    def _analyze_stream_with_ffprobe(stream_url: str, duration_seconds: int, user_agent: str) -> Dict[str, Any]:
        """
        Analyze a stream using ffprobe to detect video/audio and black screens.

        Args:
            stream_url: URL of the stream to analyze
            duration_seconds: How long to analyze
            user_agent: User agent to use for the request

        Returns:
            Dict with analysis results
        """
        # First, try to get stream info using ffprobe
        try:
            # Check if stream is accessible and get basic info
            probe_cmd = [
                "ffprobe",
                "-v",
                "error",
                "-user_agent",
                user_agent,
                "-timeout",
                str(duration_seconds * 1000000),  # microseconds
                "-show_streams",
                "-show_format",
                "-print_format",
                "json",
                "-i",
                stream_url,
            ]

            probe_result = subprocess.run(
                probe_cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 10,
            )

            if probe_result.returncode != 0:
                error_msg = probe_result.stderr.strip()

                # Parse common errors
                if "Connection refused" in error_msg or "Connection reset" in error_msg:
                    return {
                        "result": ChannelHealthCheck.RESULT_CONNECTION_FAILED,
                        "error_message": error_msg[:500],
                    }
                elif "timed out" in error_msg.lower() or "timeout" in error_msg.lower():
                    return {
                        "result": ChannelHealthCheck.RESULT_TIMEOUT,
                        "error_message": error_msg[:500],
                    }
                elif "404" in error_msg or "403" in error_msg:
                    # Extract HTTP status code
                    http_code = None
                    match = re.search(r"HTTP error (\d+)", error_msg)
                    if match:
                        http_code = int(match.group(1))
                    return {
                        "result": ChannelHealthCheck.RESULT_HTTP_ERROR,
                        "http_status_code": http_code,
                        "error_message": error_msg[:500],
                    }
                else:
                    return {
                        "result": ChannelHealthCheck.RESULT_INVALID_STREAM,
                        "error_message": error_msg[:500],
                    }

            # Parse probe output
            try:
                probe_data = json.loads(probe_result.stdout)
            except json.JSONDecodeError:
                return {
                    "result": ChannelHealthCheck.RESULT_INVALID_STREAM,
                    "error_message": "Could not parse ffprobe output",
                }

            streams = probe_data.get("streams", [])
            video_streams = [s for s in streams if s.get("codec_type") == "video"]
            audio_streams = [s for s in streams if s.get("codec_type") == "audio"]

            if not video_streams and not audio_streams:
                return {
                    "result": ChannelHealthCheck.RESULT_INVALID_STREAM,
                    "error_message": "No video or audio streams found",
                    "analysis_details": json.dumps({"streams_found": len(streams)}),
                }

            if not video_streams:
                return {
                    "result": ChannelHealthCheck.RESULT_AUDIO_ONLY,
                    "error_message": "Stream has audio but no video",
                    "analysis_details": json.dumps(
                        {
                            "audio_streams": len(audio_streams),
                            "video_streams": 0,
                        }
                    ),
                }

            # Now check for black screen using ffmpeg with blackdetect filter
            black_ratio = ChannelHealthService._detect_black_screen(stream_url, duration_seconds, user_agent)

            threshold = ChannelHealthConfig.get_float("black_screen_threshold", 0.95)

            analysis_details = {
                "video_streams": len(video_streams),
                "audio_streams": len(audio_streams),
                "video_codec": video_streams[0].get("codec_name") if video_streams else None,
                "resolution": f"{video_streams[0].get('width')}x{video_streams[0].get('height')}"
                if video_streams
                else None,
                "black_frame_ratio": black_ratio,
            }

            if black_ratio is not None and black_ratio >= threshold:
                return {
                    "result": ChannelHealthCheck.RESULT_BLACK_SCREEN,
                    "error_message": f"Black screen detected ({black_ratio:.1%} black frames)",
                    "analysis_details": json.dumps(analysis_details),
                }

            # Stream is working
            return {
                "result": ChannelHealthCheck.RESULT_SUCCESS,
                "analysis_details": json.dumps(analysis_details),
            }

        except subprocess.TimeoutExpired:
            return {
                "result": ChannelHealthCheck.RESULT_TIMEOUT,
                "error_message": f"Analysis timed out after {duration_seconds} seconds",
            }
        except FileNotFoundError:
            logger.error("ffprobe not found - install ffmpeg to enable health checks")
            return {
                "result": ChannelHealthCheck.RESULT_SKIPPED,
                "error_message": "ffprobe not installed",
            }
        except Exception as e:
            logger.error(f"Error analyzing stream: {e}")
            return {
                "result": ChannelHealthCheck.RESULT_INVALID_STREAM,
                "error_message": str(e)[:500],
            }

    @staticmethod
    def _detect_black_screen(stream_url: str, duration_seconds: int, user_agent: str) -> Optional[float]:
        """
        Detect black screen using ffmpeg's blackdetect filter.

        Returns the ratio of black frames (0.0 to 1.0), or None if detection failed.
        """
        try:
            # Use blackdetect filter to find black frames
            cmd = [
                "ffmpeg",
                "-user_agent",
                user_agent,
                "-t",
                str(duration_seconds),
                "-i",
                stream_url,
                "-vf",
                "blackdetect=d=0.1:pix_th=0.10",
                "-an",  # No audio
                "-f",
                "null",
                "-",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=duration_seconds + 15,
            )

            # Parse blackdetect output from stderr
            # Format: [blackdetect @ 0x...] black_start:0 black_end:10 black_duration:10
            stderr = result.stderr
            black_duration_total = 0.0

            for match in re.finditer(r"black_duration:([\d.]+)", stderr):
                black_duration_total += float(match.group(1))

            # Calculate ratio of black time to total time
            if duration_seconds > 0:
                return min(1.0, black_duration_total / duration_seconds)
            return None

        except Exception as e:
            logger.warning(f"Black screen detection failed: {e}")
            return None

    @staticmethod
    def record_health_check(
        channel_id: int, result: Dict[str, Any], credential_id: Optional[int] = None
    ) -> ChannelHealthCheck:
        """
        Record a health check result and update the channel's health status.

        Args:
            channel_id: ID of the channel checked
            result: Result dict from check_channel_health
            credential_id: ID of the credential used (optional)

        Returns:
            The created ChannelHealthCheck record
        """
        # Create health check record
        check = ChannelHealthCheck(
            channel_id=channel_id,
            result=result.get("result", ChannelHealthCheck.RESULT_SKIPPED),
            http_status_code=result.get("http_status_code"),
            error_message=result.get("error_message"),
            analysis_details=result.get("analysis_details"),
            check_duration_ms=result.get("check_duration_ms", 0),
            credential_id=credential_id,
            checked_at=datetime.now(timezone.utc),
        )
        db.session.add(check)

        # Update health status
        ChannelHealthService._update_health_status(channel_id, check)

        db.session.commit()
        return check

    @staticmethod
    def _update_health_status(channel_id: int, check: ChannelHealthCheck) -> None:
        """Update the aggregated health status for a channel based on a new check."""
        # Get or create health status
        status = ChannelHealthStatus.query.filter_by(channel_id=channel_id).first()
        if not status:
            status = ChannelHealthStatus(
                channel_id=channel_id,
                status=ChannelHealthStatus.STATUS_UNKNOWN,
                total_checks=0,
                successful_checks=0,
                failed_checks=0,
                consecutive_failures=0,
                distinct_failure_periods=0,
            )
            db.session.add(status)

        now = datetime.now(timezone.utc)

        # Initialize any None values to 0 for safety
        if status.total_checks is None:
            status.total_checks = 0
        if status.successful_checks is None:
            status.successful_checks = 0
        if status.failed_checks is None:
            status.failed_checks = 0
        if status.consecutive_failures is None:
            status.consecutive_failures = 0
        if status.distinct_failure_periods is None:
            status.distinct_failure_periods = 0

        # Update basic stats
        status.total_checks += 1
        status.last_check_at = now
        status.last_result = check.result

        is_failure = check.result in ChannelHealthCheck.FAILURE_RESULTS

        if is_failure:
            status.failed_checks += 1
            status.consecutive_failures += 1
            status.last_failure_at = now

            # Check if this is a distinct failure period
            min_hours = ChannelHealthConfig.get_int("min_hours_apart", 6)
            if status.last_success_at:
                # Count distinct failure periods since last success
                status.distinct_failure_periods = ChannelHealthService._count_distinct_failures(
                    channel_id, status.last_success_at, min_hours
                )
            else:
                # No success ever - count all distinct periods
                status.distinct_failure_periods = ChannelHealthService._count_distinct_failures(
                    channel_id, None, min_hours
                )

            # Check if channel should be marked as down
            threshold = ChannelHealthConfig.get_int("failure_threshold", 3)
            if status.distinct_failure_periods >= threshold:
                if status.status != ChannelHealthStatus.STATUS_DOWN:
                    status.status = ChannelHealthStatus.STATUS_DOWN
                    logger.info(
                        f"Channel {channel_id} marked as DOWN after {status.distinct_failure_periods} "
                        f"distinct failure periods"
                    )

                    # Auto-disable if configured
                    if ChannelHealthConfig.get_bool("auto_disable_down_channels", True):
                        ChannelHealthService._auto_disable_channel(channel_id)
                        status.auto_disabled_at = now
            elif status.consecutive_failures > 0:
                status.status = ChannelHealthStatus.STATUS_DEGRADED
        else:
            # Success
            status.successful_checks += 1
            status.consecutive_failures = 0
            status.last_success_at = now

            # Reset status if previously down/degraded
            if status.status in (ChannelHealthStatus.STATUS_DOWN, ChannelHealthStatus.STATUS_DEGRADED):
                status.status = ChannelHealthStatus.STATUS_HEALTHY
                status.distinct_failure_periods = 0
                logger.info(f"Channel {channel_id} health restored to HEALTHY")
            elif status.status == ChannelHealthStatus.STATUS_UNKNOWN:
                status.status = ChannelHealthStatus.STATUS_HEALTHY

        status.updated_at = now

    @staticmethod
    def _count_distinct_failures(channel_id: int, since: Optional[datetime], min_hours_apart: int) -> int:
        """
        Count the number of distinct failure periods for a channel.

        Failures must be at least min_hours_apart to count as distinct periods.
        """
        query = ChannelHealthCheck.query.filter(
            ChannelHealthCheck.channel_id == channel_id,
            ChannelHealthCheck.result.in_(ChannelHealthCheck.FAILURE_RESULTS),
        )

        if since:
            query = query.filter(ChannelHealthCheck.checked_at > since)

        checks = query.order_by(ChannelHealthCheck.checked_at.asc()).all()

        if not checks:
            return 0

        distinct_periods = 1
        last_period_time = checks[0].checked_at

        for check in checks[1:]:
            check_time = check.checked_at
            # Handle timezone-naive datetimes
            if check_time.tzinfo is None:
                check_time = check_time.replace(tzinfo=timezone.utc)
            if last_period_time.tzinfo is None:
                last_period_time = last_period_time.replace(tzinfo=timezone.utc)

            hours_diff = (check_time - last_period_time).total_seconds() / 3600
            if hours_diff >= min_hours_apart:
                distinct_periods += 1
                last_period_time = check_time

        return distinct_periods

    @staticmethod
    def _auto_disable_channel(channel_id: int) -> None:
        """Auto-disable a channel by setting is_visible to False."""
        channel = db.session.get(Channel, channel_id)
        if channel and channel.is_visible:
            channel.is_visible = False
            logger.info(f"Channel {channel_id} ({channel.name}) auto-disabled due to health failures")

    @staticmethod
    def get_channels_to_scan(account_id: int, limit: int = 100) -> List[Channel]:
        """
        Get channels that need health scanning, prioritizing:
        1. Channels never scanned
        2. Channels not scanned recently
        3. Channels with degraded status (for confirmation)

        Excludes channels that are:
        - Already marked as permanently down
        - Marked as ignored
        - Inactive

        Args:
            account_id: Account to get channels for
            limit: Maximum number of channels to return

        Returns:
            List of Channel objects to scan
        """
        # Get scan interval
        scan_interval = ChannelHealthConfig.get_int("scan_interval_minutes", 30)
        scan_cutoff = datetime.now(timezone.utc) - timedelta(minutes=scan_interval)

        # Get channels that need scanning
        # Subquery to get channels with their health status
        channels_query = (
            Channel.query.outerjoin(ChannelHealthStatus)
            .filter(
                Channel.account_id == account_id,
                Channel.is_active == True,  # noqa: E712
            )
            .filter(
                # Include channels that:
                # - Have no health status (never checked)
                # - Are not down or ignored
                db.or_(
                    ChannelHealthStatus.id.is_(None),
                    ~ChannelHealthStatus.status.in_(
                        [
                            ChannelHealthStatus.STATUS_DOWN,
                            ChannelHealthStatus.STATUS_IGNORED,
                        ]
                    ),
                )
            )
            .filter(
                # And haven't been checked recently
                db.or_(
                    ChannelHealthStatus.last_check_at.is_(None),
                    ChannelHealthStatus.last_check_at < scan_cutoff,
                )
            )
            .order_by(
                # Prioritize: never checked, then degraded, then oldest check
                db.case(
                    (ChannelHealthStatus.id.is_(None), 0),
                    (ChannelHealthStatus.status == ChannelHealthStatus.STATUS_DEGRADED, 1),
                    else_=2,
                ),
                ChannelHealthStatus.last_check_at.asc().nullsfirst(),
            )
            .limit(limit)
        )

        return channels_query.all()

    @staticmethod
    def scan_channels(account_id: int, max_channels: int = 10) -> Dict[str, Any]:
        """
        Scan channels for an account using available connections.

        This is the main entry point for scanning. It:
        1. Checks how many connections are available for scanning
        2. Gets channels that need scanning
        3. Performs health checks on each channel
        4. Records results

        Args:
            account_id: Account to scan
            max_channels: Maximum channels to scan in this batch

        Returns:
            Dict with scan results
        """
        if not ChannelHealthConfig.get_bool("scanning_enabled", False):
            return {"success": False, "message": "Scanning is disabled", "scanned": 0}

        # Get available connections
        available_connections = ChannelHealthService.get_available_scan_connections(account_id)
        if available_connections <= 0:
            return {
                "success": False,
                "message": "No connections available for scanning",
                "scanned": 0,
            }

        # Get channels to scan
        channels = ChannelHealthService.get_channels_to_scan(
            account_id, limit=min(max_channels, available_connections * 5)
        )

        if not channels:
            return {"success": True, "message": "No channels need scanning", "scanned": 0}

        # Get analysis duration
        analysis_duration = ChannelHealthConfig.get_int("analysis_duration_seconds", 10)

        results: Dict[str, Any] = {
            "success": True,
            "scanned": 0,
            "healthy": 0,
            "failed": 0,
            "errors": [],
        }

        for channel in channels:
            # Re-check connection availability before each scan
            # (client may have connected)
            if ChannelHealthService.get_available_scan_connections(account_id) <= 0:
                results["message"] = "Scanning paused - connections needed for clients"
                break

            try:
                # Get a credential for scanning
                credential = ConnectionManager.get_available_credential(account_id)
                if not credential:
                    results["message"] = "No credentials available"
                    break

                credential_id: Optional[int] = getattr(credential, "id", None)

                # Acquire connection
                if credential_id is None:
                    results["errors"].append("Credential has no ID")
                    continue

                session_token, error = ConnectionManager.acquire_connection(
                    credential_id, f"health_check_{channel.stream_id}", "health_scanner"
                )

                if not session_token:
                    results["errors"].append(f"Could not acquire connection: {error}")
                    continue

                try:
                    # Perform health check
                    check_result = ChannelHealthService.check_channel_health(channel, credential, analysis_duration)

                    # Record result
                    ChannelHealthService.record_health_check(channel.id, check_result, credential_id)

                    results["scanned"] += 1
                    if check_result.get("result") == ChannelHealthCheck.RESULT_SUCCESS:
                        results["healthy"] += 1
                    else:
                        results["failed"] += 1

                finally:
                    # Always release connection
                    ConnectionManager.release_connection(session_token)

            except Exception as e:
                logger.error(f"Error scanning channel {channel.id}: {e}")
                results["errors"].append(f"Channel {channel.id}: {str(e)}")

        return results

    @staticmethod
    def get_health_report(
        account_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        include_epg: bool = True,
    ) -> Dict[str, Any]:
        """
        Get a comprehensive health report for channels.

        Args:
            account_id: Filter by account (None for all accounts)
            status_filter: Filter by status (down, degraded, healthy, unknown, ignored)
            include_epg: Whether to include EPG mapping information

        Returns:
            Dict with report data including summary and channel details
        """
        query = Channel.query.join(Account).outerjoin(ChannelHealthStatus).filter(Account.enabled == True)  # noqa: E712

        if account_id:
            query = query.filter(Channel.account_id == account_id)

        if status_filter:
            if status_filter == "unknown":
                query = query.filter(ChannelHealthStatus.id.is_(None))
            else:
                query = query.filter(ChannelHealthStatus.status == status_filter)

        channels_data = []
        status_counts = {
            ChannelHealthStatus.STATUS_UNKNOWN: 0,
            ChannelHealthStatus.STATUS_HEALTHY: 0,
            ChannelHealthStatus.STATUS_DEGRADED: 0,
            ChannelHealthStatus.STATUS_DOWN: 0,
            ChannelHealthStatus.STATUS_IGNORED: 0,
        }

        for channel in query.all():
            status = channel.health_status
            current_status = status.status if status else ChannelHealthStatus.STATUS_UNKNOWN
            status_counts[current_status] += 1

            # Get EPG info if requested
            epg_info = None
            if include_epg:
                epg_mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
                if epg_mapping:
                    epg_channel = db.session.get(EpgChannel, epg_mapping.epg_channel_id)
                    if epg_channel:
                        epg_info = {
                            "epg_channel_id": epg_channel.channel_id,
                            "display_name": epg_channel.display_name,
                            "program_count": epg_channel.program_count,
                            "source_id": epg_channel.source_id,
                        }

            channel_info = {
                "id": channel.id,
                "account_id": channel.account_id,
                "account_name": channel.account.name if hasattr(channel, "account") else None,
                "stream_id": channel.stream_id,
                "name": channel.name,
                "cleaned_name": channel.cleaned_name,
                "is_visible": channel.is_visible,
                "status": current_status,
                "epg_info": epg_info,
            }

            if status:
                channel_info.update(
                    {
                        "total_checks": status.total_checks,
                        "successful_checks": status.successful_checks,
                        "failed_checks": status.failed_checks,
                        "consecutive_failures": status.consecutive_failures,
                        "distinct_failure_periods": status.distinct_failure_periods,
                        "last_check_at": status.last_check_at.isoformat() if status.last_check_at else None,
                        "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
                        "last_failure_at": status.last_failure_at.isoformat() if status.last_failure_at else None,
                        "last_result": status.last_result,
                        "auto_disabled_at": status.auto_disabled_at.isoformat() if status.auto_disabled_at else None,
                        "ignored_at": status.ignored_at.isoformat() if status.ignored_at else None,
                        "ignored_reason": status.ignored_reason,
                    }
                )

            channels_data.append(channel_info)

        return {
            "summary": {
                "total": sum(status_counts.values()),
                "by_status": status_counts,
            },
            "channels": channels_data,
            "config": ChannelHealthConfig.get_all(),
        }

    @staticmethod
    def get_health_summary(
        account_id: Optional[int] = None,
        category_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Get a summary of channel health counts without channel details.

        This is much faster than get_health_report for large datasets.

        Args:
            account_id: Filter by account (None for all accounts)
            category_id: Filter by category (None for all categories)

        Returns:
            Dict with summary counts and config
        """
        from sqlalchemy import func

        # Build base query for counting
        base_query = (
            db.session.query(Channel)
            .join(Account)
            .outerjoin(ChannelHealthStatus)
            .filter(Account.enabled == True)  # noqa: E712
        )

        if account_id:
            base_query = base_query.filter(Channel.account_id == account_id)

        if category_id:
            base_query = base_query.filter(Channel.category_id == category_id)

        # Count by status using a single query with conditional aggregation
        status_counts = (
            db.session.query(
                func.sum(
                    db.case(
                        (ChannelHealthStatus.id.is_(None), 1),
                        else_=0,
                    )
                ).label("unknown"),
                func.sum(
                    db.case(
                        (ChannelHealthStatus.status == ChannelHealthStatus.STATUS_HEALTHY, 1),
                        else_=0,
                    )
                ).label("healthy"),
                func.sum(
                    db.case(
                        (ChannelHealthStatus.status == ChannelHealthStatus.STATUS_DEGRADED, 1),
                        else_=0,
                    )
                ).label("degraded"),
                func.sum(
                    db.case(
                        (ChannelHealthStatus.status == ChannelHealthStatus.STATUS_DOWN, 1),
                        else_=0,
                    )
                ).label("down"),
                func.sum(
                    db.case(
                        (ChannelHealthStatus.status == ChannelHealthStatus.STATUS_IGNORED, 1),
                        else_=0,
                    )
                ).label("ignored"),
                func.count(Channel.id).label("total"),
            )
            .select_from(Channel)
            .join(Account)
            .outerjoin(ChannelHealthStatus)
            .filter(Account.enabled == True)  # noqa: E712
        )

        if account_id:
            status_counts = status_counts.filter(Channel.account_id == account_id)

        if category_id:
            status_counts = status_counts.filter(Channel.category_id == category_id)

        result = status_counts.first()

        # Handle case where result is None (no channels match filters)
        if result is None:
            return {
                "summary": {
                    "total": 0,
                    "by_status": {
                        ChannelHealthStatus.STATUS_UNKNOWN: 0,
                        ChannelHealthStatus.STATUS_HEALTHY: 0,
                        ChannelHealthStatus.STATUS_DEGRADED: 0,
                        ChannelHealthStatus.STATUS_DOWN: 0,
                        ChannelHealthStatus.STATUS_IGNORED: 0,
                    },
                },
                "config": ChannelHealthConfig.get_all(),
            }

        return {
            "summary": {
                "total": result.total or 0,
                "by_status": {
                    ChannelHealthStatus.STATUS_UNKNOWN: result.unknown or 0,
                    ChannelHealthStatus.STATUS_HEALTHY: result.healthy or 0,
                    ChannelHealthStatus.STATUS_DEGRADED: result.degraded or 0,
                    ChannelHealthStatus.STATUS_DOWN: result.down or 0,
                    ChannelHealthStatus.STATUS_IGNORED: result.ignored or 0,
                },
            },
            "config": ChannelHealthConfig.get_all(),
        }

    @staticmethod
    def get_channels_paginated(
        account_id: Optional[int] = None,
        category_id: Optional[int] = None,
        status_filter: Optional[str] = None,
        visibility_filter: Optional[str] = None,
        epg_filter: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 100,
        include_epg: bool = True,
    ) -> Dict[str, Any]:
        """
        Get paginated channel health data with filtering.

        Args:
            account_id: Filter by account (None for all accounts)
            category_id: Filter by category (None for all categories)
            status_filter: Filter by status (down, degraded, healthy, unknown, ignored)
            visibility_filter: Filter by visibility (visible, hidden)
            epg_filter: Filter by EPG presence (with, without)
            search: Search by channel name
            page: Page number (1-indexed)
            per_page: Items per page
            include_epg: Whether to include EPG mapping information

        Returns:
            Dict with paginated channels and metadata
        """
        # Build base query
        query = Channel.query.join(Account).outerjoin(ChannelHealthStatus).filter(Account.enabled == True)  # noqa: E712

        # Apply filters
        if account_id:
            query = query.filter(Channel.account_id == account_id)

        if category_id:
            query = query.filter(Channel.category_id == category_id)

        if status_filter:
            if status_filter == "unknown":
                query = query.filter(ChannelHealthStatus.id.is_(None))
            else:
                query = query.filter(ChannelHealthStatus.status == status_filter)

        if visibility_filter:
            if visibility_filter == "visible":
                query = query.filter(Channel.is_visible == True)  # noqa: E712
            elif visibility_filter == "hidden":
                query = query.filter(Channel.is_visible == False)  # noqa: E712

        if search:
            search_term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Channel.name.ilike(search_term),
                    Channel.cleaned_name.ilike(search_term),
                )
            )

        # EPG filter requires a subquery
        if epg_filter:
            from sqlalchemy import exists

            epg_exists = exists().where(ChannelEpgMapping.channel_id == Channel.id)
            if epg_filter == "with":
                query = query.filter(epg_exists)
            elif epg_filter == "without":
                query = query.filter(~epg_exists)

        # Get total count before pagination
        total = query.count()

        # Apply ordering and pagination
        query = query.order_by(Channel.name).offset((page - 1) * per_page).limit(per_page)

        # Build channel data
        channels_data = []
        for channel in query.all():
            status = channel.health_status
            current_status = status.status if status else ChannelHealthStatus.STATUS_UNKNOWN

            # Get category info
            category_info = None
            if channel.category:
                category_info = {
                    "id": channel.category.id,
                    "name": channel.category.category_name,
                }

            # Get EPG info if requested
            epg_info = None
            if include_epg:
                epg_mapping = ChannelEpgMapping.query.filter_by(channel_id=channel.id).first()
                if epg_mapping:
                    epg_channel = db.session.get(EpgChannel, epg_mapping.epg_channel_id)
                    if epg_channel:
                        epg_info = {
                            "epg_channel_id": epg_channel.channel_id,
                            "display_name": epg_channel.display_name,
                            "program_count": epg_channel.program_count,
                            "source_id": epg_channel.source_id,
                        }

            channel_info = {
                "id": channel.id,
                "account_id": channel.account_id,
                "account_name": channel.account.name if hasattr(channel, "account") else None,
                "stream_id": channel.stream_id,
                "name": channel.name,
                "cleaned_name": channel.cleaned_name,
                "is_visible": channel.is_visible,
                "status": current_status,
                "category": category_info,
                "epg_info": epg_info,
            }

            if status:
                channel_info.update(
                    {
                        "total_checks": status.total_checks,
                        "successful_checks": status.successful_checks,
                        "failed_checks": status.failed_checks,
                        "consecutive_failures": status.consecutive_failures,
                        "distinct_failure_periods": status.distinct_failure_periods,
                        "last_check_at": status.last_check_at.isoformat() if status.last_check_at else None,
                        "last_success_at": status.last_success_at.isoformat() if status.last_success_at else None,
                        "last_failure_at": status.last_failure_at.isoformat() if status.last_failure_at else None,
                        "last_result": status.last_result,
                        "auto_disabled_at": status.auto_disabled_at.isoformat() if status.auto_disabled_at else None,
                        "ignored_at": status.ignored_at.isoformat() if status.ignored_at else None,
                        "ignored_reason": status.ignored_reason,
                    }
                )

            channels_data.append(channel_info)

        return {
            "channels": channels_data,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": (total + per_page - 1) // per_page,
                "has_next": page * per_page < total,
                "has_prev": page > 1,
            },
        }

    @staticmethod
    def test_channel(channel_id: int) -> Dict[str, Any]:
        """
        Manually test a specific channel and record the result.

        Args:
            channel_id: ID of the channel to test

        Returns:
            Dict with test result
        """
        channel = db.session.get(Channel, channel_id)
        if not channel:
            return {"success": False, "error": "Channel not found"}

        credential = ConnectionManager.get_available_credential(channel.account_id)
        if not credential:
            return {"success": False, "error": "No credentials available"}

        credential_id: Optional[int] = getattr(credential, "id", None)
        if credential_id is None:
            return {"success": False, "error": "Credential has no ID"}

        analysis_duration = ChannelHealthConfig.get_int("analysis_duration_seconds", 10)

        # Acquire connection
        session_token, error = ConnectionManager.acquire_connection(
            credential_id, f"manual_test_{channel.stream_id}", "manual_test"
        )

        if not session_token:
            return {"success": False, "error": f"Could not acquire connection: {error}"}

        try:
            check_result = ChannelHealthService.check_channel_health(channel, credential, analysis_duration)

            ChannelHealthService.record_health_check(channel.id, check_result, credential_id)

            return {
                "success": True,
                "channel_id": channel_id,
                "result": check_result.get("result"),
                "error_message": check_result.get("error_message"),
                "analysis_details": check_result.get("analysis_details"),
                "check_duration_ms": check_result.get("check_duration_ms"),
            }
        finally:
            ConnectionManager.release_connection(session_token)

    @staticmethod
    def reenable_channel(channel_id: int) -> Dict[str, Any]:
        """
        Re-enable a channel that was marked as down or disabled.

        This resets the health status to allow fresh testing.

        Args:
            channel_id: ID of the channel to re-enable

        Returns:
            Dict with result
        """
        channel = db.session.get(Channel, channel_id)
        if not channel:
            return {"success": False, "error": "Channel not found"}

        # Re-enable channel visibility
        channel.is_visible = True

        # Reset health status
        status = ChannelHealthStatus.query.filter_by(channel_id=channel_id).first()
        if status:
            status.status = ChannelHealthStatus.STATUS_UNKNOWN
            status.consecutive_failures = 0
            status.distinct_failure_periods = 0
            status.auto_disabled_at = None
            status.manually_reenabled_at = datetime.now(timezone.utc)
            status.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        logger.info(f"Channel {channel_id} ({channel.name}) re-enabled for testing")
        return {"success": True, "channel_id": channel_id, "message": "Channel re-enabled"}

    @staticmethod
    def ignore_channel(channel_id: int, reason: Optional[str] = None) -> Dict[str, Any]:
        """
        Mark a channel as ignored (won't be scanned again).

        Args:
            channel_id: ID of the channel to ignore
            reason: Optional reason for ignoring

        Returns:
            Dict with result
        """
        channel = db.session.get(Channel, channel_id)
        if not channel:
            return {"success": False, "error": "Channel not found"}

        # Get or create health status
        status = ChannelHealthStatus.query.filter_by(channel_id=channel_id).first()
        if not status:
            status = ChannelHealthStatus(channel_id=channel_id)
            db.session.add(status)

        status.status = ChannelHealthStatus.STATUS_IGNORED
        status.ignored_at = datetime.now(timezone.utc)
        status.ignored_reason = reason
        status.updated_at = datetime.now(timezone.utc)

        db.session.commit()

        logger.info(f"Channel {channel_id} ({channel.name}) marked as ignored: {reason}")
        return {"success": True, "channel_id": channel_id, "message": "Channel marked as ignored"}

    @staticmethod
    def get_channel_history(channel_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get the health check history for a channel.

        Args:
            channel_id: ID of the channel
            limit: Maximum number of records to return

        Returns:
            List of health check records
        """
        checks = (
            ChannelHealthCheck.query.filter_by(channel_id=channel_id)
            .order_by(ChannelHealthCheck.checked_at.desc())
            .limit(limit)
            .all()
        )

        return [
            {
                "id": check.id,
                "result": check.result,
                "http_status_code": check.http_status_code,
                "error_message": check.error_message,
                "analysis_details": json.loads(check.analysis_details) if check.analysis_details else None,
                "check_duration_ms": check.check_duration_ms,
                "checked_at": check.checked_at.isoformat() if check.checked_at else None,
                "credential_id": check.credential_id,
            }
            for check in checks
        ]

    @staticmethod
    def update_config(key: str, value: str) -> Dict[str, Any]:
        """
        Update a health monitoring configuration value.

        Args:
            key: Configuration key
            value: New value

        Returns:
            Dict with result
        """
        if key not in ChannelHealthConfig.DEFAULTS and not ChannelHealthConfig.query.filter_by(key=key).first():
            return {"success": False, "error": f"Unknown configuration key: {key}"}

        ChannelHealthConfig.set(key, value)
        logger.info(f"Health config updated: {key}={value}")
        return {"success": True, "key": key, "value": value}

    @staticmethod
    def get_scan_status(account_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Get the current scanning status.

        Args:
            account_id: Optional account to get status for

        Returns:
            Dict with scan status information
        """
        status = {
            "scanning_enabled": ChannelHealthConfig.get_bool("scanning_enabled", False),
            "config": ChannelHealthConfig.get_all(),
        }

        if account_id:
            status["account_id"] = account_id
            status["available_connections"] = ChannelHealthService.get_available_scan_connections(account_id)
            status["channels_to_scan"] = len(ChannelHealthService.get_channels_to_scan(account_id, limit=1000))
        else:
            # Get status for all enabled accounts
            accounts_status = []
            for account in Account.query.filter_by(enabled=True).all():
                accounts_status.append(
                    {
                        "account_id": account.id,
                        "account_name": account.name,
                        "available_connections": ChannelHealthService.get_available_scan_connections(account.id),
                        "channels_to_scan": len(ChannelHealthService.get_channels_to_scan(account.id, limit=1000)),
                    }
                )
            status["accounts"] = accounts_status

        return status
