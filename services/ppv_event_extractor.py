"""Backward compatibility — use services.ppv.extraction instead."""

from services.ppv.extraction import PPVEventExtractor  # noqa: F401

__all__ = ["PPVEventExtractor"]
