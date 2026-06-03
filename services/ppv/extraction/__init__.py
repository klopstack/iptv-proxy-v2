"""
PPV channel name extraction (competitors, dates, sport hints).

Parsing and normalization for calendar-based enrichment live in
``services.ppv.enrichment`` and ``services.ppv.matching``; see
``docs/architecture/ppv-matching-strategies.md`` for the end-to-end flow.

Package split (TODO 102 phase 3):
- patterns — regex constants
- competitors — team/matchup extraction
- date_strategies — per-format date parsers
- extractor — PPVEventExtractor coordinator
"""

from services.ppv.extraction.extractor import PPVEventExtractor
from services.ppv.extraction.types import MatchupInfo

__all__ = ["MatchupInfo", "PPVEventExtractor"]
