"""Instantiates a MediaServerClient per enabled entry in the `mediaServers`
setting (seeded in database.py, Phase 1 -- CLAUDE.md Quirk #57). Nothing in
the app calls into this yet (that's Phase 4); this exists now so Phase 3/4
have a stable place to plug JellyfinClient into once it's built.
"""
import json
from typing import List, Optional

from ..config import logger, settings
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


def get_server_label(server_id: str) -> str:
    """Python mirror of frontend/src/services/mediaServerLabel.ts's
    mediaServerLabel() -- a custom `name` (Settings -> Media Servers) when
    one's set, else a generic type label. Used anywhere backend log/status
    text needs to say WHICH server, human-readably (Media Mirror's per-item
    sync log, Quirk #123's follow-up) -- consolidated here so it can't drift
    from what the UI itself already shows for the same server_id."""
    type_labels = {"jellyfin": "Jellyfin", "emby": "Emby", "plex": "Plex"}
    for entry in _load_media_servers():
        if entry.get("id") == server_id:
            name = (entry.get("name") or "").strip()
            if name:
                return name
            return type_labels.get(entry.get("type"), entry.get("type") or server_id)
    if server_id == "plex-1":
        return "Plex"
    return server_id


def get_client(server_id: str) -> Optional[MediaServerClient]:
    for entry in _load_media_servers():
        if entry.get("id") == server_id:
            return _build_client(entry)
    # 'plex-1' is a structural anchor -- every LibraryGroup that has a Plex
    # member uses this exact id (Quirk #62), and PlexClient's own real methods
    # never read the mediaServers entry's own url/token anyway, always using
    # settings.PLEX_URL/PLEX_TOKEN directly regardless of what's passed to the
    # constructor (see plex_client.py's own docstring, Quirk #58). Requiring an
    # explicit, well-formed 'plex-1' entry in the mediaServers LIST before this
    # works at all is an unnecessary, fragile dependency on a setting that has
    # nothing to do with whether Plex is actually configured and reachable --
    # and it's exactly the kind of setting this app has already found real,
    # silent ways to lose (an unrelated settings save wiping it, an upgrade
    # path never re-seeding it, etc.). Fall back to a real PlexClient whenever
    # Plex itself is genuinely configured, independent of whatever state the
    # mediaServers list happens to be in.
    if server_id == "plex-1" and settings.PLEX_URL and settings.PLEX_TOKEN:
        return PlexClient(server_id)
    return None
