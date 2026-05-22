"""Backward compatibility — use services.ppv.visibility instead."""

from services.ppv.visibility import PPVVisibilityService  # noqa: F401

__all__ = ["PPVVisibilityService"]
