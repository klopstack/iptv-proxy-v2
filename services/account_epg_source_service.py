"""Manage XMLTV EPG sources linked to IPTV accounts (provider xmltv.php feed)."""

from __future__ import annotations

import logging
import re
from typing import Optional, Tuple
from urllib.parse import quote

from models import Account, Credential, EpgSource, db

logger = logging.getLogger(__name__)

# Sources created via account UI use this suffix so they are identifiable.
ACCOUNT_XMLTV_NAME_SUFFIX = " (IPTV XMLTV)"


def normalize_account_server(server: str) -> str:
    """Strip scheme and trailing slash from server host (matches accounts UI)."""
    value = (server or "").strip()
    value = re.sub(r"^https?://", "", value, flags=re.IGNORECASE)
    return value.rstrip("/")


def build_account_xmltv_url(server: str, username: str, password: str) -> str:
    """Build Xtream Codes xmltv.php URL with credentials in query string."""
    host = normalize_account_server(server)
    user = quote(username or "", safe="")
    pwd = quote(password or "", safe="")
    return f"https://{host}/xmltv.php?username={user}&password={pwd}"


def account_xmltv_source_name(account_name: str) -> str:
    return f"{account_name}{ACCOUNT_XMLTV_NAME_SUFFIX}"


def find_account_xmltv_epg_source(account_id: int) -> Optional[EpgSource]:
    """
    Return the auto-managed XMLTV source for an account, if any.

    Only sources with account_id set and type xmltv_url are considered.
    """
    return (
        EpgSource.query.filter_by(account_id=account_id, source_type="xmltv_url").order_by(EpgSource.id.asc()).first()
    )


def upsert_account_xmltv_epg_source(
    account: Account, credential: Optional[Credential] = None
) -> Tuple[EpgSource, bool]:
    """
    Create or update an xmltv_url EPG source for this account's primary credential.

    Returns:
        (source, created) where created is True if a new row was inserted.
    """
    cred = credential or account.get_primary_credential()
    if not cred:
        raise ValueError("Account has no credentials configured")

    url = build_account_xmltv_url(account.server, cred.username, cred.password)
    name = account_xmltv_source_name(account.name)

    source = find_account_xmltv_epg_source(account.id)
    created = source is None
    if source is None:
        source = EpgSource(
            name=name,
            source_type="xmltv_url",
            account_id=account.id,
            url=url,
            priority=200,
            enabled=True,
        )
        db.session.add(source)
    else:
        source.name = name
        source.url = url
        source.account_id = account.id
        source.enabled = True

    db.session.flush()
    logger.info(
        "%s account XMLTV EPG source for account %s (%s)",
        "Created" if created else "Updated",
        account.id,
        account.name,
    )
    return source, created


def serialize_account_xmltv_epg_source(source: Optional[EpgSource]) -> Optional[dict]:
    if not source:
        return None
    return {
        "id": source.id,
        "name": source.name,
        "source_type": source.source_type,
        "url": source.url,
        "enabled": source.enabled,
        "last_sync": source.last_sync.isoformat() if source.last_sync else None,
        "last_sync_status": source.last_sync_status,
        "channel_count": source.channel_count,
    }
