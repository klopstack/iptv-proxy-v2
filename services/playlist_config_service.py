"""Playlist configuration helpers (slug assignment and lookup)."""

from typing import Optional

from services.text_utils import slugify


def make_unique_slug(name: str, exclude_id: Optional[int] = None, *, exclude_obj=None) -> str:
    """Derive a unique slug from a playlist name, appending -2, -3, ... on collision."""
    from models import PlaylistConfig
    from models._base import db

    base = slugify(name) or "playlist"
    candidate = base
    counter = 2

    def slug_taken(slug: str) -> bool:
        query = PlaylistConfig.query.filter_by(slug=slug)
        if exclude_id is not None:
            query = query.filter(PlaylistConfig.id != exclude_id)
        if query.first():
            return True
        for pending in db.session.new:
            if not isinstance(pending, PlaylistConfig):
                continue
            if pending is exclude_obj:
                continue
            if pending.id is not None and pending.id == exclude_id:
                continue
            if pending.slug == slug:
                return True
        return False

    while slug_taken(candidate):
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def assign_slug(config) -> None:
    """Set config.slug from config.name, ensuring uniqueness."""
    config.slug = make_unique_slug(config.name, exclude_id=config.id, exclude_obj=config)


def get_playlist_config_by_slug(slug: str):
    """Look up a playlist config by its persisted slug (indexed)."""
    from models import PlaylistConfig

    return PlaylistConfig.query.filter_by(slug=slug.lower()).first()
