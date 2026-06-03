"""Serializers for EPG source API responses."""

from typing import Any

from services.datetime_utils import serialize_utc_iso


def serialize_epg_source(source, *, mapping_count: int = 0) -> dict[str, Any]:
    """Serialize an EpgSource for JSON responses."""
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "account_id": source.account_id,
        "account_name": source.account.name if source.account else None,
        "url": source.url,
        "priority": source.priority,
        "enabled": source.enabled,
        "last_sync": serialize_utc_iso(source.last_sync),
        "last_sync_status": source.last_sync_status,
        "last_sync_message": source.last_sync_message,
        "channel_count": source.channel_count,
        "used_mapping_count": mapping_count,
        "xmltv_grabber": source.xmltv_grabber,
        "xmltv_config_name": source.xmltv_config_name,
        "xmltv_days": source.xmltv_days,
        "xmltv_offset": source.xmltv_offset,
        "xmltv_extra_args": source.xmltv_extra_args,
    }
