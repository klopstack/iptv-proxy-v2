"""
PPV Filtering Service - Apply PPV visibility rules based on account settings
"""

from datetime import datetime, timezone

from services.ppv_filter_service import PPVFilterService


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
        self.ppv_filter = PPVFilterService(current_time=datetime.now(timezone.utc).replace(tzinfo=None))

    def should_show_channel(self, channel):
        """
        Determine if a channel should be shown based on PPV visibility rules.

        Args:
            channel: Channel instance to check

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
            # Hide inactive/past PPV events
            return self._is_ppv_active(channel)
        elif self.ppv_visibility == self.SHOW_ALL:
            # Show all PPV channels
            return True
        else:
            # Unknown mode - default to hiding inactive
            return self._is_ppv_active(channel)

    def _is_ppv_active(self, channel):
        """
        Check if a PPV event is active (not in the past).

        Extracts datetime from channel name and compares with current time.

        Args:
            channel: Channel instance to check

        Returns:
            bool: True if event is in future or currently happening, False if in past
        """
        try:
            # Try to extract event datetime from channel name
            event_datetime = self.ppv_filter.parse_iso_datetime_with_24hr(channel.name)

            if event_datetime:
                # If datetime is in future, show it
                return event_datetime > datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                # If we can't parse a datetime, default to showing it
                # (incomplete channel info, not actively filtered)
                return True
        except Exception:
            # If parsing fails, show the channel
            # (safer to show than hide due to parsing errors)
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
