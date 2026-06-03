"""Thin coordinator for PPV EPG operations."""

from typing import Any, Dict, List, Optional, Tuple

from models import Event
from services.ppv.epg import queries, sync, xmltv


class PPVEpgService:
    """Service for generating EPG data from PPV events."""

    @staticmethod
    def generate_ppv_epg_xmltv(
        account_id: Optional[int] = None,
        include_inactive: bool = False,
        event_duration_hours: int = 4,
    ) -> bytes:
        return xmltv.generate_ppv_epg_xmltv(
            account_id=account_id,
            include_inactive=include_inactive,
            event_duration_hours=event_duration_hours,
        )

    @staticmethod
    def list_ppv_events(
        mode: str = "all",
        account_id: Optional[int] = None,
        days_ahead: int = 7,
        status: Optional[str] = None,
        data_completeness: Optional[str] = None,
        search: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        return queries.list_ppv_events(
            mode=mode,
            account_id=account_id,
            days_ahead=days_ahead,
            status=status,
            data_completeness=data_completeness,
            search=search,
            page=page,
            per_page=per_page,
        )

    @staticmethod
    def get_ppv_event_detail(event_id: int) -> Optional[Dict[str, Any]]:
        return queries.get_ppv_event_detail(event_id)

    @staticmethod
    def get_ppv_events_for_account(account_id: int) -> List[Dict]:
        return queries.get_ppv_events_for_account(account_id)

    @staticmethod
    def get_upcoming_ppv_events(days_ahead: int = 7) -> List[Dict]:
        return queries.get_upcoming_ppv_events(days_ahead=days_ahead)

    @staticmethod
    def get_event_channels(event_id: int) -> List[Dict]:
        return queries.get_event_channels(event_id)

    @staticmethod
    def create_epg_source_for_ppv_events(name: str = "PPV Events") -> int:
        return sync.create_epg_source_for_ppv_events(name=name)

    @staticmethod
    def sync_ppv_events_to_epg_channels(epg_source_id: int) -> Tuple[int, int]:
        return sync.sync_ppv_events_to_epg_channels(epg_source_id)

    @staticmethod
    def sync_ppv_event_to_epg_channels(event: Event) -> bool:
        return sync.sync_ppv_event_to_epg_channels(event)


def get_ppv_epg_service() -> PPVEpgService:
    """Get singleton instance of PPV EPG service."""
    return PPVEpgService()
