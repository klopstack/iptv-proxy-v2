"""
Lightweight LLM client for PPV event description generation.

Supports OpenAI-compatible REST APIs (OpenAI, local Ollama, etc.) and
Anthropic's Messages API.  The provider and model are read from Settings
at call time so they can be changed without restarting the service.

Settings keys used:
    ppv_llm_enrichment_enabled  - "true" / "false" (default "false")
    ppv_llm_provider            - "openai" | "anthropic" (default "openai")
    ppv_llm_api_key             - API key for the selected provider
    ppv_llm_model               - model name (default "gpt-4o-mini")
    ppv_llm_base_url            - optional base URL override (e.g. Ollama)

Returns None (not raises) on any failure so callers can fall back gracefully.
"""

from __future__ import annotations

import logging
from typing import Optional

import requests

from services.ppv.context.base import EventContext
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
    try:
        from models.sync import Settings
    except ImportError:
        return None

    enabled = Settings.get("ppv_llm_enrichment_enabled", "false")
    if str(enabled).lower() not in ("true", "1", "yes"):
        logger.debug("LLM enrichment disabled via settings")
        return None

    api_key = (Settings.get("ppv_llm_api_key", "") or "").strip()
    if not api_key:
        logger.debug("No LLM API key configured; skipping description generation")
        return None

    provider = (Settings.get("ppv_llm_provider", "openai") or "openai").strip().lower()
    model = (Settings.get("ppv_llm_model", _DEFAULT_MODEL) or _DEFAULT_MODEL).strip()
    base_url = (Settings.get("ppv_llm_base_url", "") or "").strip()

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
