"""
PPV EPG Service — package split (TODO 102 phase 2).

- xmltv — XMLTV builder
- queries — event listing and detail
- sync — EpgSource / EpgChannel sync helpers
- service — PPVEpgService coordinator
"""

from services.ppv.epg.service import PPVEpgService, get_ppv_epg_service

__all__ = ["PPVEpgService", "get_ppv_epg_service"]
