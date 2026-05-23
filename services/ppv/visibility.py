"""
PPV Visibility Service - Apply PPV visibility rules based on account settings

Uses database Event records created by services.ppv.enrichment for filtering.
"""

import logging
from datetime import datetime, timezone

from models import Event, EventChannelLink, db

logger = logging.getLogger(__name__)


class PPVVisibilityService:
    """Applies PPV visibility rules based on account ppv_visibility setting"""

    # Visibility modes
    HIDE_ALL = "hide_all"
    HIDE_INACTIVE = "hide_inactive"  # Hide inactive/past events
    SHOW_ALL = "show_all"

    VALID_MODES = [HIDE_ALL, HIDE_INACTIVE, SHOW_ALL]

    def __init__(self, account):
        """
        Initialize with an account.

        Args:
            account: Account instance with ppv_visibility setting
        """
        self.account = account
        self.ppv_visibility = getattr(account, "ppv_visibility", self.HIDE_INACTIVE)
        self._event_cache = {}  # Cache event lookups for this service instance

    def should_show_channel(self, channel):
        """
        Determine if a channel should be shown based on PPV visibility rules.

        Uses PPVEventExtractor to detect events in channel names and filter out:
        - Placeholder channels ("NO EVENT STREAMING")
        - Inactive channels (empty/generic names)
        - Past events (event date in the past)
        - Far-future placeholder dates (2098-12-31, 2099-01-01)

        Args:
            channel: Channel instance to check (must have name, is_ppv attributes)

        Returns:
            bool: True if channel should be shown, False to hide
        """
        # If not a PPV channel, always show (PPV rules don't apply)
        if not channel.is_ppv:
            return True

        # Apply PPV visibility rule
        if self.ppv_visibility == self.HIDE_ALL:
            # Hide all PPV channels
            return False
        elif self.ppv_visibility == self.HIDE_INACTIVE:
            # Use event extractor to determine if channel has an active event
            return self._is_ppv_active(channel)
        elif self.ppv_visibility == self.SHOW_ALL:
            # Show all PPV channels
            return True
        else:
            # Unknown mode - default to hiding inactive
            return self._is_ppv_active(channel)

    def _is_ppv_active(self, channel):
        """
        Check if a PPV channel has an active event.

        Queries Event records linked to this channel via EventChannelLink.
        Events are created by services.ppv.enrichment which:
        1. Extracts event info from channel names
        2. Matches against TheSportsDB calendar
        3. Creates Event records with full details

        Args:
            channel: Channel instance to check (needs id attribute)

        Returns:
            bool: True if event is active/upcoming, False if inactive/past/no event
        """
        try:
            # Check cache first
            cache_key = channel.id
            if cache_key in self._event_cache:
                event = self._event_cache[cache_key]
            else:
                # Query linked event for this channel
                event = (
                    db.session.query(Event)
                    .join(EventChannelLink, Event.id == EventChannelLink.event_id)
                    .filter(EventChannelLink.channel_id == channel.id)
                    .order_by(Event.scheduled_at.desc())  # Most recent event first
                    .first()
                )
                self._event_cache[cache_key] = event

            # If no event linked, check enrichment status
            if not event:
                # If enrichment explicitly marked as "no_match", hide channel (no active event)
                if channel.ppv_enrichment_status == "no_match":
                    logger.debug(f"Hiding channel with no_match status: {channel.name[:60]}")
                    return False

                # If enrichment is queued or processing, show channel (optimistic)
                if channel.ppv_enrichment_status in ("queued", "processing"):
                    logger.debug(f"Showing channel being enriched: {channel.name[:60]}")
                    return True

                # If enrichment failed with error, show channel (avoid hiding valid channels)
                if channel.ppv_enrichment_status == "error":
                    logger.debug(f"Showing channel with enrichment error: {channel.name[:60]}")
                    return True

                # No event and no enrichment status - default to hiding (conservative)
                logger.debug(f"Hiding channel with no linked event: {channel.name[:60]}")
                return False

            # Have an event - check if it's in the future
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)

            # Check event status first
            if event.status == Event.STATUS_CANCELLED:
                logger.debug(f"Hiding cancelled event: {channel.name[:60]} (event: {event.external_id})")
                return False

            if event.status == Event.STATUS_FINISHED:
                logger.debug(f"Hiding finished event: {channel.name[:60]} (event: {event.external_id})")
                return False

            # Check scheduled time
            if event.scheduled_at < current_time:
                # Event in past - hide it
                logger.debug(
                    f"Hiding past event: {channel.name[:60]} (date: {event.scheduled_at}, event: {event.external_id})"
                )
                return False

            # Event is in the future or live - show it
            logger.debug(
                f"Showing future/live event: {channel.name[:60]} (date: {event.scheduled_at}, event: {event.external_id})"
            )
            return True

        except Exception as e:
            # Log error but don't crash - default to showing to avoid hiding valid channels
            logger.warning(f"Error checking PPV status for channel '{channel.name}': {e}")
            return True

    @staticmethod
    def get_visibility_options():
        """Get all available PPV visibility options."""
        return {
            PPVVisibilityService.HIDE_ALL: {
                "value": PPVVisibilityService.HIDE_ALL,
                "label": "Hide All PPV",
                "description": "Hide all pay-per-view channels",
            },
            PPVVisibilityService.HIDE_INACTIVE: {
                "value": PPVVisibilityService.HIDE_INACTIVE,
                "label": "Hide Inactive PPV",
                "description": "Show only upcoming/active PPV events, hide past events",
            },
            PPVVisibilityService.SHOW_ALL: {
                "value": PPVVisibilityService.SHOW_ALL,
                "label": "Show All PPV",
                "description": "Show all pay-per-view channels including inactive ones",
            },
        }
