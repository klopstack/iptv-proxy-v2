"""
Lightweight LLM client for PPV event description generation.

Supports OpenAI-compatible REST APIs (OpenAI, local Ollama, etc.) and
Anthropic's Messages API.  The provider and model are read from the
``provider_settings`` table under the ``"llm_enrichment"`` namespace so
they can be changed without restarting the service.

Provider settings keys (namespace ``"llm_enrichment"``):
    enabled     - "true" / "false" (default "false")
    provider    - "openai" | "anthropic" (default "openai")
    api_key     - API key for the selected LLM provider
    model       - model name (default "gpt-4o-mini")
    base_url    - optional base URL override (e.g. Ollama)

Returns None (not raises) on any failure so callers can fall back gracefully.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import requests

from services.ppv.context.base import ContextDataProvider, EventContext
from services.ppv.context.prompt_builder import (
    build_mechanical_description,
    build_prompt,
    get_system_prompt,
    validate_description,
)

logger = logging.getLogger(__name__)

_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
_DEFAULT_ANTHROPIC_BASE = "https://api.anthropic.com"
_ANTHROPIC_VERSION = "2023-06-01"
_REQUEST_TIMEOUT = 30  # seconds

# ---------------------------------------------------------------------------
# LLM enrichment settings descriptor (not a real provider — no sports coverage)
# ---------------------------------------------------------------------------

_LLM_NAMESPACE = "llm_enrichment"


class LLMEnrichmentSettings(ContextDataProvider):
    """
    Virtual provider that owns the LLM enrichment settings namespace.

    This class is *not* registered in the provider registry and does not
    supply any sports data.  Its sole purpose is to declare the UI-visible
    settings fields for the LLM description-generation feature so that
    ``/api/ppv-enrichment/provider-settings`` can serve them alongside
    real data-provider settings.
    """

    name = _LLM_NAMESPACE
    supported_sports: set = set()
    supported_leagues: set = set()
    provided_data_types: set = set()
    priority = 0

    def settings_fields(self) -> List[Dict]:
        return [
            {
                "key": "enabled",
                "label": "Enable LLM Description Generation",
                "type": "toggle",
                "description": (
                    "Generate a 2-sentence EPG description for each PPV event using an LLM. "
                    "Requires a valid API key below."
                ),
                "required": False,
                "default": "false",
            },
            {
                "key": "provider",
                "label": "LLM Provider",
                "type": "select",
                "description": "Which LLM provider to use for description generation.",
                "required": False,
                "default": "openai",
                "options": [
                    {"value": "openai", "label": "OpenAI (or compatible)"},
                    {"value": "anthropic", "label": "Anthropic"},
                ],
            },
            {
                "key": "api_key",
                "label": "API Key",
                "type": "password",
                "description": "API key for the selected LLM provider.",
                "required": True,
            },
            {
                "key": "model",
                "label": "Model",
                "type": "text",
                "description": (
                    "Model name, e.g. gpt-4o-mini or claude-3-haiku-20240307."
                ),
                "required": False,
                "default": _DEFAULT_MODEL,
            },
            {
                "key": "base_url",
                "label": "Base URL Override",
                "type": "text",
                "description": (
                    "Optional base URL for OpenAI-compatible APIs (e.g. Ollama, LiteLLM). "
                    "Leave empty to use the provider default."
                ),
                "required": False,
                "default": "",
            },
        ]


def _llm_setting(key: str, default: str = "") -> str:
    """Read an LLM enrichment setting from the provider_settings table."""
    try:
        from models.provider_settings import ProviderSettings
        return ProviderSettings.get(_LLM_NAMESPACE, key, default=default)
    except Exception:
        return default


def generate_event_description(context: EventContext) -> Optional[str]:
    """
    Generate a 2-sentence EPG description for the event described by *context*.

    Returns the description string on success, or None if:
    - LLM enrichment is disabled in settings
    - No API key is configured
    - The API call fails
    - The output fails the hallucination validator

    Falls back to build_mechanical_description() when returning None
    is not acceptable (callers decide).
    """
    enabled = _llm_setting("enabled", "false")
    if str(enabled).lower() not in ("true", "1", "yes"):
        logger.debug("LLM enrichment disabled via settings")
        return None

    api_key = _llm_setting("api_key", "").strip()
    if not api_key:
        logger.debug("No LLM API key configured; skipping description generation")
        return None

    provider = (_llm_setting("provider", "openai") or "openai").strip().lower()
    model = (_llm_setting("model", _DEFAULT_MODEL) or _DEFAULT_MODEL).strip()
    base_url = _llm_setting("base_url", "").strip()

    prompt = build_prompt(context)
    system = get_system_prompt()

    try:
        if provider == "anthropic":
            description = _call_anthropic(api_key, model, system, prompt, base_url or _DEFAULT_ANTHROPIC_BASE)
        else:
            description = _call_openai(api_key, model, system, prompt, base_url or _DEFAULT_OPENAI_BASE)
    except Exception as exc:
        logger.warning("LLM API call failed: %s", exc)
        return None

    if not description:
        return None

    if not validate_description(description, prompt):
        logger.warning(
            "LLM description for %s vs %s failed hallucination check; discarding",
            context.home_team.name,
            context.away_team.name,
        )
        return None

    logger.info(
        "Generated LLM description for %s vs %s via %s/%s",
        context.home_team.name,
        context.away_team.name,
        provider,
        model,
    )
    return description.strip()


def generate_event_description_or_fallback(context: EventContext) -> str:
    """
    Like generate_event_description but always returns a string.
    Falls back to the mechanical description when LLM returns None.
    """
    result = generate_event_description(context)
    if result:
        return result
    return build_mechanical_description(context)


# ---------------------------------------------------------------------------
# Provider-specific HTTP calls
# ---------------------------------------------------------------------------

def _call_openai(api_key: str, model: str, system: str, prompt: str, base_url: str) -> Optional[str]:
    """Call an OpenAI-compatible chat completions endpoint."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": 200,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return None
    return (choices[0].get("message") or {}).get("content")


def _call_anthropic(api_key: str, model: str, system: str, prompt: str, base_url: str) -> Optional[str]:
    """Call Anthropic's Messages API."""
    url = f"{base_url.rstrip('/')}/v1/messages"
    payload = {
        "model": model,
        "max_tokens": 200,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": _ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=_REQUEST_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    content = data.get("content") or []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            return block.get("text")
    return None
