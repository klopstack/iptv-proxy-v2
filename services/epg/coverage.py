"""
EPG Coverage Module

Handles EPG coverage statistics and reporting.
"""
import logging
from typing import Dict, List, Optional

from models import Category, Channel, ChannelEpgMapping, EpgChannel, EpgSource, db

logger = logging.getLogger(__name__)


def get_epg_coverage_stats(account_id: Optional[int] = None) -> Dict:
    """
    Get EPG coverage statistics.

    Args:
        account_id: Optional - filter to specific account

    Returns:
        Dict with coverage statistics
    """
    # Count channels with EPG mappings
    mapping_query = db.session.query(ChannelEpgMapping.channel_id).distinct()

    if account_id:
        # Filter to channels from this account
        mapping_query = mapping_query.join(Channel, ChannelEpgMapping.channel_id == Channel.id).filter(
            Channel.account_id == account_id
        )

    mapped_count = mapping_query.count()

    # Count total channels
    channel_query = Channel.query.filter_by(is_active=True)
    if account_id:
        channel_query = channel_query.filter_by(account_id=account_id)
    total_count = channel_query.count()

    # Count channels with provider EPG IDs
    provider_epg_query = Channel.query.filter(
        Channel.is_active == True, Channel.epg_channel_id.isnot(None), Channel.epg_channel_id != ""  # noqa: E712
    )
    if account_id:
        provider_epg_query = provider_epg_query.filter_by(account_id=account_id)
    provider_epg_count = provider_epg_query.count()

    # Count EPG sources and channels
    epg_source_count = EpgSource.query.filter_by(enabled=True).count()
    epg_channel_count = EpgChannel.query.count()

    return {
        "total_channels": total_count,
        "channels_with_provider_epg_id": provider_epg_count,
        "channels_with_epg_mapping": mapped_count,
        "coverage_percent": round((mapped_count / total_count * 100), 1) if total_count > 0 else 0,
        "epg_sources": epg_source_count,
        "epg_channels_available": epg_channel_count,
    }


def get_category_epg_coverage(account_id: int) -> List[Dict]:
    """
    Get EPG coverage broken down by category.

    Args:
        account_id: Account to get stats for

    Returns:
        List of dicts with category info and EPG coverage
    """
    results = []

    categories = Category.query.filter_by(account_id=account_id).all()

    for category in categories:
        # Count total active channels in category
        total = Channel.query.filter_by(account_id=account_id, category_id=category.id, is_active=True).count()

        if total == 0:
            continue

        # Count channels with provider EPG ID
        with_provider_epg = Channel.query.filter(
            Channel.account_id == account_id,
            Channel.category_id == category.id,
            Channel.is_active == True,  # noqa: E712
            Channel.epg_channel_id.isnot(None),
            Channel.epg_channel_id != "",
        ).count()

        # Count channels with EPG mappings
        with_mapping = (
            db.session.query(Channel.id)
            .join(ChannelEpgMapping, Channel.id == ChannelEpgMapping.channel_id)
            .filter(
                Channel.account_id == account_id,
                Channel.category_id == category.id,
                Channel.is_active == True,  # noqa: E712
            )
            .count()
        )

        results.append(
            {
                "category_id": category.id,
                "category_name": category.category_name,
                "total_channels": total,
                "with_provider_epg": with_provider_epg,
                "with_epg_mapping": with_mapping,
                "coverage_percent": round((with_mapping / total * 100), 1) if total > 0 else 0,
                "is_ppv": category.is_ppv or False,
            }
        )

    return sorted(results, key=lambda x: x["category_name"])


def get_unmapped_channels(account_id: int, limit: int = 100) -> List[Dict]:
    """
    Get channels that don't have EPG mappings.

    Args:
        account_id: Account to check
        limit: Max number of results

    Returns:
        List of channel dicts without EPG mappings
    """
    # Subquery for channels WITH mappings
    mapped_ids = db.session.query(ChannelEpgMapping.channel_id).subquery()

    # Channels NOT in the mapped set
    unmapped = (
        Channel.query.filter(
            Channel.account_id == account_id, Channel.is_active == True, ~Channel.id.in_(mapped_ids)  # noqa: E712
        )
        .limit(limit)
        .all()
    )

    return [
        {
            "id": ch.id,
            "stream_id": ch.stream_id,
            "name": ch.name,
            "cleaned_name": ch.cleaned_name,
            "category_id": ch.category_id,
            "epg_channel_id": ch.epg_channel_id,
        }
        for ch in unmapped
    ]


def get_epg_source_summary() -> List[Dict]:
    """
    Get summary of all EPG sources and their channel counts.

    Returns:
        List of EPG source summaries
    """
    sources = EpgSource.query.all()

    results = []
    for source in sources:
        channel_count = EpgChannel.query.filter_by(source_id=source.id).count()
        mapping_count = (
            db.session.query(ChannelEpgMapping.id)
            .join(EpgChannel, ChannelEpgMapping.epg_channel_id == EpgChannel.id)
            .filter(EpgChannel.source_id == source.id)
            .count()
        )

        results.append(
            {
                "id": source.id,
                "name": source.name,
                "source_type": source.source_type,
                "enabled": source.enabled,
                "priority": source.priority,
                "channel_count": channel_count,
                "mapping_count": mapping_count,
                "url": source.url,
            }
        )

    return sorted(results, key=lambda x: x["priority"])
