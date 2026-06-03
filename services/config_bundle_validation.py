"""Validate configuration import bundles before applying changes."""

from __future__ import annotations

from typing import Any

BUNDLE_TYPE = "iptv-proxy-config-bundle"
SUPPORTED_VERSIONS = frozenset({"1.0"})

_TOP_LEVEL_LIST_KEYS = (
    "accounts",
    "filters",
    "rulesets",
    "account_ruleset_assignments",
    "epg_match_rulesets",
    "account_epg_match_ruleset_assignments",
    "epg_exclusion_patterns",
    "epg_channel_name_mappings",
)

_FCC_PATTERN_LIST_KEYS = (
    "networks",
    "channel_patterns",
    "location_patterns",
    "strategies",
    "country_suffixes",
    "quality_tags",
    "country_tags",
    "callsign_suffixes",
)

_OPTION_KEYS = frozenset({"overwrite", "create_missing_accounts"})


def validate_config_import_bundle(data: Any) -> str | None:
    """Return an error message if the bundle is invalid, else None."""
    if not isinstance(data, dict):
        return "Bundle must be a JSON object"

    if data.get("type") != BUNDLE_TYPE:
        return f'Invalid bundle type (expected "{BUNDLE_TYPE}")'

    version = data.get("version")
    if version is not None and version not in SUPPORTED_VERSIONS:
        return f'Unsupported bundle version "{version}" (supported: {", ".join(sorted(SUPPORTED_VERSIONS))})'

    options = data.get("options")
    if options is not None:
        if not isinstance(options, dict):
            return "options must be an object"
        unknown = set(options) - _OPTION_KEYS
        if unknown:
            return f"Unknown options keys: {', '.join(sorted(unknown))}"
        for key in _OPTION_KEYS:
            if key in options and not isinstance(options[key], bool):
                return f"options.{key} must be a boolean"

    for key in _TOP_LEVEL_LIST_KEYS:
        value = data.get(key)
        if value is None:
            continue
        if not isinstance(value, list):
            return f"{key} must be an array"
        if not all(isinstance(item, dict) for item in value):
            return f"Each entry in {key} must be an object"

    accounts = data.get("accounts") or []
    if accounts:
        for index, account in enumerate(accounts):
            if not isinstance(account, dict):
                return f"accounts[{index}] must be an object"
            name = account.get("name")
            server = account.get("server")
            if name is not None and not isinstance(name, str):
                return f"accounts[{index}].name must be a string"
            if server is not None and not isinstance(server, str):
                return f"accounts[{index}].server must be a string"

    fcc_patterns = data.get("fcc_patterns")
    if fcc_patterns is not None:
        if not isinstance(fcc_patterns, dict):
            return "fcc_patterns must be an object"
        unknown_fcc = set(fcc_patterns) - set(_FCC_PATTERN_LIST_KEYS)
        if unknown_fcc:
            return f"Unknown fcc_patterns keys: {', '.join(sorted(unknown_fcc))}"
        for key in _FCC_PATTERN_LIST_KEYS:
            section = fcc_patterns.get(key)
            if section is None:
                continue
            if not isinstance(section, list):
                return f"fcc_patterns.{key} must be an array"
            if not all(isinstance(item, dict) for item in section):
                return f"Each entry in fcc_patterns.{key} must be an object"

    return None
