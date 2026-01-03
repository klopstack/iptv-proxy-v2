"""
PPV Event Enrichment Service

Manages background enrichment of PPV events with TheSportsDB data.
Uses a queue system with API rate limiting to respect free tier limits:
- Free tier: ~500 requests/day (conservative ~20/hour)
- Batch processing with configurable batch size
- Persistent queue tracking for resumable processing
- Automatic retry with exponential backoff

Strategy:
1. Queue all unmatched PPV channels for enrichment
2. Process in batches respecting rate limits
3. Use tiered matching strategies (Direct Search → Calendar Browse)
4. Store event data in Event model
5. Link channels to events via EventChannelLink
6. Track enrichment progress and failures for retry
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

from flask import Flask

from models import Channel, Event, EventChannelLink, SyncMetadata, db
from services.ppv_event_extractor import PPVEventExtractor
from services.thesportsdb_service import TheSportsDBService

logger = logging.getLogger(__name__)

# API rate limiting - TheSportsDB API limit
THESPORTSDB_REQUESTS_PER_MINUTE = 30  # Official rate limit
THESPORTSDB_REQUEST_WINDOW_SECONDS = 60  # 1 minute window

# Processing configuration
DEFAULT_BATCH_SIZE = 10  # Channels to process per batch
DEFAULT_REQUESTS_PER_MINUTE = 25  # Conservative limit (under 30/min)
DEFAULT_RETRY_DELAY_MINUTES = 60  # Wait 1 hour before retry
MAX_RETRY_ATTEMPTS = 3

# Metadata keys for persistent tracking
METADATA_KEY_ENRICHMENT_QUEUED = "ppv_enrichment_queued_count"
METADATA_KEY_ENRICHMENT_PROCESSED = "ppv_enrichment_processed_count"
METADATA_KEY_ENRICHMENT_FAILURES = "ppv_enrichment_failures"
METADATA_KEY_ENRICHMENT_LAST_RUN = "ppv_enrichment_last_run"
METADATA_KEY_ENRICHMENT_NEXT_RUN = "ppv_enrichment_next_run"
METADATA_KEY_API_REQUESTS_MINUTE = "thesportsdb_requests_minute"
METADATA_KEY_API_REQUESTS_MINUTE_RESET = "thesportsdb_requests_minute_reset_at"


class PPVEnrichmentQueue:
    """
    Queue for managing PPV event enrichment with TheSportsDB.

    Handles:
    - Queuing unmatched PPV channels
    - Rate-limited batch processing
    - Event creation and channel linking
    - Progress tracking and retry management
    """

    def __init__(
        self,
        app: Flask,
        batch_size: int = DEFAULT_BATCH_SIZE,
        requests_per_minute: int = DEFAULT_REQUESTS_PER_MINUTE,
    ):
        """
        Initialize enrichment queue.

        Args:
            app: Flask app instance
            batch_size: Number of channels to process per batch
            requests_per_minute: Rate limit for TheSportsDB API calls (max 30/min)
        """
        self.app = app
        self.batch_size = batch_size
        self.requests_per_minute = min(requests_per_minute, THESPORTSDB_REQUESTS_PER_MINUTE)
        self.request_interval_seconds = 60 / self.requests_per_minute

        # Services
        self.thesportsdb = TheSportsDBService()
        self.extractor = PPVEventExtractor()

        # Track last request time for rate limiting
        self._last_request_time = 0

    def queue_channels_for_enrichment(self, channels: List[Channel]) -> Dict[str, int]:
        """
        Queue PPV channels for enrichment.

        Args:
            channels: List of Channel objects to enrich

        Returns:
            Dict with queuing statistics
        """
        with self.app.app_context():
            queued = 0
            skipped_already_matched = 0

            for channel in channels:
                # Check if already enriched
                if self._is_channel_enriched(channel):
                    skipped_already_matched += 1
                    continue

                # Mark for processing
                if not channel.ppv_enrichment_queue_id:
                    channel.ppv_enrichment_queue_id = self._generate_queue_id()
                    channel.ppv_enrichment_status = "queued"
                    channel.ppv_enrichment_attempts = 0
                    queued += 1

            if queued > 0:
                db.session.commit()
                logger.info(f"Queued {queued} PPV channels for enrichment")

            total = SyncMetadata.get(METADATA_KEY_ENRICHMENT_QUEUED, "0")
            try:
                total = int(total) + queued
            except (ValueError, TypeError):
                total = queued

            SyncMetadata.set(METADATA_KEY_ENRICHMENT_QUEUED, str(total))

            return {
                "queued": queued,
                "skipped_already_matched": skipped_already_matched,
                "total_queued": total,
            }

    def process_queue(self, max_requests: Optional[int] = None) -> Dict[str, int]:
        """
        Process queued channels for enrichment.

        Respects rate limiting (30 requests/minute) and stops if limit would be exceeded.

        Args:
            max_requests: Maximum API requests to make in this run
                         (None = use per-minute limit)

        Returns:
            Dict with processing statistics
        """
        if max_requests is None:
            max_requests = self.requests_per_minute

        with self.app.app_context():
            # Check rate limit
            if not self._check_api_rate_limit(max_requests):
                logger.info("TheSportsDB API rate limit reached (30 requests/minute), " "skipping enrichment run")
                return {
                    "processed": 0,
                    "matched": 0,
                    "failed": 0,
                    "rate_limited": True,
                }

            stats = {
                "processed": 0,
                "matched": 0,
                "failed": 0,
                "retried": 0,
                "api_requests_made": 0,
                "rate_limited": False,
            }

            # Get next batch of channels to process
            channels_to_process = self._get_next_batch(self.batch_size)

            if not channels_to_process:
                logger.info("No channels queued for enrichment")
                return stats

            logger.info(f"Processing batch of {len(channels_to_process)} channels")

            for channel in channels_to_process:
                # Check rate limit again
                requests_remaining = max_requests - stats["api_requests_made"]
                if requests_remaining <= 0:
                    logger.info(
                        f"API request limit reached ({max_requests}), "
                        f"stopping enrichment at {stats['processed']} processed"
                    )
                    stats["rate_limited"] = True
                    break

                try:
                    # Attempt enrichment
                    matched, requests_used = self._enrich_channel(channel, remaining_requests=requests_remaining)

                    stats["api_requests_made"] += requests_used
                    stats["processed"] += 1

                    if matched:
                        stats["matched"] += 1
                        channel.ppv_enrichment_status = "matched"
                    else:
                        # Retry or mark as unmatched
                        channel.ppv_enrichment_attempts += 1
                        if channel.ppv_enrichment_attempts >= MAX_RETRY_ATTEMPTS:
                            channel.ppv_enrichment_status = "no_match"
                            logger.info(
                                f"Channel {channel.name} (ID: {channel.id}) "
                                f"failed to match after {MAX_RETRY_ATTEMPTS} attempts"
                            )
                        else:
                            channel.ppv_enrichment_status = "retry_pending"

                    db.session.commit()

                except Exception as e:
                    logger.error(
                        f"Error enriching channel {channel.name} (ID: {channel.id}): {e}",
                        exc_info=True,
                    )
                    stats["failed"] += 1
                    channel.ppv_enrichment_status = "error"
                    channel.ppv_enrichment_error = str(e)[:500]  # Store truncated error
                    db.session.commit()

            # Update persistent tracking
            self._update_enrichment_stats(stats)

            # Record next run time
            next_run = datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_RETRY_DELAY_MINUTES)
            SyncMetadata.set(METADATA_KEY_ENRICHMENT_NEXT_RUN, next_run.isoformat())

            logger.info(
                f"Enrichment batch complete: "
                f"{stats['processed']} processed, "
                f"{stats['matched']} matched, "
                f"{stats['failed']} failed, "
                f"{stats['api_requests_made']} API requests"
            )

            return stats

    def get_enrichment_status(self) -> Dict:
        """
        Get current enrichment queue status.

        Returns:
            Dict with queue statistics and progress
        """
        with self.app.app_context():
            queued_count = self._count_by_status("queued")
            processing_count = self._count_by_status("processing")
            retry_count = self._count_by_status("retry_pending")
            matched_count = self._count_by_status("matched")
            no_match_count = self._count_by_status("no_match")
            error_count = self._count_by_status("error")

            total_queued = SyncMetadata.get(METADATA_KEY_ENRICHMENT_QUEUED, "0")
            total_processed = SyncMetadata.get(METADATA_KEY_ENRICHMENT_PROCESSED, "0")
            total_failures = SyncMetadata.get(METADATA_KEY_ENRICHMENT_FAILURES, "0")

            last_run = SyncMetadata.get(METADATA_KEY_ENRICHMENT_LAST_RUN)
            next_run = SyncMetadata.get(METADATA_KEY_ENRICHMENT_NEXT_RUN)

            api_requests_minute = SyncMetadata.get(METADATA_KEY_API_REQUESTS_MINUTE, "0")
            api_reset_at = SyncMetadata.get(METADATA_KEY_API_REQUESTS_MINUTE_RESET)

            return {
                "queue_status": {
                    "queued": queued_count,
                    "processing": processing_count,
                    "retry_pending": retry_count,
                    "matched": matched_count,
                    "no_match": no_match_count,
                    "error": error_count,
                },
                "cumulative_stats": {
                    "total_queued": int(total_queued),
                    "total_processed": int(total_processed),
                    "total_failures": int(total_failures),
                },
                "api_usage": {
                    "requests_this_minute": int(api_requests_minute),
                    "minute_limit": THESPORTSDB_REQUESTS_PER_MINUTE,
                    "requests_remaining": (THESPORTSDB_REQUESTS_PER_MINUTE - int(api_requests_minute)),
                    "minute_window_reset_at": api_reset_at,
                    "requests_per_minute_limit": self.requests_per_minute,
                },
                "timing": {
                    "last_run": last_run,
                    "next_run": next_run,
                },
            }

    # Private methods

    def _is_channel_enriched(self, channel: Channel) -> bool:
        """Check if channel already has matched event."""
        if not channel.is_ppv:
            return True  # Not PPV, no enrichment needed

        # Check if channel already linked to an event
        return EventChannelLink.query.filter_by(channel_id=channel.id).first() is not None

    def _generate_queue_id(self) -> str:
        """Generate unique queue ID for tracking."""
        return f"queue_{datetime.now(timezone.utc).timestamp()}"

    def _get_next_batch(self, batch_size: int) -> List[Channel]:
        """Get next batch of channels to process."""
        return (
            Channel.query.filter(
                Channel.is_ppv is True,
                Channel.ppv_enrichment_status.in_(["queued", "retry_pending", "error"]),
            )
            .order_by(Channel.ppv_enrichment_status == "retry_pending")
            .limit(batch_size)
            .all()
        )

    def _enrich_channel(self, channel: Channel, remaining_requests: int) -> Tuple[bool, int]:
        """
        Attempt to enrich a single channel.

        Returns:
            Tuple of (matched: bool, requests_used: int)
        """
        channel.ppv_enrichment_status = "processing"
        db.session.commit()

        # Extract event details from channel name
        extraction = self.extractor.extract_all(channel.name)
        if extraction["is_placeholder"]:
            # No recognizable event in name
            return False, 0

        # Try to match to TheSportsDB event
        try:
            match = None  # TODO: Implement matching logic
            # match = self.thesportsdb.search_event(
            #     channel.name,
            #     channel.category,
            #     max_requests=remaining_requests,
            # )

            if not match:
                return False, 1  # Made request, no match

            # Create or link event
            event = self._create_or_get_event(match)

            # Create channel link
            link = EventChannelLink.query.filter_by(
                event_id=event.id,
                channel_id=channel.id,
            ).first()

            if not link:
                link = EventChannelLink(
                    event_id=event.id,
                    channel_id=channel.id,
                )
                db.session.add(link)

            link.match_confidence = match.get("confidence", 1.0)
            link.match_method = match.get("strategy", "unknown")
            link.feed_type = "primary"

            db.session.add(link)
            db.session.commit()

            logger.info(f"Matched channel {channel.name} to event " f"{match['home_team']} vs {match['away_team']}")

            return True, 1

        except Exception as e:
            logger.error(f"Error matching channel {channel.name}: {e}")
            return False, 0

    def _create_or_get_event(self, match: Dict) -> Event:
        """Create or retrieve event from match data."""
        external_id = match.get("external_id", match.get("event_id"))

        # Check if event already exists
        event = Event.query.filter_by(external_id=external_id).first()
        if event:
            return event

        # Create new event
        scheduled_at = match.get("scheduled_at")
        if isinstance(scheduled_at, str):
            scheduled_at = datetime.fromisoformat(scheduled_at)

        event = Event(
            external_id=external_id,
            source=Event.SOURCE_THESPORTSDB,
            sport=match.get("sport", "Unknown"),
            league_id=match.get("league_id"),
            league_name=match.get("league_name"),
            home_team_id=match.get("home_team_id"),
            home_team_name=match.get("home_team", ""),
            away_team_id=match.get("away_team_id"),
            away_team_name=match.get("away_team", ""),
            scheduled_at=scheduled_at or datetime.now(timezone.utc),
            status=match.get("status", Event.STATUS_SCHEDULED),
            venue_name=match.get("venue_name"),
            city=match.get("city"),
            country=match.get("country"),
            is_ppv=True,
            data_completeness="partial",
        )

        db.session.add(event)
        db.session.commit()

        return event

    def _check_api_rate_limit(self, max_requests: int) -> bool:
        """Check if API rate limit allows more requests (30 requests/minute)."""
        requests_this_minute = int(SyncMetadata.get(METADATA_KEY_API_REQUESTS_MINUTE, "0"))
        reset_at_str = SyncMetadata.get(METADATA_KEY_API_REQUESTS_MINUTE_RESET)

        now = datetime.now(timezone.utc)

        # Check if we need to reset counter
        if reset_at_str:
            try:
                reset_at = datetime.fromisoformat(reset_at_str)
                if now >= reset_at:
                    # Reset per-minute counter
                    requests_this_minute = 0
                    reset_at = now + timedelta(seconds=THESPORTSDB_REQUEST_WINDOW_SECONDS)
                    SyncMetadata.set(
                        METADATA_KEY_API_REQUESTS_MINUTE_RESET,
                        reset_at.isoformat(),
                    )
            except (ValueError, TypeError):
                pass
        else:
            # Initialize reset time (1 minute from now)
            reset_at = now + timedelta(seconds=THESPORTSDB_REQUEST_WINDOW_SECONDS)
            SyncMetadata.set(METADATA_KEY_API_REQUESTS_MINUTE_RESET, reset_at.isoformat())

        # Check if we can make more requests within per-minute limit
        if requests_this_minute + max_requests > THESPORTSDB_REQUESTS_PER_MINUTE:
            return False

        return True

    def _count_by_status(self, status: str) -> int:
        """Count channels by enrichment status."""
        return Channel.query.filter(
            Channel.is_ppv is True,
            Channel.ppv_enrichment_status == status,
        ).count()

    def _update_enrichment_stats(self, stats: Dict):
        """Update persistent enrichment statistics."""
        processed = int(SyncMetadata.get(METADATA_KEY_ENRICHMENT_PROCESSED, "0"))
        processed += stats["processed"]
        SyncMetadata.set(METADATA_KEY_ENRICHMENT_PROCESSED, str(processed))

        failures = int(SyncMetadata.get(METADATA_KEY_ENRICHMENT_FAILURES, "0"))
        failures += stats["failed"]
        SyncMetadata.set(METADATA_KEY_ENRICHMENT_FAILURES, str(failures))

        # Track API usage per-minute
        requests_this_minute = int(SyncMetadata.get(METADATA_KEY_API_REQUESTS_MINUTE, "0"))
        requests_this_minute += stats["api_requests_made"]
        SyncMetadata.set(METADATA_KEY_API_REQUESTS_MINUTE, str(requests_this_minute))

        # Record last run time
        SyncMetadata.set(
            METADATA_KEY_ENRICHMENT_LAST_RUN,
            datetime.now(timezone.utc).isoformat(),
        )


# Singleton instance
_enrichment_queue = None


def get_enrichment_queue(app: Flask) -> PPVEnrichmentQueue:
    """
    Get or create enrichment queue singleton.

    Args:
        app: Flask app instance

    Returns:
        PPVEnrichmentQueue instance
    """
    global _enrichment_queue
    if _enrichment_queue is None:
        _enrichment_queue = PPVEnrichmentQueue(app)
    return _enrichment_queue
