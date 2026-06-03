"""
Account admin operations: credentials, category sync, and channel stats.

Extracted from routes/accounts.py so handlers stay thin (parse → service → respond).
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_

from models import Account, Category, Channel, ChannelTag, Credential, EpgSource, Tag, db
from services.account_epg_source_service import (
    find_account_xmltv_epg_source,
    serialize_account_xmltv_epg_source,
    upsert_account_xmltv_epg_source,
)
from services.cache_service import cache_service
from services.channel_query_service import ChannelQueryService
from services.connection_manager import ConnectionManager
from services.datetime_utils import serialize_utc_iso
from services.iptv_service import IPTVService, get_iptv_service_for_account
from services.serializers.credentials import serialize_credential
from services.tag_service import TagService

logger = logging.getLogger(__name__)


class AccountAdminService:
    """Credential CRUD, category sync, and account statistics."""

    @staticmethod
    def list_accounts_data() -> List[Dict[str, Any]]:
        accounts = Account.query.all()

        channel_counts = (
            db.session.query(Channel.account_id, db.func.count(Channel.id))
            .filter(Channel.is_active == True)  # noqa: E712
            .group_by(Channel.account_id)
            .all()
        )
        channel_count_map = {account_id: count for account_id, count in channel_counts}

        xmltv_sources = {
            row.account_id: row
            for row in EpgSource.query.filter(
                EpgSource.account_id.isnot(None),
                EpgSource.source_type == "xmltv_url",
            ).all()
        }

        result = []
        for account in accounts:
            account_data = {
                "id": account.id,
                "name": account.name,
                "server": account.server,
                "enabled": account.enabled,
                "ppv_visibility": account.ppv_visibility,
                "ppv_rename_format": account.ppv_rename_format,
                "ppv_rename_timezone": account.ppv_rename_timezone,
                "fcc_rename_format": account.fcc_rename_format,
                "credentials": [serialize_credential(c) for c in list(account.credentials)],
                "total_max_connections": account.get_total_max_connections(),
                "channel_count": channel_count_map.get(account.id, 0),
                "xmltv_epg_source": serialize_account_xmltv_epg_source(xmltv_sources.get(account.id)),
            }
            account_data["username"] = account.credentials[0].username if account.credentials else None
            result.append(account_data)
        return result

    @staticmethod
    def get_credentials(account: Account) -> List[Dict[str, Any]]:
        return [serialize_credential(c) for c in list(account.credentials)]

    @staticmethod
    def add_credential(account: Account, data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not data.get("username") or not data.get("password"):
            return None, "Username and password are required"

        existing = Credential.query.filter_by(account_id=account.id, username=data["username"]).first()
        if existing:
            return None, "Credential with this username already exists"

        credential = Credential(
            account_id=account.id,
            username=data["username"],
            password=data["password"],
            max_connections=data.get("max_connections", 1),
            enabled=data.get("enabled", True),
        )
        db.session.add(credential)
        db.session.commit()

        try:
            service = IPTVService(
                account.server, credential.username, credential.password, account.user_agent or "okhttp/3.14.9"
            )
            auth_info = service.authenticate()
            user_info = auth_info.get("user_info", {})

            credential.max_connections = int(user_info.get("max_connections", 1) or 1)
            credential.status = user_info.get("status", "Unknown")
            credential.exp_date = user_info.get("exp_date", "")
            db.session.commit()
        except Exception as e:
            logger.warning("Could not verify new credential: %s", e)

        return serialize_credential(credential), None

    @staticmethod
    def update_credential(account_id: int, credential: Credential, data: Dict[str, Any]) -> Dict[str, Any]:
        if "username" in data:
            credential.username = data["username"]
        if "password" in data and data["password"]:
            credential.password = data["password"]
        if "enabled" in data:
            credential.enabled = data["enabled"]
        if "max_connections" in data:
            credential.max_connections = data["max_connections"]

        db.session.commit()
        cache_service.clear_account_cache(account_id)

        account = db.session.get(Account, account_id)
        primary = account.get_primary_credential() if account else None
        if account and primary and primary.id == credential.id and find_account_xmltv_epg_source(account_id):
            try:
                upsert_account_xmltv_epg_source(account, credential)
                db.session.commit()
            except ValueError as e:
                logger.warning("Could not refresh XMLTV EPG URL for account %s: %s", account_id, e)

        return serialize_credential(credential)

    @staticmethod
    def delete_credential(account: Account, credential: Credential) -> Optional[str]:
        if len(account.credentials) <= 1:
            return "Cannot delete the last credential"

        db.session.delete(credential)
        db.session.commit()
        return None

    @staticmethod
    def test_credential(account: Account, credential: Credential) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        try:
            service = IPTVService(
                account.server, credential.username, credential.password, account.user_agent or "okhttp/3.14.9"
            )
            auth_info = service.authenticate()
            user_info = auth_info.get("user_info", {})

            credential.max_connections = int(user_info.get("max_connections", 1) or 1)
            credential.status = user_info.get("status", "Unknown")
            credential.exp_date = user_info.get("exp_date", "")
            db.session.commit()

            return (
                {
                    "success": True,
                    "credential": serialize_credential(credential),
                    "user_info": {
                        "username": user_info.get("username", ""),
                        "status": credential.status,
                        "exp_date": credential.exp_date,
                        "max_connections": credential.max_connections,
                    },
                },
                None,
            )
        except Exception as e:
            logger.error("Error testing credential %s: %s", credential.id, e)
            return None, str(e)

    @staticmethod
    def get_categories_payload(account_id: int) -> List[Dict[str, Any]]:
        """Categories from in-memory cache or DB — no upstream IPTV call."""
        cached = cache_service.get_cached_categories(account_id)
        if cached is not None:
            return cached

        rows = Category.query.filter_by(account_id=account_id, is_active=True).order_by(Category.category_name).all()
        if rows:
            return [
                {
                    "category_id": row.category_id,
                    "category_name": row.category_name,
                    **({"cleaned_name": row.cleaned_name} if row.cleaned_name else {}),
                }
                for row in rows
            ]

        return []

    @staticmethod
    def sync_categories(account: Account) -> Dict[str, Any]:
        """Fetch categories from upstream IPTV, update cache, and process extraction tags."""
        service = get_iptv_service_for_account(account)
        categories = service.get_live_categories()
        cache_service.cache_categories(account.id, categories)

        streams = cache_service.get_cached_streams(account.id)
        if streams:
            try:
                AccountAdminService._process_extraction_tags(account.id, streams, categories)
            except Exception as tag_error:
                logger.warning("Error auto-processing tags for account %s: %s", account.id, tag_error)

        return {"success": True, "categories": categories, "count": len(categories)}

    @staticmethod
    def _process_extraction_tags(account_id: int, streams: List[Dict], categories: List[Dict]) -> None:
        account = db.session.get(Account, account_id)
        if not account:
            return

        category_map = {str(c["category_id"]): c["category_name"] for c in categories}
        tag_rules = TagService.get_rules_for_account(account)

        ChannelTag.query.filter_by(account_id=account_id, source=ChannelTag.SOURCE_EXTRACTION).delete()

        for stream in streams:
            stream_id = str(stream.get("stream_id"))
            channel_name = stream.get("name", "")
            category_id = str(stream.get("category_id", ""))
            category_name = category_map.get(category_id, "")

            tags, _, _, _ = TagService.extract_tags(channel_name, category_name, tag_rules)

            for tag_name in tags:
                normalized_tag = TagService.normalize_tag_name(tag_name)

                if not normalized_tag or len(normalized_tag) < 2:
                    continue

                tag = Tag.query.filter_by(name=normalized_tag).first()
                if not tag:
                    tag = Tag(name=normalized_tag)
                    db.session.add(tag)
                    db.session.flush()

                existing = ChannelTag.query.filter_by(account_id=account_id, stream_id=stream_id, tag_id=tag.id).first()
                if not existing:
                    channel_tag = ChannelTag(
                        account_id=account_id,
                        stream_id=stream_id,
                        tag_id=tag.id,
                        source=ChannelTag.SOURCE_EXTRACTION,
                    )
                    db.session.add(channel_tag)

        db.session.commit()
        logger.info("Auto-processed tags for account %s", account_id)

    @staticmethod
    def get_account_stats(account: Account) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Return stats dict or (None, error_message) when upstream fetch fails."""
        account_id = account.id
        channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()

        if channel_count > 0:
            category_count = db.session.query(Category.id).filter_by(account_id=account_id).count()

            playlist_visible = ChannelQueryService.channels_for_account(account_id)
            visible_count = len(playlist_visible)
            hidden_count = channel_count - visible_count

            category_counts = {}
            category_data = (
                db.session.query(Category.category_id, db.func.count(Channel.id))
                .join(Channel, Channel.category_id == Category.id)
                .filter(Channel.account_id == account_id, Channel.is_active)
                .group_by(Category.category_id)
                .all()
            )
            for cat_id, count in category_data:
                category_counts[str(cat_id)] = count

            return (
                {
                    "total_channels": channel_count,
                    "visible_channels": visible_count,
                    "hidden_channels": hidden_count,
                    "total_categories": category_count,
                    "category_counts": category_counts,
                    "using_database": True,
                    "synced": True,
                    "last_sync": serialize_utc_iso(account.updated_at),
                },
                None,
            )

        try:
            service = get_iptv_service_for_account(account)

            streams = cache_service.get_cached_streams(account_id)
            if not streams:
                streams = service.get_live_streams()
                cache_service.cache_streams(account_id, streams)

            categories = cache_service.get_cached_categories(account_id)
            if not categories:
                categories = service.get_live_categories()
                cache_service.cache_categories(account_id, categories)

            category_counts = {}
            for stream in streams:
                cat_id = str(stream.get("category_id", "Unknown"))
                category_counts[cat_id] = category_counts.get(cat_id, 0) + 1

            return (
                {
                    "total_channels": len(streams),
                    "total_categories": len(categories),
                    "category_counts": category_counts,
                    "using_database": False,
                    "synced": False,
                    "last_sync": None,
                },
                None,
            )
        except Exception as e:
            logger.error("Error fetching stats for account %s: %s", account_id, e)
            return None, str(e)

    @staticmethod
    def test_account_connection(account: Account) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        """Test all credentials for an account. Returns (payload, error, http_status)."""
        account_id = account.id
        credentials: List[Credential] = list(account.credentials) if account.credentials else []

        if not credentials:
            return None, "No credentials configured", 400

        credential_results = []
        total_channels = 0
        total_categories = 0
        first_error = None

        for cred in credentials:
            try:
                service = IPTVService(
                    account.server, cred.username, cred.password, account.user_agent or "okhttp/3.14.9"
                )
                auth_info = service.authenticate()

                if not total_channels:
                    streams = service.get_live_streams()
                    categories = service.get_live_categories()
                    total_channels = len(streams)
                    total_categories = len(categories)

                user_info = auth_info.get("user_info", {})
                cred.max_connections = int(user_info.get("max_connections", 1) or 1)
                cred.status = user_info.get("status", "Unknown")
                cred.exp_date = user_info.get("exp_date", "")
                db.session.commit()

                credential_results.append(
                    {
                        "id": cred.id,
                        "username": cred.username,
                        "success": True,
                        "status": cred.status,
                        "exp_date": cred.exp_date,
                        "max_connections": cred.max_connections,
                    }
                )
            except Exception as e:
                logger.error("Error testing credential %s for account %s: %s", cred.id, account_id, e)
                if not first_error:
                    first_error = str(e)
                credential_results.append(
                    {
                        "id": cred.id,
                        "username": cred.username,
                        "success": False,
                        "error": str(e),
                    }
                )

        if all(not c.get("success") for c in credential_results):
            return (
                {
                    "success": False,
                    "error": first_error or "All credentials failed",
                    "credentials": credential_results,
                },
                None,
                400,
            )

        total_max_connections = sum(c.get("max_connections", 1) for c in credential_results if c.get("success"))
        return (
            {
                "success": True,
                "channels": total_channels,
                "categories": total_categories,
                "total_max_connections": total_max_connections,
                "credentials": credential_results,
                "connection_status": ConnectionManager.get_connection_status(account_id),
            },
            None,
            200,
        )

    @staticmethod
    def preview_filter_matches(
        account: Account, filter_type: str, filter_value: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str], int]:
        """Preview channel count matching a filter. Returns (payload, error, http_status)."""
        account_id = account.id

        if not account.enabled:
            return None, "Account is disabled", 403

        channel_count = Channel.query.filter_by(account_id=account_id, is_active=True).count()
        if channel_count == 0:
            return None, "Account not synced - sync required", 503

        if not filter_type or not filter_value:
            return None, "Missing filter_type or filter_value", 400

        total_query = Channel.query.filter(Channel.account_id == account_id, Channel.is_active)
        total_count = total_query.count()
        match_query = total_query

        if filter_type == "category":
            match_query = match_query.join(Category).filter(Category.category_name.ilike(f"%{filter_value}%"))
        elif filter_type == "channel_name":
            match_query = match_query.filter(
                or_(Channel.name.ilike(f"%{filter_value}%"), Channel.cleaned_name.ilike(f"%{filter_value}%"))
            )
        elif filter_type == "regex":
            try:
                re.compile(filter_value)
                all_channels = total_query.all()
                pattern = re.compile(filter_value, re.IGNORECASE)
                match_count = sum(
                    1
                    for ch in all_channels
                    if pattern.search(ch.name or "") or (ch.cleaned_name and pattern.search(ch.cleaned_name))
                )
                return {"success": True, "match_count": match_count, "total_count": total_count}, None, 200
            except re.error as e:
                return None, f"Invalid regex: {str(e)}", 400
        elif filter_type == "tag":
            tags = [t.strip() for t in filter_value.split(",") if t.strip()]
            if not tags:
                return None, "No tags specified", 400
            tags = TagService.normalize_filter_tags(tags)

            tagged_streams = (
                db.session.query(ChannelTag.stream_id)
                .join(Tag)
                .filter(ChannelTag.account_id == account_id, Tag.name.in_(tags))
                .distinct()
            )
            match_query = match_query.filter(Channel.stream_id.in_(tagged_streams))
        else:
            return None, "Invalid filter_type", 400

        match_count = match_query.count()
        return {"success": True, "match_count": match_count, "total_count": total_count}, None, 200

    @staticmethod
    def cleanup_orphan_tags() -> Dict[str, Any]:
        """Delete tags with no associated channels."""
        orphaned_tags = (
            db.session.query(Tag)
            .outerjoin(ChannelTag, Tag.id == ChannelTag.tag_id)
            .filter(ChannelTag.tag_id.is_(None))
            .all()
        )

        orphan_count = len(orphaned_tags)
        tag_names = [tag.name for tag in orphaned_tags[:100]]

        for tag in orphaned_tags:
            db.session.delete(tag)

        db.session.commit()
        logger.info("Cleaned up %s orphaned tags", orphan_count)

        return {
            "success": True,
            "tags_deleted": orphan_count,
            "sample_tags": tag_names[:20],
        }
