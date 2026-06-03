"""EPG program package — re-exports for backward compatibility."""

from services.epg.program_persistence import create_epg_program as _create_program
from services.epg.program_persistence import update_epg_program as _update_program
from services.epg.programs.repository import (
    cleanup_expired_programs,
    get_current_program,
    get_current_programs_batch,
    get_database_coverage_stats,
    get_programs_for_channels,
    get_schedule_around_time,
    get_upcoming_programs,
    has_programs_in_database,
    search_programs_by_title,
)
from services.epg.programs.sync import (
    CHANNEL_PROGRAM_BUFFER_FLUSH,
    DEFAULT_BATCH_SIZE,
    DEFAULT_PREVIEW_HOURS,
    get_epg_channel_id_map,
    get_matched_epg_channel_ids,
    parse_xmltv_programs_streaming,
    sync_programs_for_source,
)
from services.epg.programs.xmltv_export import (
    epg_channel_to_xmltv_element,
    format_xmltv_time,
    generate_xmltv_from_database,
    program_to_xmltv_element,
)

__all__ = [
    "_create_program",
    "_update_program",
    "CHANNEL_PROGRAM_BUFFER_FLUSH",
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_PREVIEW_HOURS",
    "cleanup_expired_programs",
    "epg_channel_to_xmltv_element",
    "format_xmltv_time",
    "generate_xmltv_from_database",
    "get_current_program",
    "get_current_programs_batch",
    "get_database_coverage_stats",
    "get_epg_channel_id_map",
    "get_matched_epg_channel_ids",
    "get_programs_for_channels",
    "get_schedule_around_time",
    "get_upcoming_programs",
    "has_programs_in_database",
    "parse_xmltv_programs_streaming",
    "program_to_xmltv_element",
    "search_programs_by_title",
    "sync_programs_for_source",
]
