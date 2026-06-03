"""Channel health scan (runs every scheduler tick, not interval-gated)."""

import logging

logger = logging.getLogger(__name__)


def run_channel_health_scan() -> None:
    try:
        from services.channel_health_service import ChannelHealthService

        ChannelHealthService.run_scheduled_scan_pass()
    except Exception as e:
        logger.error("Error in channel health scanning: %s", e)
