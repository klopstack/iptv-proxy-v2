"""Backward-compatible EpgService facade delegating to services.epg submodules."""

from services.epg import coverage, fcc, generation, matching, matching_legacy, parsing, ppv, utils


class EpgService:
    """
    Backward-compatible facade for EPG service functionality.

    Prefer importing directly from submodules in new code:
        from services.epg.generation import generate_epg_for_channels
        from services.epg.parsing import sync_epg_source
        from services.epg.coverage import get_epg_coverage_stats
    """

    parse_xmltv = staticmethod(parsing.parse_xmltv)
    parse_xmltv_streaming = staticmethod(parsing.parse_xmltv_streaming)
    sync_epg_source = staticmethod(parsing.sync_epg_source)
    create_provider_epg_source = staticmethod(matching_legacy.create_provider_epg_source)

    match_channels_to_epg = staticmethod(matching.match_channels_to_epg)

    @staticmethod
    def match_channels_to_epg_fcc_enhanced(
        account_id: int,
        epg_source_id=None,
        batch_size: int = 100,
    ):
        return matching.match_channels_to_epg(
            account_id,
            source_id=epg_source_id,
            batch_size=batch_size,
            include_filtered=True,
        )

    generate_epg_for_channels = staticmethod(generation.generate_epg_for_channels)
    generate_filtered_epg = staticmethod(generation.generate_filtered_epg)
    _build_channel_link_map = staticmethod(generation.build_channel_link_map)
    _build_mapping_offset_map = staticmethod(generation.build_mapping_offset_map)

    is_ppv_channel = staticmethod(ppv.is_ppv_channel)
    is_ppv_category = staticmethod(ppv.is_ppv_category)
    is_ppv_placeholder_name = staticmethod(ppv.is_ppv_placeholder_name)
    get_ppv_event_title = staticmethod(ppv.get_ppv_event_title)

    get_epg_coverage_stats = staticmethod(coverage.get_epg_coverage_stats)
    get_category_epg_coverage = staticmethod(coverage.get_category_epg_coverage)
    get_unmapped_channels = staticmethod(coverage.get_unmapped_channels)
    get_epg_source_summary = staticmethod(coverage.get_epg_source_summary)

    preview_fcc_epg_matches = staticmethod(fcc.preview_fcc_epg_matches)
    _build_fcc_epg_indices = staticmethod(fcc.build_fcc_epg_indices)
    _build_epg_lookup_indices = staticmethod(fcc.build_epg_lookup_indices)
    _get_fcc_facility_for_channel = staticmethod(fcc.get_fcc_facility_for_channel)
    _match_by_fcc_callsign = staticmethod(fcc.match_by_fcc_callsign)
    _match_by_fcc_network = staticmethod(fcc.match_by_fcc_network)
    _load_fcc_facilities = staticmethod(fcc.load_fcc_facilities)
    _lookup_fcc_callsign = staticmethod(fcc.lookup_fcc_callsign)
    _load_country_tags_for_channels = staticmethod(fcc.load_country_tags_for_channels)
    _load_existing_mappings = staticmethod(fcc.load_existing_mappings)

    _parse_xmltv_time = staticmethod(utils.parse_xmltv_time)

    @staticmethod
    def _normalize_name(name):
        return utils.normalize_channel_name(name) if name else ""

    _get_name_tokens = staticmethod(matching.EpgMatcher.get_name_tokens)

    @staticmethod
    def _calculate_match_score(name1: str, name2: str):
        return matching.EpgMatcher.calculate_match_score(name1, name2)

    @staticmethod
    def _fuzzy_match(
        channel_name: str,
        epg_channels,
        min_score: float = 0.75,
        country_tags=None,
    ):
        return matching.EpgMatcher.fuzzy_match(channel_name, epg_channels, min_score, country_tags)

    @staticmethod
    def _extract_country_from_epg_id(epg_id):
        if epg_id is None:
            return None
        return matching.EpgMatcher.extract_country_from_epg_id(epg_id)

    _prepare_channels_and_epg = staticmethod(matching_legacy.prepare_channels_and_epg)
    _match_channel_strategies = staticmethod(matching_legacy.match_channel_strategies)
    _save_channel_mapping = staticmethod(matching_legacy.save_channel_mapping)
