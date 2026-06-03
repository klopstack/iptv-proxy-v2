"""EPG program and health-check history cleanup jobs."""

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
