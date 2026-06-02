"""
LLM prompt builder and description generator for PPV events.

Takes an EventContext and produces a safe, fact-grounded EPG description.

Safety guarantees:
- All facts come from EventContext fields; no free-form LLM knowledge allowed
- Sections without data are marked UNKNOWN and the system prompt instructs
  the model to skip those topics entirely
- Temperature 0 eliminates creative embellishment
- Post-generation validator checks for hallucinated numbers: any digit sequence
  in the output that does not appear in the prompt payload triggers fallback
  to the mechanical description
- The system prompt explicitly forbids adding facts not in the FACTS block
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from services.ppv.context.base import EventContext

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sport categorisation helpers
# ---------------------------------------------------------------------------

_COMBAT_SPORTS = frozenset({"boxing", "mma", "wrestling", "kickboxing", "muay thai"})
_INDIVIDUAL_SPORTS = frozenset({"golf", "tennis", "athletics", "cycling", "swimming", "darts", "snooker"})


def _sport_category(sport: str) -> str:
    s = sport.lower()
    if s in _COMBAT_SPORTS:
        return "combat"
    if s in _INDIVIDUAL_SPORTS:
        return "individual"
    return "team"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are writing a short EPG programme description for a live sports event.\n"
    "Rules:\n"
    "1. Write exactly 2 sentences.\n"
    "2. Use ONLY the facts provided in the FACTS block below. "
    "Do NOT add any statistics, records, scores, history, or context not listed there.\n"
    "3. If a fact is marked UNKNOWN, do not mention that topic at all.\n"
    "4. Do not include any numbers that do not appear in the FACTS block.\n"
    "5. Write in present/future tense appropriate for an upcoming broadcast.\n"
    "6. Be factual and neutral; avoid hype or speculation.\n"
    "Output only the two-sentence description, nothing else."
)


def _format_team_section(label: str, team_ctx, sport_cat: str) -> str:
    lines = [f"{label} ({team_ctx.name}):"]
    if team_ctx.record:
        lines.append(f"  - Record: {team_ctx.record}")
    else:
        lines.append("  - Record: UNKNOWN")
    if team_ctx.standing:
        lines.append(f"  - Standing: {team_ctx.standing}")
    else:
        lines.append("  - Standing: UNKNOWN")
    if sport_cat == "combat" and team_ctx.extra:
        lines.append(f"  - Fighter record: {team_ctx.extra}")
    if team_ctx.recent_form:
        lines.append(f"  - Recent form: {', '.join(team_ctx.recent_form[:5])}")
    return "\n".join(lines)


def build_prompt(context: EventContext) -> str:
    """
    Build the user-turn prompt string from an EventContext.

    The system prompt is returned separately via get_system_prompt().
    Together they form the full LLM request.
    """
    sport_cat = _sport_category(context.sport)
    lines = [
        "=== FACTS ===",
        f"Sport: {context.sport or 'UNKNOWN'}",
        f"League/Competition: {context.league or 'UNKNOWN'}",
        "",
        _format_team_section("Home team", context.home_team, sport_cat),
        "",
        _format_team_section("Away team", context.away_team, sport_cat),
    ]

    if context.head_to_head:
        lines.append("")
        lines.append(f"Head-to-head (last {len(context.head_to_head)} meetings):")
        for result in context.head_to_head:
            lines.append(f"  - {result}")
    else:
        lines.append("")
        lines.append("Head-to-head: UNKNOWN")

    if context.event_notes:
        lines.append("")
        lines.append(f"At stake / context: {context.event_notes}")
    else:
        lines.append("")
        lines.append("At stake / context: UNKNOWN")

    lines.append("=== END FACTS ===")
    lines.append("")
    lines.append("Write the 2-sentence EPG description now:")

    return "\n".join(lines)


def get_system_prompt() -> str:
    """Return the system prompt (shared across all requests)."""
    return _SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Post-generation hallucination validator
# ---------------------------------------------------------------------------


def _extract_numbers(text: str) -> set[str]:
    """Extract all digit sequences from text."""
    return set(re.findall(r"\d+", text))


def validate_description(description: str, prompt: str) -> bool:
    """
    Return True if the description passes the hallucination check.

    Fails if the description contains a number that does not appear anywhere
    in the prompt (which contains all the injected facts).
    """
    desc_numbers = _extract_numbers(description)
    prompt_numbers = _extract_numbers(prompt)
    hallucinated = desc_numbers - prompt_numbers
    if hallucinated:
        logger.warning(
            "Hallucination check failed: numbers %s in description not found in prompt",
            hallucinated,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Mechanical fallback description
# ---------------------------------------------------------------------------


def build_mechanical_description(context: EventContext) -> str:
    """
    Build the existing-style label-value description as a safe fallback.
    Used when LLM is disabled or validation fails.
    """
    parts = []
    if context.sport:
        parts.append(f"Sport: {context.sport}")
    if context.league:
        parts.append(f"League: {context.league}")
    if context.home_team.standing:
        parts.append(f"{context.home_team.name}: {context.home_team.standing}")
    elif context.home_team.record:
        parts.append(f"{context.home_team.name}: {context.home_team.record}")
    elif context.home_team.extra:
        parts.append(f"{context.home_team.name}: {context.home_team.extra}")
    if context.away_team.standing:
        parts.append(f"{context.away_team.name}: {context.away_team.standing}")
    elif context.away_team.record:
        parts.append(f"{context.away_team.name}: {context.away_team.record}")
    elif context.away_team.extra:
        parts.append(f"{context.away_team.name}: {context.away_team.extra}")
    if context.head_to_head:
        parts.append(f"Recent H2H: {context.head_to_head[0]}")
    if context.event_notes:
        parts.append(context.event_notes)
    return "\n".join(parts) if parts else "Pay-Per-View Sports Event"
