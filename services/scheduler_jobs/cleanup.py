"""Scheduled data retention jobs (EPG, health, events, image cache)."""

import logging

from services.scheduler_constants import DEFAULT_EPG_PROGRAM_RETENTION_DAYS

logger = logging.getLogger(__name__)


def run_epg_program_cleanup() -> bool:
    try:
        from services.epg.programs import cleanup_expired_programs

        deleted = cleanup_expired_programs(days_old=DEFAULT_EPG_PROGRAM_RETENTION_DAYS)
        logger.info("EPG program cleanup removed %s row(s)", deleted)
        return True
    except Exception:
        logger.error("Error during EPG program cleanup", exc_info=True)
        return False


def run_health_check_cleanup() -> bool:
    try:
        from services.channel_health_service import cleanup_old_health_checks

        deleted = cleanup_old_health_checks()
        logger.info("Health check cleanup removed %s row(s)", deleted)
        return True
    except Exception:
        logger.error("Error during health check cleanup", exc_info=True)
        return False


def run_event_cleanup() -> bool:
    try:
        from services.event_retention import cleanup_old_events

        deleted = cleanup_old_events()
        logger.info("Event cleanup removed %s event(s)", deleted)
        return True
    except Exception:
        logger.error("Error during event cleanup", exc_info=True)
        return False


def run_image_cache_cleanup() -> bool:
    try:
        from services.image_cache_service import ImageCacheService

        cache = ImageCacheService.get_instance()
        removed = cache.cleanup_expired(delete_files=True)
        logger.info("Image cache cleanup marked %s expired entr(ies)", removed)
        return True
    except Exception:
        logger.error("Error during image cache cleanup", exc_info=True)
        return False
