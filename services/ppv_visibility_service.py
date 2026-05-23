"""Backward compatibility — use services.ppv.visibility instead."""

import warnings

warnings.warn(
    "Import from services.ppv.visibility instead of services.ppv_visibility_service",
    DeprecationWarning,
    stacklevel=2,
)

from services.ppv.visibility import PPVVisibilityService  # noqa: F401

__all__ = ["PPVVisibilityService"]
