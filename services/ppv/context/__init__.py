"""
PPV Context Data Provider package.

Provides a plugin-like architecture for fetching contextual data about sports events
(standings, head-to-head history, team form, event notes) from multiple sources.
The assembled context is passed to an LLM to generate human-readable EPG descriptions.

Usage:
    from services.ppv.context import build_event_context, generate_event_description
    from services.ppv.context.registry import get_registry

    context = build_event_context(event)
    description = generate_event_description(context)
"""

from services.ppv.context.assembler import build_event_context
from services.ppv.context.base import DataType, EventContext, TeamContext
from services.ppv.context.llm_client import generate_event_description, generate_event_description_or_fallback
from services.ppv.context.registry import ProviderRegistry, get_registry

__all__ = [
    "build_event_context",
    "generate_event_description",
    "generate_event_description_or_fallback",
    "get_registry",
    "ProviderRegistry",
    "DataType",
    "EventContext",
    "TeamContext",
]
