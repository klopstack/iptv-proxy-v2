"""Serializers for account credential API responses."""

from typing import Any

from models import Credential


def serialize_credential(credential: Credential) -> dict[str, Any]:
    """Serialize a credential for JSON responses."""
    return {
        "id": credential.id,
        "username": credential.username,
        "max_connections": credential.max_connections or 1,
        "active_connections": credential.active_connections or 0,
        "status": credential.status,
        "exp_date": credential.exp_date,
        "enabled": credential.enabled,
    }
