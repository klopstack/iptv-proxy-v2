"""Sportsipy, MiLB, and TheSportsDB team registry refresh job."""

import logging

logger = logging.getLogger(__name__)


def run_sportsipy_team_refresh() -> bool:
    try:
        from services.milb_team_service import refresh_milb_teams_from_mlb_api
        from services.sportsipy_service import (
            get_sportsipy_service,
            refresh_teams_from_sportsipy,
            refresh_tsdb_registry_teams,
            seed_initial_team_data,
        )

        logger.info("Starting sportsipy team data refresh")
        seed_result = seed_initial_team_data()
        if seed_result.get("teams_added", 0) > 0:
            logger.info("Seeded %s initial teams", seed_result["teams_added"])

        result = refresh_teams_from_sportsipy(
            sports=["mlb", "nba", "ncaab", "ncaaf", "nfl", "nhl"],
        )
        if not result.get("success"):
            logger.warning("Sportsipy refresh had issues: %s", result.get("errors", []))
            return False

        logger.info(
            "Sportsipy refresh complete: %s added, %s updated, sports=%s",
            result.get("teams_added", 0),
            result.get("teams_updated", 0),
            result.get("sports_processed", []),
        )

        milb_result = refresh_milb_teams_from_mlb_api()
        if milb_result.get("success"):
            logger.info(
                "MiLB team refresh complete: %s added, %s updated, total=%s",
                milb_result.get("teams_added", 0),
                milb_result.get("teams_updated", 0),
                milb_result.get("total_teams", 0),
            )
        else:
            logger.warning("MiLB team refresh failed: %s", milb_result.get("error"))
            return False

        tsdb_result = refresh_tsdb_registry_teams(sports=("fb", "wnba"))
        if tsdb_result.get("success"):
            logger.info(
                "TheSportsDB registry refresh complete: %s added, %s updated, %s removed, sports=%s",
                tsdb_result.get("teams_added", 0),
                tsdb_result.get("teams_updated", 0),
                tsdb_result.get("teams_removed", 0),
                tsdb_result.get("sports_processed", []),
            )
        else:
            logger.warning("TheSportsDB registry refresh had issues: %s", tsdb_result.get("errors", []))
            return False

        get_sportsipy_service().reload_team_data()
        return True
    except Exception:
        logger.error("Error refreshing sportsipy teams", exc_info=True)
        return False
