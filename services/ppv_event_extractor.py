"""Backward compatibility — use services.ppv.extraction instead."""

import warnings

warnings.warn(
    "Import from services.ppv.extraction instead of services.ppv_event_extractor",
    DeprecationWarning,
    stacklevel=2,
)

from services.ppv.extraction import PPVEventExtractor  # noqa: F401

__all__ = ["PPVEventExtractor"]
