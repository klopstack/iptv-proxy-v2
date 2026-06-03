"""JSON field helpers for model serialization."""

import json
from typing import Any, Optional


def safe_json_loads(value: Optional[str], default: Any = None) -> Any:
    """Parse a JSON column value, returning default when empty."""
    if not value:
        return default
    return json.loads(value)
