"""
Delete an IPTV account and all account-scoped database rows.

Global/shared rows are preserved: tags, events, rulesets, playlist_configs,
epg_match_rulesets (only account junction rows are removed).
"""

import logging
from typing import Dict, List

from sqlalchemy import delete, select

from models import (
    Account,
    AccountEpgMatchRuleSet,
    AccountRuleSet,
    ActiveStream,
    Category,
    Channel,
    ChannelEpgMapping,
    ChannelHealthCheck,
    ChannelHealthStatus,
    ChannelLink,
    ChannelTag,
    Credential,
    EpgChannel,
    EpgProgram,
    EpgSource,
    EventChannelLink,
    Filter,
    SdLineup,
    SdStation,
    XtreamCredential,
    db,
)

logger = logging.getLogger(__name__)


class AccountDeleteService:
    """Remove an account and dependent rows in FK-safe order."""

    @staticmethod
    def delete_account(account_id: int) -> Dict:
        """
        Delete account and all owned data.

        Returns:
            Dict with success flag and deletion counts.
        """
        account = db.session.get(Account, account_id)
        if not account:
            return {"success": False, "error": "Account not found"}

        account_name = account.name
        stats: Dict[str, int] = {}

        channel_ids: List[int] = list(
            db.session.scalars(select(Channel.id).where(Channel.account_id == account_id)).all()
        )
        credential_ids: List[int] = list(
            db.session.scalars(select(Credential.id).where(Credential.account_id == account_id)).all()
        )
        epg_source_ids: List[int] = list(
            db.session.scalars(select(EpgSource.id).where(EpgSource.account_id == account_id)).all()
        )

        if epg_source_ids:
            epg_channel_ids: List[int] = list(
                db.session.scalars(select(EpgChannel.id).where(EpgChannel.source_id.in_(epg_source_ids))).all()
            )
            if epg_channel_ids:
                stats["epg_programs"] = AccountDeleteService._exec_delete(
                    delete(EpgProgram).where(EpgProgram.epg_channel_id.in_(epg_channel_ids))
                )
                stats["channel_epg_mappings_epg"] = AccountDeleteService._exec_delete(
                    delete(ChannelEpgMapping).where(ChannelEpgMapping.epg_channel_id.in_(epg_channel_ids))
                )

            lineup_ids: List[int] = list(
                db.session.scalars(select(SdLineup.id).where(SdLineup.epg_source_id.in_(epg_source_ids))).all()
            )
            if lineup_ids:
                stats["sd_stations"] = AccountDeleteService._exec_delete(
                    delete(SdStation).where(SdStation.lineup_id.in_(lineup_ids))
                )
                stats["sd_lineups"] = AccountDeleteService._exec_delete(
                    delete(SdLineup).where(SdLineup.id.in_(lineup_ids))
                )

            stats["epg_channels"] = AccountDeleteService._exec_delete(
                delete(EpgChannel).where(EpgChannel.source_id.in_(epg_source_ids))
            )
            stats["epg_sources"] = AccountDeleteService._exec_delete(
                delete(EpgSource).where(EpgSource.id.in_(epg_source_ids))
            )

        if channel_ids:
            stats["channel_epg_mappings"] = AccountDeleteService._exec_delete(
                delete(ChannelEpgMapping).where(ChannelEpgMapping.channel_id.in_(channel_ids))
            )
            stats["event_channel_links"] = AccountDeleteService._exec_delete(
                delete(EventChannelLink).where(EventChannelLink.channel_id.in_(channel_ids))
            )
            stats["channel_health_checks"] = AccountDeleteService._exec_delete(
                delete(ChannelHealthCheck).where(ChannelHealthCheck.channel_id.in_(channel_ids))
            )
            stats["channel_health_status"] = AccountDeleteService._exec_delete(
                delete(ChannelHealthStatus).where(ChannelHealthStatus.channel_id.in_(channel_ids))
            )
            stats["channel_links"] = AccountDeleteService._exec_delete(
                delete(ChannelLink).where(
                    (ChannelLink.channel_id.in_(channel_ids)) | (ChannelLink.source_channel_id.in_(channel_ids))
                )
            )

        if credential_ids:
            stats["active_streams"] = AccountDeleteService._exec_delete(
                delete(ActiveStream).where(ActiveStream.credential_id.in_(credential_ids))
            )

        stats["channel_tags"] = AccountDeleteService._exec_delete(
            delete(ChannelTag).where(ChannelTag.account_id == account_id)
        )
        stats["channels"] = AccountDeleteService._exec_delete(delete(Channel).where(Channel.account_id == account_id))
        stats["categories"] = AccountDeleteService._exec_delete(
            delete(Category).where(Category.account_id == account_id)
        )
        stats["account_rulesets"] = AccountDeleteService._exec_delete(
            delete(AccountRuleSet).where(AccountRuleSet.account_id == account_id)
        )
        stats["account_epg_match_rulesets"] = AccountDeleteService._exec_delete(
            delete(AccountEpgMatchRuleSet).where(AccountEpgMatchRuleSet.account_id == account_id)
        )
        stats["filters"] = AccountDeleteService._exec_delete(delete(Filter).where(Filter.account_id == account_id))
        stats["xtream_credentials"] = AccountDeleteService._exec_delete(
            delete(XtreamCredential).where(XtreamCredential.account_id == account_id)
        )
        stats["credentials"] = AccountDeleteService._exec_delete(
            delete(Credential).where(Credential.account_id == account_id)
        )

        db.session.delete(account)
        db.session.commit()

        logger.info("Deleted account %s (id=%s): %s", account_name, account_id, stats)
        return {"success": True, "account_id": account_id, "account_name": account_name, "deleted": stats}

    @staticmethod
    def _exec_delete(statement) -> int:
        result = db.session.execute(statement)
        return getattr(result, "rowcount", 0) or 0
