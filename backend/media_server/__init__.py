"""Media-server abstraction layer (Jellyfin-integration plan Phase 2/3).

See ai_repo/simposter/jellyfin-upgrade-plan.md for the full design and
CLAUDE.md Quirk #58 for what shipped vs. what's still pending.
"""
from .base import ImageType, Library, MediaItem, MediaItemMetadata, MediaServerClient
from .plex_client import PlexClient
from .jellyfin_client import JellyfinClient
from .registry import get_client, get_enabled_clients

__all__ = [
    "ImageType",
    "Library",
    "MediaItem",
    "MediaItemMetadata",
    "MediaServerClient",
    "PlexClient",
    "JellyfinClient",
    "get_client",
    "get_enabled_clients",
]
