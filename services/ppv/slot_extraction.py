"""
Extract numbered slot identifiers from PPV channel names (MiLB, MLB, etc.).
"""

import re
from typing import Optional

# Order matters: more specific patterns first
PPV_SLOT_PATTERNS = [
    re.compile(r":Milb\s+(\d{1,3})", re.IGNORECASE),
    re.compile(r"\(MiLB\s+(\d{1,3})\)", re.IGNORECASE),
    re.compile(r"(?:^|[\s:])(?:MILB|Milb)\s+(\d{1,3})(?:\s|$|:)", re.IGNORECASE),
    re.compile(
        r"(?:PPV|UFC|NBA|NHL|MLB|MILB|MLS|WNBA)\s*(\d{1,3})\s*[:\-]?\s*$",
        re.IGNORECASE,
    ),
]


def extract_ppv_slot_number(name: str) -> Optional[int]:
    """Return the PPV slot number from a channel name, or None if not found."""
    if not name:
        return None
    for pattern in PPV_SLOT_PATTERNS:
        match = pattern.search(name)
        if match:
            try:
                return int(match.group(1))
            except (ValueError, IndexError):
                continue
    return None
