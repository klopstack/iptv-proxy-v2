"""Backward compatibility — use services.ppv.epg instead."""

from services.ppv.epg import PPVEpgService  # noqa: F401

__all__ = ["PPVEpgService"]
