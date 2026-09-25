"""Instantiates a MediaServerClient per enabled entry in the `mediaServers`
setting (seeded in database.py, Phase 1 -- CLAUDE.md Quirk #57). Nothing in
the app calls into this yet (that's Phase 4); this exists now so Phase 3/4
have a stable place to plug JellyfinClient into once it's built.
"""
import json
from typing import List, Optional

from ..config import logger
from .base import MediaServerClient
from .plex_client import PlexClient
from .jellyfin_client import JellyfinClient


def _load_media_servers() -> List[dict]:
    from .. import database as db
    try:
        raw = db.get_ui_settings() or {}
        value = raw.get("mediaServers")
        if isinstance(value, str):
            return json.loads(value)
        if isinstance(value, list):
            return value
    except Exception as e:
        logger.debug("[MEDIA_SERVER] Failed to load mediaServers setting: %s", e)
    return []


def _build_client(entry: dict) -> Optional[MediaServerClient]:
    server_type = entry.get("type")
    server_id = entry.get("id")
    if not server_id:
        return None
    if server_type == "plex":
        return PlexClient(server_id, url=entry.get("url"), token=entry.get("token"))
    if server_type in ("jellyfin", "emby"):
        return JellyfinClient(
            server_id,
            url=entry.get("url") or "",
            api_key=entry.get("apiKey") or entry.get("token") or "",
            is_emby=(server_type == "emby"),
        )
    logger.debug("[MEDIA_SERVER] No client implementation for server type '%s' (id=%s)", server_type, server_id)
    return None


def get_enabled_clients() -> List[MediaServerClient]:
    """Every enabled, currently-supported configured server. An install with
    no mediaServers setting seeded yet (a fresh, not-yet-onboarded install --
    see Quirk #57) gets an empty list here; existing call sites keep using
    settings.PLEX_URL directly until Phase 4 wires them through this."""
    clients = []
    for entry in _load_media_servers():
        if not entry.get("enabled", True):
            continue
        client = _build_client(entry)
        if client:
            clients.append(client)
    return clients


def get_client(server_id: str) -> Optional[MediaServerClient]:
    for entry in _load_media_servers():
        if entry.get("id") == server_id:
            return _build_client(entry)
    return None
