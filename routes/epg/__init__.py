"""
EPG routes package - Consolidated EPG management
"""
from .channels import account_epg_channels_bp, epg_channels_bp
from .common import sync_sd_channels_to_epg, sync_sd_lineup_impl
from .match_rules import account_epg_match_rules_bp, epg_match_rules_bp
from .schedules_direct import schedules_direct_bp
from .sources import epg_sources_bp
from .xmltv import xmltv_bp

__all__ = [
    "epg_channels_bp",
    "account_epg_channels_bp",
    "epg_match_rules_bp",
    "account_epg_match_rules_bp",
    "epg_sources_bp",
    "schedules_direct_bp",
    "xmltv_bp",
    "sync_sd_channels_to_epg",
    "sync_sd_lineup_impl",
]
