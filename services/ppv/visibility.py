"""
PPV Visibility Service - Apply PPV visibility rules based on account settings

Uses database Event records created by services.ppv.enrichment for filtering.
"""

import logging
from datetime import datetime, timedelta, timezone

from models import Event, EventChannelLink, db
from services.ppv.constants import get_sport_grace_hours
from services.ppv.detection import is_generic_channel_name, is_ppv_placeholder_name
from services.ppv.extraction import PPVEventExtractor

logger = logging.getLogger(__name__)


class PPVVisibilityService:
    """Applies PPV visibility rules based on account ppv_visibility setting"""

    # Visibility modes
    HIDE_ALL = "hide_all"
    HIDE_INACTIVE = "hide_inactive"  # Hide inactive/past events
    GROUP_LIVE_REPLAY = "group_live_replay"
    SHOW_ALL = "show_all"

    PPV_GROUP_LIVE = "live"
    PPV_GROUP_REPLAY = "replay"

    VALID_MODES = [HIDE_ALL, HIDE_INACTIVE, GROUP_LIVE_REPLAY, SHOW_ALL]

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
        elif self.ppv_visibility == self.GROUP_LIVE_REPLAY:
            return self.classify_live_replay_channel(channel) is not None
        elif self.ppv_visibility == self.SHOW_ALL:
            # Show all PPV channels
            return True
        else:
            # Unknown mode - default to hiding inactive
            return self._is_ppv_active(channel)

    def classify_live_replay_channel(self, channel, current_time=None):
        """Classify a PPV channel as 'live', 'replay', or None for Live/Replay grouping."""
        if not channel.is_ppv:
            return None

        event = self.get_linked_event(channel)
        return self.classify_live_replay_event(event, current_time=current_time)

    @classmethod
    def classify_live_replay_event(cls, event, current_time=None):
        """Classify an event as 'live', 'replay', or None using a 24-hour Live window."""
        if not event or event.status == Event.STATUS_CANCELLED:
            return None

        current_time = current_time or datetime.now(timezone.utc).replace(tzinfo=None)
        live_cutoff = current_time + timedelta(hours=24)

        if event.status == Event.STATUS_LIVE:
            return cls.PPV_GROUP_LIVE
        if not event.scheduled_at:
            return None
        if event.scheduled_at < current_time:
            return cls.PPV_GROUP_REPLAY
        if event.scheduled_at <= live_cutoff:
            return cls.PPV_GROUP_LIVE
        return None

    @staticmethod
    def _is_far_future_channel(channel_name: str) -> bool:
        """Return True if the channel name contains an explicit date more than 31 days away."""
        extraction = PPVEventExtractor().extract_all(channel_name)
        event_date = extraction.get("date")
        if not isinstance(event_date, datetime):
            return False
        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=31)
        return event_date.replace(tzinfo=None) > cutoff

    @staticmethod
    def _is_inactive_ppv_slot_name(channel_name: str) -> bool:
        """True for generic numbered PPV slots without a real event title."""
        return is_ppv_placeholder_name(channel_name) or is_generic_channel_name(channel_name)

    def get_linked_event(self, channel):
        """Return the most relevant linked event for a channel, if any."""
        cache_key = channel.id
        if cache_key not in self._event_cache:
            self._event_cache[cache_key] = (
                db.session.query(Event)
                .join(EventChannelLink, Event.id == EventChannelLink.event_id)
                .filter(EventChannelLink.channel_id == channel.id)
                .order_by(Event.scheduled_at.desc())  # Most recent event first
                .first()
            )
        return self._event_cache[cache_key]

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
            event = self.get_linked_event(channel)

            # If no event linked, check enrichment status
            if not event:
                if self._is_inactive_ppv_slot_name(channel.name):
                    logger.debug(f"Hiding inactive PPV slot: {channel.name[:60]}")
                    return False

                # If enrichment explicitly marked as "no_match", hide channel (no active event)
                if channel.ppv_enrichment_status == "no_match":
                    logger.debug(f"Hiding channel with no_match status: {channel.name[:60]}")
                    return False

                # If enrichment is queued or processing, show channel (optimistic)
                # but still hide if the channel name indicates a far-future event
                if channel.ppv_enrichment_status in ("queued", "processing"):
                    if self._is_far_future_channel(channel.name):
                        logger.debug(f"Hiding far-future channel (>1 month away): {channel.name[:60]}")
                        return False
                    logger.debug(f"Showing channel being enriched: {channel.name[:60]}")
                    return True

                # If enrichment failed with error, show channel (avoid hiding valid channels)
                if channel.ppv_enrichment_status == "error":
                    logger.debug(f"Showing channel with enrichment error: {channel.name[:60]}")
                    return True

                # No event and no enrichment status - default to hiding (conservative)
                logger.debug(f"Hiding channel with no linked event: {channel.name[:60]}")
                return False

            # Have an event — check status then timing
            current_time = datetime.now(timezone.utc).replace(tzinfo=None)

            # Explicit terminal statuses: hide immediately
            if event.status == Event.STATUS_CANCELLED:
                logger.debug(f"Hiding cancelled event: {channel.name[:60]} (event: {event.external_id})")
                return False

            if event.status == Event.STATUS_FINISHED:
                logger.debug(f"Hiding finished event: {channel.name[:60]} (event: {event.external_id})")
                return False

            # STATUS_LIVE: provider confirmed in-progress — always show
            if event.status == Event.STATUS_LIVE:
                logger.debug(f"Showing live event: {channel.name[:60]} (event: {event.external_id})")
                return True

            # Provider-supplied stop time: show until that moment passes
            stop_time = PPVEventExtractor.extract_stop_time(channel.name)
            if stop_time is not None:
                if current_time < stop_time:
                    logger.debug(
                        f"Showing event within stop: window: {channel.name[:60]} "
                        f"(stop: {stop_time}, event: {event.external_id})"
                    )
                    return True
                # stop: time has passed — fall through to grace-window check

            # Future event: show unless it's more than a month away
            if event.scheduled_at >= current_time:
                far_future_cutoff = current_time + timedelta(days=31)
                if event.scheduled_at > far_future_cutoff:
                    logger.debug(
                        f"Hiding far-future event (>1 month away): {channel.name[:60]} "
                        f"(date: {event.scheduled_at}, event: {event.external_id})"
                    )
                    return False
                logger.debug(
                    f"Showing future event: {channel.name[:60]} "
                    f"(date: {event.scheduled_at}, event: {event.external_id})"
                )
                return True

            # Event started in the past but may still be in-progress:
            # use a sport-aware grace window so games don't vanish mid-broadcast.
            grace_hours = get_sport_grace_hours(event.sport)
            effective_end = event.scheduled_at + timedelta(hours=grace_hours)
            if current_time < effective_end:
                logger.debug(
                    f"Showing event within grace window: {channel.name[:60]} "
                    f"(grace: {grace_hours}h, effective_end: {effective_end}, event: {event.external_id})"
                )
                return True

            # Past grace window — hide
            logger.debug(
                f"Hiding past event (grace expired): {channel.name[:60]} "
                f"(date: {event.scheduled_at}, grace: {grace_hours}h, event: {event.external_id})"
            )
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
            PPVVisibilityService.GROUP_LIVE_REPLAY: {
                "value": PPVVisibilityService.GROUP_LIVE_REPLAY,
                "label": "Group PPV as Live/Replay",
                "description": "Hide PPV categories and group events into Live (next 24 hours) and Replay",
            },
            PPVVisibilityService.SHOW_ALL: {
                "value": PPVVisibilityService.SHOW_ALL,
                "label": "Show All PPV",
                "description": "Show all pay-per-view channels including inactive ones",
            },
        }
