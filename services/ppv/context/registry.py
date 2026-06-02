"""
Provider registry for the PPV context data provider system.

The registry holds all registered providers and answers the question
"which providers can supply data type X for sport Y in league Z?"
ordered by ascending priority (lowest number = highest priority).

Providers are registered at application startup.  The default set of
built-in providers is registered automatically when get_registry() is
first called.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple

from services.ppv.context.base import ContextDataProvider, DataType

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Registry of ContextDataProvider instances."""

    def __init__(self) -> None:
        self._providers: List[ContextDataProvider] = []

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, provider: ContextDataProvider) -> None:
        """Register a provider.  Replaces any existing provider with the same name."""
        self._providers = [p for p in self._providers if p.name != provider.name]
        self._providers.append(provider)
        self._providers.sort(key=lambda p: p.priority)
        logger.debug("Registered context provider %r (priority=%d)", provider.name, provider.priority)

    def unregister(self, name: str) -> None:
        """Remove a provider by name."""
        self._providers = [p for p in self._providers if p.name != name]

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get_providers_for(
        self,
        sport: str,
        league: str,
        data_type: DataType,
    ) -> List[ContextDataProvider]:
        """
        Return providers that can supply *data_type* for *sport*/*league*,
        ordered by ascending priority.
        """
        return [p for p in self._providers if p.covers(sport, league, data_type)]

    def all_providers(self) -> List[ContextDataProvider]:
        """Return all registered providers in priority order."""
        return list(self._providers)

    # ------------------------------------------------------------------
    # Observability
    # ------------------------------------------------------------------

    def coverage_report(self) -> Dict:
        """
        Return a structured coverage matrix.

        Shape:
        {
            "providers": [{"name": "espn", "priority": 10, "sports": [...], "data_types": [...]}],
            "by_sport": {
                "NFL": {
                    "standings": ["espn"],
                    "head_to_head": ["espn", "thesportsdb"],
                    ...
                },
                ...
            },
            "gaps": [
                {"sport": "Cricket", "data_type": "standings", "note": "no provider registered"}
            ]
        }
        """
        # Collect all sports mentioned across providers
        all_sports: List[str] = []
        for p in self._providers:
            for s in p.supported_sports:
                if s not in all_sports:
                    all_sports.append(s)
        all_sports.sort()

        by_sport: Dict[str, Dict[str, List[str]]] = {}
        for sport in all_sports:
            by_sport[sport] = {}
            for dt in DataType:
                providers_for = [
                    p.name for p in self._providers if p.covers_sport(sport) and dt in p.provided_data_types
                ]
                if providers_for:
                    by_sport[sport][dt.value] = providers_for

        providers_info = [
            {
                "name": p.name,
                "priority": p.priority,
                "sports": sorted(p.supported_sports),
                "leagues": sorted(p.supported_leagues),
                "data_types": sorted(dt.value for dt in p.provided_data_types),
            }
            for p in self._providers
        ]

        # Identify gaps: sports × data_types with no coverage
        gaps: List[Dict[str, str]] = []
        for sport in all_sports:
            for dt in DataType:
                covered = any(p.covers_sport(sport) and dt in p.provided_data_types for p in self._providers)
                if not covered:
                    gaps.append({"sport": sport, "data_type": dt.value, "note": "no provider registered"})

        return {
            "providers": providers_info,
            "by_sport": by_sport,
            "gaps": gaps,
        }


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[ProviderRegistry] = None


def get_registry() -> ProviderRegistry:
    """Return the global provider registry, initialising it on first call."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
        _register_builtin_providers(_registry)
    return _registry


def reset_registry() -> None:
    """Reset the global registry (useful for testing)."""
    global _registry
    _registry = None


def _register_builtin_providers(registry: ProviderRegistry) -> None:
    """Register the built-in provider implementations."""
    try:
        from services.ppv.context.providers.espn import ESPNProvider

        registry.register(ESPNProvider())
    except Exception as exc:
        logger.warning("Could not register ESPN provider: %s", exc)

    try:
        from services.ppv.context.providers.football_data import FootballDataProvider

        registry.register(FootballDataProvider())
    except Exception as exc:
        logger.warning("Could not register football-data.org provider: %s", exc)

    try:
        from services.ppv.context.providers.thesportsdb import TheSportsDBContextProvider

        registry.register(TheSportsDBContextProvider())
    except Exception as exc:
        logger.warning("Could not register TheSportsDB context provider: %s", exc)

    try:
        from services.ppv.context.providers.mlb_stats import MlbStatsContextProvider

        registry.register(MlbStatsContextProvider())
    except Exception as exc:
        logger.warning("Could not register MLB Stats context provider: %s", exc)

    try:
        from services.ppv.context.providers.sportsipy import SportsipyContextProvider

        registry.register(SportsipyContextProvider())
    except Exception as exc:
        logger.warning("Could not register sportsipy context provider: %s", exc)
