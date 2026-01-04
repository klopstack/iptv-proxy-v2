"""
PPV Visibility Service - Apply PPV visibility rules based on account settings

Uses PPVEventExtractor to detect events in channel names and filter inactive channels.
"""

import logging
from datetime import datetime, timezone

from services.ppv_event_extractor import PPVEventExtractor

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
        self.event_extractor = PPVEventExtractor(current_date=datetime.now(timezone.utc).replace(tzinfo=None))

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

        Uses PPVEventExtractor to:
        1. Detect placeholder channels (NO EVENT STREAMING)
        2. Detect inactive channels (empty/generic names)
        3. Extract event dates and check if in future
        4. Detect far-future placeholder dates (2098-12-31)

        Args:
            channel: Channel instance to check (needs name attribute)

        Returns:
            bool: True if event is active/upcoming, False if inactive/past
        """
        try:
            # Extract all event information from channel name
            event_info = self.event_extractor.extract_all(channel.name)

            # Hide if channel is a placeholder (NO EVENT STREAMING)
            if event_info.get("is_placeholder"):
                logger.debug(f"Hiding placeholder channel: {channel.name[:60]}")
                return False

            # Hide if channel is inactive (empty/generic name)
            if event_info.get("is_inactive"):
                logger.debug(f"Hiding inactive channel: {channel.name[:60]}")
                return False

            # Hide if date was inferred as too far in future (placeholder date)
            if event_info.get("inferred_how") == "date_too_far_future":
                logger.debug(f"Hiding far-future placeholder channel: {channel.name[:60]}")
                return False

            # Check if event has a date
            event_date = event_info.get("date")
            if event_date:
                # Hide if event is in the past
                current_time = datetime.now(timezone.utc).replace(tzinfo=None)
                if event_date < current_time:
                    logger.debug(f"Hiding past event: {channel.name[:60]} (date: {event_date})")
                    return False
                else:
                    # Event is in the future - show it
                    logger.debug(f"Showing future event: {channel.name[:60]} (date: {event_date})")
                    return True

            # If no date extracted, check if competitors were found
            # Channels with competitors but no date are likely upcoming events
            if event_info.get("competitors"):
                logger.debug(f"Showing channel with competitors: {channel.name[:60]}")
                return True

            # No event information found - default to hiding (conservative)
            logger.debug(f"Hiding channel with no event info: {channel.name[:60]}")
            return False

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
