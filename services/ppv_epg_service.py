"""Backward compatibility — use services.ppv.epg instead."""

import warnings

warnings.warn(
    "Import from services.ppv.epg instead of services.ppv_epg_service",
    DeprecationWarning,
    stacklevel=2,
)

from services.ppv.epg import PPVEpgService  # noqa: F401

__all__ = ["PPVEpgService"]
