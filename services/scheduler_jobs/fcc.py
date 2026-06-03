"""FCC facility data sync job."""

import logging

logger = logging.getLogger(__name__)


def run_fcc_sync() -> bool:
    try:
        from services.fcc_facility_service import FccFacilityService

        logger.info("Starting weekly FCC facility data sync")
        result = FccFacilityService.full_sync()
        if result.get("success"):
            stats = result.get("stats", {})
            logger.info(
                "FCC data synced: %s added, %s updated, %s total",
                stats.get("added", 0),
                stats.get("updated", 0),
                stats.get("total", 0),
            )
            return True
        logger.warning("FCC sync issue: %s", result.get("message", "Unknown error"))
        return False
    except Exception as e:
        logger.error("Error syncing FCC data: %s", e)
        return False
