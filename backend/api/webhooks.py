"""
Webhook handlers for automatic poster generation.

This module provides webhook endpoints for integrating with:
- Radarr: Movie library management (webhook on movie import/download)
- Sonarr: TV show library management (webhook on episode import/download)
- Tautulli: Plex activity monitoring (webhook on library events)

When configured, these webhooks automatically generate posters when new media
is added to your Plex library. Settings for auto-send and auto-labels can be
configured in the Performance tab under "Automatic Poster Generation".

Example webhook URLs:
- Radarr: http://your-server:5000/webhook/radarr/{template_id}/{preset_id}
- Sonarr: http://your-server:5000/webhook/sonarr/{template_id}/{preset_id}?include_seasons=true
- Tautulli: http://your-server:5000/webhook/tautulli?template_id=...&preset_id=...&event_types=watched,added
"""

from fastapi import APIRouter, HTTPException, Query, Body, BackgroundTasks, Depends, Request
from typing import Dict, Any, Optional, List, Callable
import hmac
import xml.etree.ElementTree as ET
import time
import threading

from ..config import logger, settings, plex_headers, plex_session, load_presets, load_render_cache, plex_remove_label, plex_add_label, get_label_to_add
from ..schemas import MovieBatchRequest, TVShowBatchRequest, Movie
from .. import database as db
from .. import cache
from ..media_server import get_client
from .notifications import send_discord_notification, send_apprise_notification

router = APIRouter()


def verify_webhook_secret(request: Request) -> None:
    """
    Reject webhook calls when a shared secret is configured but not supplied/matching.

    No-op when settings.WEBHOOK_SECRET is unset (the default) — preserves existing
    trusted-network deployments where no secret was ever configured. When a secret IS
    set (Settings -> Automation -> Webhook Secret, or WEBHOOK_SECRET env var), it must
    be supplied via the "X-Webhook-Secret" header or "?secret=" query param, matching
    how Radarr/Sonarr/Tautulli let you attach a custom header or query string to
    webhook URLs.
    """
    secret = settings.WEBHOOK_SECRET
    if not secret:
        return
    supplied = request.headers.get("X-Webhook-Secret") or request.query_params.get("secret") or ""
    if not hmac.compare_digest(supplied, secret):
        logger.warning("[WEBHOOK] Rejected request to %s: missing or invalid webhook secret", request.url.path)
        raise HTTPException(status_code=401, detail="Invalid or missing webhook secret")


# ============================================================================
# TEMPLATE MIGRATION - Backward compatibility
# ============================================================================

def _normalize_template_id(template_id: str) -> str:
    """
    Convert legacy 'default' and 'universal' template IDs to 'uniformlogo'.
    Provides backward compatibility for existing webhook configurations.
    """
    if template_id in ('default', 'universal'):
        logger.info(f"[WEBHOOK] Converting legacy template '{template_id}' to 'uniformlogo'")
        return 'uniformlogo'
    return template_id


# ============================================================================
# WEBHOOK COOLDOWN - Prevent duplicate poster generation
# ============================================================================
# When Sonarr imports multiple episodes for the same season, each episode
# fires a separate webhook. This cooldown coalesces them so only one
# poster generation runs per show+season combo within the cooldown window.

_webhook_cooldowns: Dict[str, float] = {}
_webhook_cooldown_lock = threading.Lock()
WEBHOOK_COOLDOWN_SECONDS = 300  # 5 minutes


def _check_webhook_cooldown(key: str) -> bool:
    """
    Check if a webhook with this key was recently processed.

    Returns True if the webhook should be SKIPPED (within cooldown period).
    Returns False if the webhook should be PROCESSED (first occurrence or cooldown expired).
    """
    with _webhook_cooldown_lock:
        now = time.time()
        last_processed = _webhook_cooldowns.get(key)

        if last_processed and (now - last_processed) < WEBHOOK_COOLDOWN_SECONDS:
            logger.info(f"[WEBHOOK] Cooldown active for key '{key}' - skipping duplicate (last processed {int(now - last_processed)}s ago)")
            return True  # Skip - duplicate within cooldown

        # Record this webhook and allow processing
        _webhook_cooldowns[key] = now

        # Cleanup old entries to prevent memory growth
        cutoff = now - WEBHOOK_COOLDOWN_SECONDS * 2
        expired = [k for k, v in _webhook_cooldowns.items() if v < cutoff]
        for k in expired:
            del _webhook_cooldowns[k]

        return False  # Process this webhook


# ============================================================================
# HELPER FUNCTIONS - Cache updates
# ============================================================================

def _update_movie_cache(rating_key: str, library_id: Optional[str] = None):
    """
    Fetch movie metadata from Plex and update the cache.
    This ensures newly added movies appear in the library view.
    """
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        logger.debug(f"[WEBHOOK] Fetching Plex metadata from: {url}")
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        video = root.find(".//Video")
        if video is not None:
            # Get library_id from the metadata if not provided
            actual_library_id = library_id
            if not actual_library_id:
                actual_library_id = video.get("librarySectionID")
                logger.debug(f"[WEBHOOK] Extracted librarySectionID from Plex: {actual_library_id}")

            if not actual_library_id:
                logger.warning(f"[WEBHOOK] No library_id found for movie {rating_key}, using 'default'")
                actual_library_id = "default"

            # Create Movie object for cache
            movie = Movie(
                key=rating_key,
                title=video.get("title", "Unknown"),
                year=int(video.get("year")) if video.get("year") else None,
                addedAt=int(video.get("addedAt", 0)),
                library_id=actual_library_id
            )

            # Get TMDB ID if available
            tmdb_id = None
            for guid in video.findall(".//Guid"):
                guid_id = guid.get("id", "")
                if "tmdb://" in guid_id:
                    try:
                        tmdb_id = int(guid_id.split("tmdb://")[1])
                    except (ValueError, IndexError):
                        pass
                    break

            cache.upsert_movie(movie, tmdb_id=tmdb_id)
            logger.info(f"[WEBHOOK] Updated movie cache for {rating_key} ({movie.title}) in library {actual_library_id}")
        else:
            logger.warning(f"[WEBHOOK] No Video element found in Plex response for {rating_key}")

    except Exception as e:
        logger.warning(f"[WEBHOOK] Failed to update movie cache for {rating_key}: {e}", exc_info=True)


def _update_tv_cache(rating_key: str, library_id: Optional[str] = None):
    """
    Fetch TV show metadata from Plex and update the cache.
    This ensures newly added shows appear in the library view.
    """
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        logger.debug(f"[WEBHOOK] Fetching Plex TV metadata from: {url}")
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        directory = root.find(".//Directory[@type='show']")
        if directory is not None:
            # Get library_id from the metadata if not provided
            actual_library_id = library_id
            if not actual_library_id:
                actual_library_id = directory.get("librarySectionID")
                logger.debug(f"[WEBHOOK] Extracted librarySectionID from Plex: {actual_library_id}")

            if not actual_library_id:
                logger.warning(f"[WEBHOOK] No library_id found for TV show {rating_key}, using 'default'")
                actual_library_id = "default"

            # Get external IDs
            tmdb_id = None
            tvdb_id = None
            for guid in directory.findall(".//Guid"):
                guid_id = guid.get("id", "")
                if "tmdb://" in guid_id:
                    try:
                        tmdb_id = int(guid_id.split("tmdb://")[1])
                    except (ValueError, IndexError):
                        pass
                elif "tvdb://" in guid_id:
                    try:
                        tvdb_id = int(guid_id.split("tvdb://")[1])
                    except (ValueError, IndexError):
                        pass

            # Create show dict for cache
            show = {
                "key": rating_key,
                "title": directory.get("title", "Unknown"),
                "year": int(directory.get("year")) if directory.get("year") else None,
                "addedAt": int(directory.get("addedAt", 0)),
                "library_id": actual_library_id
            }

            cache.upsert_tv_show(show, tmdb_id=tmdb_id, tvdb_id=tvdb_id)
            logger.info(f"[WEBHOOK] Updated TV cache for {rating_key} ({show['title']}) in library {actual_library_id}")
        else:
            logger.warning(f"[WEBHOOK] No Directory[@type='show'] element found in Plex response for {rating_key}")

    except Exception as e:
        logger.warning(f"[WEBHOOK] Failed to update TV cache for {rating_key}: {e}", exc_info=True)


# ============================================================================
# HELPER FUNCTIONS - Label checking for webhook ignore
# ============================================================================

def _get_item_labels(rating_key: str) -> List[str]:
    """
    Get labels for a Plex item by rating_key.

    Returns:
        List of label names (strings), empty list if no labels or error
    """
    try:
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.content)

        labels = []
        # Look for labels in Video (movies) or Directory (TV shows)
        for elem in root.findall(".//*[@ratingKey]"):
            for label in elem.findall(".//Label"):
                tag = label.get("tag")
                if tag:
                    labels.append(tag)

        logger.debug(f"[WEBHOOK] Found labels for {rating_key}: {labels}")
        return labels
    except Exception as e:
        logger.warning(f"[WEBHOOK] Failed to get labels for {rating_key}: {e}")
        return []


def _get_default_remove_labels(library_id: str) -> List[str]:
    """
    Get the per-library 'Default Labels to Remove' configured in Settings.
    These are merged with the global auto-labels when sending posters via
    auto-generate, webhooks, or scheduled scans.
    """
    try:
        ui_settings = db.get_ui_settings()
        if not ui_settings:
            return []
        default_labels = ui_settings.get("defaultLabelsToRemove", {}) or {}
        if isinstance(default_labels, dict):
            return [l for l in (default_labels.get(str(library_id), []) or []) if l]
        elif isinstance(default_labels, list):
            return [l for l in default_labels if l]
        return []
    except Exception as e:
        logger.warning(f"[WEBHOOK] Failed to get default remove labels for library {library_id}: {e}")
        return []


def _get_webhook_ignore_labels(library_id: str, is_tv: bool = False) -> List[str]:
    """
    Get the list of labels to ignore for webhook processing for a library.

    Args:
        library_id: The library ID
        is_tv: True for TV libraries, False for movie libraries

    Returns:
        List of label names to ignore
    """
    try:
        ui_settings = db.get_ui_settings()
        if not ui_settings:
            return []

        plex_settings = ui_settings.get("plex", {})

        if is_tv:
            mappings = plex_settings.get("tvShowLibraryMappings", []) or []
        else:
            mappings = plex_settings.get("libraryMappings", []) or []

        for mapping in mappings:
            if mapping.get("id") == library_id:
                ignore_labels = mapping.get("webhookIgnoreLabels", []) or []
                logger.debug(f"[WEBHOOK] Ignore labels for library {library_id}: {ignore_labels}")
                return ignore_labels

        return []
    except Exception as e:
        logger.warning(f"[WEBHOOK] Failed to get ignore labels for library {library_id}: {e}")
        return []


def _should_skip_webhook(rating_key: str, library_id: str, is_tv: bool = False) -> bool:
    """
    Check if a webhook should be skipped based on item labels.

    Returns:
        True if the item should be skipped (has an ignore label), False otherwise
    """
    ignore_labels = _get_webhook_ignore_labels(library_id, is_tv)
    if not ignore_labels:
        return False

    item_labels = _get_item_labels(rating_key)
    if not item_labels:
        return False

    # Check if any item label matches an ignore label (case-insensitive)
    ignore_labels_lower = [l.lower() for l in ignore_labels]
    for label in item_labels:
        if label.lower() in ignore_labels_lower:
            try:
                _t, _ = db.get_title_for_rating_key(rating_key)
            except Exception:
                _t = None
            logger.info("[WEBHOOK] Skipping %s [%s] - has ignore label '%s'", rating_key, _t or "?", label)
            return True

    return False


# ============================================================================
# HELPER FUNCTIONS - Find Plex items by external IDs
# ============================================================================

def find_plex_movie_by_tmdb_id(tmdb_id: int, library_id: Optional[str] = None) -> Optional[tuple]:
    """
    Find a Plex movie's rating_key by its TMDb ID.

    Args:
        tmdb_id: The TMDb ID to search for
        library_id: Optional library ID to search in (defaults to all movie libraries)

    Returns:
        Tuple of (rating_key, library_id) if found, None otherwise
    """
    try:
        # Get Plex library to search
        if library_id:
            libraries = [{"key": library_id}]
        else:
            # Get all movie libraries from settings
            lib_url = f"{settings.PLEX_URL}/library/sections"
            r = plex_session.get(lib_url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            libraries = [
                {"key": sec.get("key")}
                for sec in root.findall(".//Directory[@type='movie']")
            ]

        # Search each library for the TMDb ID
        for lib in libraries:
            lib_key = lib["key"]
            # includeGuids=1 is required to get external IDs (TMDb, IMDB, etc.) in the response
            url = f"{settings.PLEX_URL}/library/sections/{lib_key}/all?includeGuids=1"
            r = plex_session.get(url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)

            for video in root.findall(".//Video"):
                rating_key = video.get("ratingKey")
                # Check GUID for TMDb match. Must be an exact match -- "tmdb://58" is a
                # literal substring of "tmdb://5825", so a naive `in` check here would
                # match the wrong movie whenever one TMDb ID is a numeric prefix of another.
                for guid in video.findall("Guid"):
                    guid_id = guid.get("id", "")
                    if guid_id == f"tmdb://{tmdb_id}":
                        logger.info("[WEBHOOK] Found movie rating_key=%s [%s] in library=%s for TMDb ID %s", rating_key, video.get("title", "?"), lib_key, tmdb_id)
                        return (rating_key, lib_key)

        logger.warning(f"[WEBHOOK] Could not find Plex movie with TMDb ID {tmdb_id}")
        return None

    except Exception as e:
        logger.error(f"[WEBHOOK] Error searching for movie with TMDb ID {tmdb_id}: {e}")
        return None


def find_plex_show_by_tvdb_id(tvdb_id: int, library_id: Optional[str] = None) -> Optional[tuple]:
    """
    Find a Plex TV show's rating_key by its TVDb ID.

    Args:
        tvdb_id: The TVDb ID to search for
        library_id: Optional library ID to search in (defaults to all TV libraries)

    Returns:
        Tuple of (rating_key, library_id) if found, None otherwise
    """
    try:
        # Get Plex library to search
        if library_id:
            libraries = [{"key": library_id}]
        else:
            # Get all TV show libraries from settings
            lib_url = f"{settings.PLEX_URL}/library/sections"
            r = plex_session.get(lib_url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)
            libraries = [
                {"key": sec.get("key")}
                for sec in root.findall(".//Directory[@type='show']")
            ]

        # Search each library for the TVDb ID
        for lib in libraries:
            lib_key = lib["key"]
            # includeGuids=1 is required to get external IDs (TVDb, IMDB, etc.) in the response
            url = f"{settings.PLEX_URL}/library/sections/{lib_key}/all?includeGuids=1"
            r = plex_session.get(url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)

            for video in root.findall(".//Directory[@type='show']"):
                rating_key = video.get("ratingKey")
                # Check GUID for TVDb match. Must be an exact match -- see the identical
                # fix/comment in find_plex_movie_by_tmdb_id() above.
                for guid in video.findall("Guid"):
                    guid_id = guid.get("id", "")
                    if guid_id == f"tvdb://{tvdb_id}":
                        logger.info("[WEBHOOK] Found TV show rating_key=%s [%s] in library=%s for TVDb ID %s", rating_key, video.get("title", "?"), lib_key, tvdb_id)
                        return (rating_key, lib_key)

        logger.warning(f"[WEBHOOK] Could not find Plex TV show with TVDb ID {tvdb_id}")
        return None

    except Exception as e:
        logger.error(f"[WEBHOOK] Error searching for TV show with TVDb ID {tvdb_id}: {e}")
        return None


def find_plex_item_with_retry(
    find_func: Callable,
    external_id: int,
    item_type: str,
    library_id: Optional[str] = None,
    initial_delay: int = 30,
    max_retries: int = 5,
    retry_delay: int = 15
) -> Optional[tuple]:
    """
    Find a Plex item with retry logic to handle cases where Plex hasn't
    imported the file yet when the webhook fires.

    Args:
        find_func: The function to call (find_plex_movie_by_tmdb_id or find_plex_show_by_tvdb_id)
        external_id: The external ID (TMDb or TVDb)
        item_type: Type for logging ("movie" or "TV show")
        library_id: Optional library ID to search in
        initial_delay: Seconds to wait before first lookup attempt (default 30)
        max_retries: Maximum number of retry attempts (default 5)
        retry_delay: Seconds between retries (default 15)

    Returns:
        Tuple of (rating_key, library_id) if found, None if not found after all retries
    """
    # Initial delay to give the media server (Plex, or Jellyfin/Emby per
    # Phase 8b -- item_type carries "(server=...)" for those) time to import
    # the file
    logger.info(f"[WEBHOOK] Waiting {initial_delay}s for the media server to import {item_type} (ID: {external_id})")
    time.sleep(initial_delay)

    for attempt in range(max_retries + 1):
        result = find_func(external_id, library_id)
        if result:
            if attempt > 0:
                logger.info(f"[WEBHOOK] Found {item_type} on retry {attempt} (ID: {external_id})")
            return result

        if attempt < max_retries:
            logger.info(f"[WEBHOOK] {item_type} not found (ID: {external_id}), retry {attempt + 1}/{max_retries} in {retry_delay}s")
            time.sleep(retry_delay)

    logger.warning(f"[WEBHOOK] {item_type} not found after {max_retries} retries (ID: {external_id})")
    return None


def find_media_server_item_by_external_id(
    server_id: str,
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
    media_type: str,  # "movie" | "tv"
    library_id: str,
) -> Optional[tuple]:
    """Non-Plex counterpart to find_plex_movie_by_tmdb_id()/
    find_plex_show_by_tvdb_id() above, for Phase 8b (webhook automation
    without Plex). Resolves an item on a SPECIFIC Jellyfin/Emby server via
    the already-built, already-verified MediaServerClient.
    find_item_by_external_id() (Quirk #58/#98), instead of Plex's own raw-XML
    GUID search -- there's no reason to reimplement matching logic here.

    `library_id` is REQUIRED (not optional, unlike the two Plex resolvers'
    whole-server search) -- MediaServerClient has no "search every library on
    this server" equivalent, and Quirk #98 already established that an
    unscoped lookup can resolve to the WRONG same-tmdb_id item when more than
    one library on the server happens to have a title with that id (a
    duplicate/4K library, or an untracked library sharing the server). The
    webhook URL for a non-Plex server must always specify a library.

    Returns (item_id, library_id) -- the same shape find_plex_movie_by_tmdb_id()/
    find_plex_show_by_tvdb_id() return, so it composes with the existing
    find_plex_item_with_retry() loop unmodified via a thin local closure
    (see process_media_server_webhook_with_retry() below) rather than this
    function needing find_plex_item_with_retry()'s exact (external_id,
    library_id) 2-arg calling shape itself."""
    if not library_id:
        logger.warning("[WEBHOOK] Non-Plex webhook lookup requires a library_id (server=%s, media_type=%s) -- refusing to search unscoped", server_id, media_type)
        return None
    try:
        client = get_client(server_id)
        if not client:
            logger.warning("[WEBHOOK] No enabled MediaServerClient for server_id=%s -- is it still configured in Settings -> Media Servers?", server_id)
            return None
        item_id = client.find_item_by_external_id(tmdb_id, tvdb_id, media_type, library_id)
        if item_id:
            logger.info("[WEBHOOK] Found %s item_id=%s on server=%s library=%s (tmdb=%s tvdb=%s)", media_type, item_id, server_id, library_id, tmdb_id, tvdb_id)
            return (item_id, library_id)
        logger.warning("[WEBHOOK] Could not find %s on server=%s library=%s (tmdb=%s tvdb=%s)", media_type, server_id, library_id, tmdb_id, tvdb_id)
        return None
    except Exception as e:
        logger.error("[WEBHOOK] Error searching for %s on server=%s: %s", media_type, server_id, e)
        return None


def _nonplex_group_members(media_type: str) -> List[tuple]:
    """Every (server_id, library_id) Jellyfin/Emby member of the user's Library
    Groups for this media type, in group order, de-duplicated."""
    out: List[tuple] = []
    try:
        groups = (db.get_ui_settings() or {}).get("libraryGroups") or []
    except Exception as e:
        logger.warning("[WEBHOOK] Couldn't read library groups: %s", e)
        return out
    if not isinstance(groups, list):
        logger.warning("[WEBHOOK] libraryGroups setting has unexpected type %s -- ignoring", type(groups).__name__)
        return out
    for g in groups:
        if (g.get("mediaType") or "movie") != media_type:
            continue
        for m in g.get("members") or []:
            pair = (m.get("serverId"), m.get("libraryId"))
            if pair[0] and pair[1] and pair[0] != "plex-1" and pair not in out:
                out.append(pair)
    return out


def _nonplex_server_libraries(media_type: str) -> List[tuple]:
    """Fallback when no Library Group holds a Jellyfin/Emby library: ask every
    enabled Jellyfin/Emby server for its libraries of this media type. Lets a
    webhook find its item without any groups configured at all."""
    out: List[tuple] = []
    try:
        from ..media_server import get_enabled_clients, PlexClient
        clients = [c for c in get_enabled_clients() if not isinstance(c, PlexClient)]
    except Exception as e:
        logger.warning("[WEBHOOK] Couldn't load configured media servers: %s", e)
        return out
    for client in clients:
        try:
            for lib in client.list_libraries():
                if lib.media_type == media_type and (client.server_id, lib.id) not in out:
                    out.append((client.server_id, lib.id))
        except Exception as e:
            logger.warning("[WEBHOOK] Couldn't list libraries on %s: %s", client.server_id, e)
    return out


def _resolve_webhook_target(server_id: Optional[str], library_id: Optional[str], media_type: str, group_id: Optional[str] = None) -> tuple:
    """Decide where a Radarr/Sonarr webhook's item should be looked up when the
    URL doesn't name a non-Plex server explicitly.

    Returns (kind, server_id, library_id, candidates):
      - ("plex", "plex-1", library_id, None) -- the original Plex path.
      - ("media_server", sid, lid, None) -- one specific Jellyfin/Emby library.
      - ("media_server", None, None, [(sid, lid), ...]) -- search these in order.
      - ("none", None, None, None) -- nothing configured that could hold it.

    Webhook URLs created before Plex was removed (or that never named a
    server) still work: a library_id belonging to a Jellyfin/Emby group
    member is mapped to that member's server, and with no Plex configured at
    all, every Jellyfin/Emby library in the user's Library Groups is
    searched instead of an empty Plex URL.
    """
    if group_id:
        # The Webhook URL Generator's normal mode: the URL names a Library
        # Group. Plex member present (and Plex configured) -> the Plex path,
        # which syncs to the group's other members, with the group's
        # Jellyfin/Emby libraries as the fallback for a title Plex doesn't
        # have (returned as `candidates`). Otherwise search the group's
        # Jellyfin/Emby libraries directly; the render then reaches every
        # member of the group. An unknown group_id (deleted since the URL
        # was made) falls through to the default behavior below.
        try:
            groups = (db.get_ui_settings() or {}).get("libraryGroups") or []
        except Exception:
            groups = []
        # Accept either the group's id or its name (case-insensitive, within
        # this media type) -- the Webhook URL Generator uses the readable
        # name whenever it's unique, so URLs look like ?group=4k-Movies.
        group = next((g for g in groups if g.get("id") == group_id), None)
        if group is None:
            wanted = str(group_id).strip().lower()
            named = [g for g in groups
                     if (g.get("mediaType") or "movie") == media_type and str(g.get("name") or "").strip().lower() == wanted]
            if len(named) == 1:
                group = named[0]
            elif len(named) > 1:
                logger.warning("[WEBHOOK] More than one %s library group is named '%s' -- use the group id instead", media_type, group_id)
        if group:
            members = [(m.get("serverId"), m.get("libraryId")) for m in group.get("members") or [] if m.get("serverId") and m.get("libraryId")]
            plex_member = next((lid for sid, lid in members if sid == "plex-1"), None)
            others = [(sid, lid) for sid, lid in members if sid != "plex-1"]
            if plex_member and settings.PLEX_URL and settings.PLEX_TOKEN:
                return ("plex", "plex-1", plex_member, others or None)
            if others:
                return ("media_server", None, None, others)
            return ("none", None, None, None)
        logger.warning("[WEBHOOK] Library group %s from the webhook URL no longer exists -- using default lookup", group_id)
    if server_id and server_id != "plex-1":
        return ("media_server", server_id, library_id, None)
    members = _nonplex_group_members(media_type)
    if library_id:
        owner = next((sid for sid, lid in members if str(lid) == str(library_id)), None)
        if owner:
            return ("media_server", owner, library_id, None)
    if settings.PLEX_URL and settings.PLEX_TOKEN:
        return ("plex", "plex-1", library_id, None)
    if members:
        return ("media_server", None, None, members)
    server_libs = _nonplex_server_libraries(media_type)
    if server_libs:
        logger.info("[WEBHOOK] No %s library group found -- searching all %d %s librar%s on your Jellyfin/Emby server(s)",
                    media_type, len(server_libs), media_type, "y" if len(server_libs) == 1 else "ies")
        return ("media_server", None, None, server_libs)
    try:
        _ui = db.get_ui_settings() or {}
        _groups = _ui.get("libraryGroups") or []
        _servers = _ui.get("mediaServers") or []
    except Exception:
        _groups, _servers = [], []
    logger.warning(
        "[WEBHOOK] Nowhere to look this %s up: Plex isn't configured, %d library group(s) exist but none "
        "has a %s Jellyfin/Emby library, and no enabled Jellyfin/Emby server returned a %s library "
        "(media servers configured: %s)",
        media_type, len(_groups) if isinstance(_groups, list) else 0, media_type, media_type,
        ", ".join(f"{s.get('id')}({'on' if s.get('enabled', True) else 'off'})" for s in _servers if isinstance(s, dict)) or "none",
    )
    return ("none", None, None, None)


def _find_on_candidates(candidates: List[tuple], tmdb_id, tvdb_id, media_type: str) -> Optional[tuple]:
    """Search several (server_id, library_id) pairs in order; returns
    (item_id, library_id, server_id) for the first match."""
    for sid, lid in candidates:
        found = find_media_server_item_by_external_id(sid, tmdb_id, tvdb_id, media_type, lid)
        if found:
            return (found[0], found[1], sid)
    return None


def process_radarr_webhook_with_retry(
    tmdb_id: int,
    title: str,
    year: Optional[int],
    template_id: str,
    preset_id: str,
    auto_send: bool,
    auto_labels: List[str],
    library_id: Optional[str] = None,
    fallback_candidates: Optional[List[tuple]] = None,
):
    """
    Background task for Radarr webhooks that waits for Plex import, then generates poster.

    `library_id` (from the webhook URL's own optional query param -- see radarr_webhook())
    scopes find_plex_item_with_retry()'s search to one specific Plex library instead of
    searching every movie library and using whichever has a match first, which is
    ambiguous whenever the same title exists in more than one library.
    """
    logger.info(f"[RADARR_WEBHOOK] Starting delayed processing for: {title} ({year}) - TMDb ID: {tmdb_id}")

    # Find movie with retry logic - returns (rating_key, library_id) tuple
    result = find_plex_item_with_retry(
        find_func=find_plex_movie_by_tmdb_id,
        external_id=tmdb_id,
        item_type="movie",
        library_id=library_id,
        initial_delay=30,
        max_retries=5,
        retry_delay=15
    )

    if not result:
        if fallback_candidates:
            # Group webhook: Plex doesn't have it, but the group's Jellyfin/Emby
            # libraries might (a title can exist on only one server).
            logger.info(f"[RADARR_WEBHOOK] {title} not on Plex -- trying the group's other libraries")
            process_media_server_webhook_with_retry(
                server_id=None, media_type="movie", tmdb_id=tmdb_id, tvdb_id=None, title=title, year=year,
                template_id=template_id, preset_id=preset_id, auto_send=auto_send, library_id=None,
                candidates=fallback_candidates, initial_delay=0,
            )
            return
        logger.error(f"[RADARR_WEBHOOK] Could not find movie in Plex after retries: {title} (TMDb ID: {tmdb_id})")
        return

    rating_key, library_id = result

    # Check if item has ignore labels
    if library_id and _should_skip_webhook(rating_key, library_id, is_tv=False):
        logger.info(f"[RADARR_WEBHOOK] Skipping poster generation for {title} - has webhook ignore label")
        return

    # Now process the poster generation
    process_webhook_poster_generation(
        rating_key=rating_key,
        template_id=template_id,
        preset_id=preset_id,
        auto_send=auto_send,
        auto_labels=auto_labels,
        library_id=library_id,
        is_tv=False
    )


def process_sonarr_webhook_with_retry(
    tvdb_id: int,
    title: str,
    year: Optional[int],
    template_id: str,
    preset_id: str,
    auto_send: bool,
    auto_labels: List[str],
    include_seasons: bool,
    affected_seasons: Optional[List[int]] = None,
    library_id: Optional[str] = None,
    fallback_candidates: Optional[List[tuple]] = None,
):
    """
    Background task for Sonarr webhooks that waits for Plex import, then generates poster.

    `library_id` (from the webhook URL's own optional query param -- see sonarr_webhook())
    scopes find_plex_item_with_retry()'s search to one specific Plex library instead of
    searching every TV library and using whichever has a match first, which is ambiguous
    whenever the same show exists in more than one library.
    """
    logger.info(f"[SONARR_WEBHOOK] Starting delayed processing for: {title} ({year}) - TVDb ID: {tvdb_id}, affected_seasons: {affected_seasons}")

    # Find TV show with retry logic - returns (rating_key, library_id) tuple
    result = find_plex_item_with_retry(
        find_func=find_plex_show_by_tvdb_id,
        external_id=tvdb_id,
        item_type="TV show",
        library_id=library_id,
        initial_delay=30,
        max_retries=5,
        retry_delay=15
    )

    if not result:
        if fallback_candidates:
            logger.info(f"[SONARR_WEBHOOK] {title} not on Plex -- trying the group's other libraries")
            process_media_server_webhook_with_retry(
                server_id=None, media_type="tv", tmdb_id=None, tvdb_id=tvdb_id, title=title, year=year,
                template_id=template_id, preset_id=preset_id, auto_send=auto_send, library_id=None,
                include_seasons=include_seasons, affected_seasons=affected_seasons,
                candidates=fallback_candidates, initial_delay=0,
            )
            return
        logger.error(f"[SONARR_WEBHOOK] Could not find TV show in Plex after retries: {title} (TVDb ID: {tvdb_id})")
        return

    rating_key, library_id = result

    # Check if item has ignore labels
    if library_id and _should_skip_webhook(rating_key, library_id, is_tv=True):
        logger.info(f"[SONARR_WEBHOOK] Skipping poster generation for {title} - has webhook ignore label")
        return

    # Check if this is a NEW show (not in cache) - if so, generate series poster too
    is_new_show = False
    if library_id:
        try:
            cached_shows = db.get_cached_tv_shows(library_id=library_id)
            # Check if this show exists in cache
            show_in_cache = any(show.get("rating_key") == rating_key for show in cached_shows)
            is_new_show = not show_in_cache
            if is_new_show:
                logger.info(f"[SONARR_WEBHOOK] Detected NEW show - will generate series poster + season posters")
        except Exception as e:
            logger.warning(f"[SONARR_WEBHOOK] Could not check cache for new show detection: {e}")

    # If it's a new show and include_seasons is True, generate series poster first
    if is_new_show and include_seasons:
        logger.info(f"[SONARR_WEBHOOK] Generating series poster for NEW show: {title}")
        process_webhook_poster_generation(
            rating_key=rating_key,
            template_id=template_id,
            preset_id=preset_id,
            auto_send=auto_send,
            auto_labels=auto_labels,
            library_id=library_id,
            is_tv=True,
            include_seasons=False,  # Series poster only
            affected_seasons=None
        )

    # Now process the poster generation (season posters if include_seasons=True)
    process_webhook_poster_generation(
        rating_key=rating_key,
        template_id=template_id,
        preset_id=preset_id,
        auto_send=auto_send,
        auto_labels=auto_labels,
        library_id=library_id,
        is_tv=True,
        include_seasons=include_seasons,
        affected_seasons=affected_seasons
    )


def process_media_server_webhook_with_retry(
    server_id: Optional[str],
    media_type: str,  # "movie" | "tv"
    tmdb_id: Optional[int],
    tvdb_id: Optional[int],
    title: str,
    year: Optional[int],
    template_id: str,
    preset_id: str,
    auto_send: bool,
    library_id: Optional[str],
    include_seasons: bool = False,
    affected_seasons: Optional[List[int]] = None,
    candidates: Optional[List[tuple]] = None,
    initial_delay: int = 30,
):
    """Phase 8b -- non-Plex counterpart to process_radarr_webhook_with_retry()/
    process_sonarr_webhook_with_retry() above, for a webhook URL that
    specified a non-Plex `server_id` (see radarr_webhook()/sonarr_webhook()'s
    own `server_id` query param). Resolves the item on that SPECIFIC server
    (`library_id` is REQUIRED, not optional -- see
    find_media_server_item_by_external_id()'s own docstring for why there's
    no whole-server-search equivalent to fall back to), pre-seeds a real
    cache row for it, then hands off to the exact same
    process_webhook_poster_generation() the Plex wrappers already use, just
    with `server_id` passed through so it routes the render through
    sync_render_to_linked_servers() (Quirk #106/#110/#132) instead of a
    direct Plex POST.

    Deliberately ONE function covering both media types (matching
    process_webhook_poster_generation()'s own `is_tv`-branching shape),
    not two near-duplicate functions the way the two Plex wrappers are
    split -- the one genuinely different TV-only step (new-show detection,
    a second series-poster-first call, mirroring
    process_sonarr_webhook_with_retry()'s own logic exactly) is the only
    real branch below; everything else is identical for movie/TV.

    No label-based ignore-library check (_should_skip_webhook(), Plex-only --
    JellyfinClient.remove_label()/add_label() are deliberate no-ops per
    Quirk #59, so there's no label mechanism to key a skip off of for a
    non-Plex item yet)."""
    logger.info("[MEDIA_SERVER_WEBHOOK:%s] Starting delayed processing for: %s (%s) -- tmdb=%s tvdb=%s library=%s",
                server_id, title, year, tmdb_id, tvdb_id, library_id)

    # `candidates` (see _resolve_webhook_target()): the URL named no server
    # and Plex isn't configured, so search every Jellyfin/Emby library in the
    # user's Library Groups, in order, and use whichever has the item.
    found_server = {"id": server_id}

    def _find_func(_external_id_unused, lib_id):
        # find_plex_item_with_retry() calls find_func(external_id, library_id)
        # -- tmdb_id/tvdb_id are already bound via closure above, so the first
        # positional arg here is intentionally unused.
        if candidates:
            hit = _find_on_candidates(candidates, tmdb_id, tvdb_id, media_type)
            if hit:
                found_server["id"] = hit[2]
                return (hit[0], hit[1])
            return None
        return find_media_server_item_by_external_id(server_id, tmdb_id, tvdb_id, media_type, lib_id)

    result = find_plex_item_with_retry(
        find_func=_find_func,
        external_id=(tvdb_id if media_type == "tv" else tmdb_id),
        item_type=f"{media_type} (server={server_id or 'group libraries'})",
        library_id=library_id,
        initial_delay=initial_delay,
        max_retries=5,
        retry_delay=15,
    )

    if not result:
        logger.error("[MEDIA_SERVER_WEBHOOK:%s] Could not find %s after retries: %s (tmdb=%s tvdb=%s)",
                      server_id, media_type, title, tmdb_id, tvdb_id)
        return

    item_id, library_id = result
    server_id = found_server["id"]

    # New-show detection must happen BEFORE the cache pre-seed below, or
    # every show would look "already cached" the instant it's seeded.
    is_new_show = False
    if media_type == "tv":
        try:
            cached_shows = db.get_cached_tv_shows(library_id=library_id)
            show_in_cache = any(show.get("rating_key") == item_id for show in cached_shows)
            is_new_show = not show_in_cache
            if is_new_show:
                logger.info("[MEDIA_SERVER_WEBHOOK:%s] Detected NEW show -- will generate series poster + season posters", server_id)
        except Exception as e:
            logger.warning("[MEDIA_SERVER_WEBHOOK:%s] Could not check cache for new show detection: %s", server_id, e)

    # Pre-seed a real cache row -- title/year/tmdb_id/tvdb_id are already
    # known from the webhook payload, so no extra metadata fetch is needed.
    # This is what lets _process_single_movie()/_process_single_tv_show()'s
    # own db.get_server_id_for_rating_key() check (Quirk #106) correctly
    # recognize this item as belonging to `server_id` instead of silently
    # defaulting to 'plex-1' for a rating_key it's never seen before. Uses
    # the genuinely single-item-safe writers (Quirk #132's new upsert_media_
    # server_*_single()) -- NEVER the bulk upsert_media_server_movies()/
    # _tv_shows(), which would treat every OTHER already-cached item in this
    # (server_id, library_id) pair as orphaned and delete it.
    try:
        seed = {"rating_key": item_id, "title": title, "year": year, "tmdb_id": tmdb_id, "tvdb_id": tvdb_id}
        if media_type == "tv":
            db.upsert_media_server_tv_show_single(server_id, library_id, seed)
        else:
            db.upsert_media_server_movie_single(server_id, library_id, seed)
    except Exception as e:
        logger.warning("[MEDIA_SERVER_WEBHOOK:%s] Failed to pre-seed cache for %s [%s]: %s -- continuing anyway", server_id, item_id, title, e)

    if media_type == "tv":
        if is_new_show and include_seasons:
            logger.info("[MEDIA_SERVER_WEBHOOK:%s] Generating series poster for NEW show: %s", server_id, title)
            process_webhook_poster_generation(
                rating_key=item_id,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=[],
                library_id=library_id,
                is_tv=True,
                include_seasons=False,  # Series poster only
                affected_seasons=None,
                server_id=server_id,
            )
        process_webhook_poster_generation(
            rating_key=item_id,
            template_id=template_id,
            preset_id=preset_id,
            auto_send=auto_send,
            auto_labels=[],
            library_id=library_id,
            is_tv=True,
            include_seasons=include_seasons,
            affected_seasons=affected_seasons,
            server_id=server_id,
        )
    else:
        process_webhook_poster_generation(
            rating_key=item_id,
            template_id=template_id,
            preset_id=preset_id,
            auto_send=auto_send,
            auto_labels=[],
            library_id=library_id,
            is_tv=False,
            server_id=server_id,
        )


def _sync_poster_to_other_servers(tmdb_id: Optional[int], media_type: str, title_hint: str = "?", library_id: Optional[str] = None, season_index: Optional[int] = None, tvdb_id: Optional[int] = None, template_id: Optional[str] = None, preset_id: Optional[str] = None, year: Optional[int] = None, season_title: Optional[str] = None) -> List[str]:
    """Phase 6 (webhooks) -- after a webhook-triggered Plex render+send
    succeeds, check whether the same title also exists on any OTHER server
    that's actually linked to this Plex library via a Library Group
    (Quirk #62/#64) and upload the same just-rendered poster there too.
    This is the piece of "real, automated content on Jellyfin" that was
    still missing after Quirks #65-70 (those only covered manually browsing/
    editing an already-scanned item) -- without this, Jellyfin never got a
    poster from a Radarr/Sonarr-triggered generation at all.

    Group-scoped, not "every enabled server" (fixed in Quirk #95 -- the
    original v1.6.116 version of this function looped get_enabled_clients()
    unconditionally, which meant a webhook could push a poster to a
    Jellyfin/Emby server that was never linked to this Plex library at all,
    purely because it happened to also have an item with a matching
    tmdb_id -- e.g. a user's personal Jellyfin server with an unrelated
    library. `library_id` (the Plex library the item was ACTUALLY found in
    by this webhook, resolved by find_plex_movie_by_tmdb_id()/
    find_plex_show_by_tvdb_id() before this is called -- not necessarily the
    same as an explicit ?library_id= query param, since that param is only
    a search-scoping hint) is used to look up that library's own
    LibraryGroup and restrict the sync to just its other, non-Plex members.
    A library with no group (or a group with no other members) correctly
    syncs to nothing -- there's no "linked" server to sync to, and this
    function must never guess.

    Deliberately runs strictly AFTER the existing Plex webhook path has
    already fully succeeded, reads the render bytes that path *just* wrote
    (save_render_cache_by_tmdb(), called unconditionally on every successful
    send since Quirk #41) directly off disk rather than through
    load_render_cache_by_tmdb() -- that wrapper is gated by
    reuseCachedPosterDays and a tmdb_last_seen "recently scan-confirmed"
    check (Quirk #41's own design, meant for a different problem: reusing an
    OLD render across a rating_key rotation), which would very often return
    None here even though the file was written moments ago in this exact
    request, since a webhook path never touches tmdb_last_seen (only scans
    do). Best-effort and fully isolated: any failure here is logged and
    swallowed, never raised -- this must never be able to affect the Plex
    path's own already-committed success.

    `season_index` (Quirk #100): when given, reads the per-season cache file
    save_render_cache_by_tmdb() also writes (_render_cache_path_by_tmdb()
    already supports this) and, on each linked server, resolves the SERIES
    item first (as always) then that specific season via
    find_season_by_index() -- a server where the season can't be resolved is
    skipped for this call, never a hard failure. None (the default) is the
    original series-only behavior, unchanged.

    `tvdb_id` (Quirk #111): REQUIRED for a TV item to ever resolve on any
    target server -- both PlexClient.find_item_by_external_id() and
    JellyfinClient.find_item_by_external_id() only match media_type == "tv"
    via a tvdb://<id> (Plex) / ProviderIds.Tvdb (Jellyfin) lookup, never
    tmdb_id, matching this app's pre-existing Quirk #25 webhook-matching
    convention. Before this fix, every call site here hardcoded the third
    positional arg to None, meaning find_item_by_external_id() returned None
    immediately (no network call at all) for every TV sync attempt, for the
    entire lifetime of this function -- TV webhook cross-server sync never
    actually worked. Movies are unaffected (movie matching is tmdb_id-based,
    tvdb_id is simply unused/None for that branch).

    `template_id`/`preset_id` (Quirk #112): passed through purely so a
    successful sync can write a poster_history row -- this function's own
    upload used to be completely invisible in History, the same gap
    media_server_send.py's sync_render_to_linked_servers() had (that
    function's callers in batch.py were fixed first). `year` is left `None`
    for the history row here (this function only ever has `title_hint`, a
    plain display string, not a split title/year the way batch.py's callers
    do) -- acceptable, since the row still identifies the right item/server/
    template/preset, which is what actually matters for "did this sync
    happen." Update (Quirk #151): callers now pass `year` and, for a
    season, `season_title`, so the row reads "Show - Season 1 (2015)" like
    the matching Plex row instead of the bare show name with no year.

    Returns the list of server_ids actually synced to (empty list for a
    no-op/every-failure run) -- added so the webhook's own per-item Discord/
    Apprise notification (built right after this returns, in
    process_webhook_poster_generation()) can say "Also synced to: Jellyfin"
    instead of staying completely silent about a sync that happened in the
    same request. Previously this function was pure fire-and-forget with no
    return value at all."""
    synced_server_ids: List[str] = []
    if not tmdb_id:
        return synced_server_ids
    try:
        from ..config import _render_cache_path_by_tmdb, get_library_group_members
        from ..media_server import get_enabled_clients, PlexClient, ImageType

        find_media_type = "tv" if media_type == "tv-show" else "movie"

        if not library_id:
            logger.debug("[WEBHOOK_SYNC] No library_id resolved for tmdb_id=%s [%s] -- cannot determine linked servers, skipping cross-server sync", tmdb_id, title_hint)
            return synced_server_ids
        members = get_library_group_members("plex-1", str(library_id), find_media_type)
        # Keep each member's own library_id (not just server_id) -- see the
        # matching fix/comment in media_server_send.py's
        # sync_render_to_linked_servers() for the real bug this closes
        # (an unscoped find_item_by_external_id() can resolve to the wrong
        # same-tmdb_id item when it exists in more than one library on the
        # same server).
        allowed_servers = {sid: lid for sid, lid in (members or []) if sid != "plex-1"}
        if not allowed_servers:
            logger.debug("[WEBHOOK_SYNC] Plex library %s has no linked Library Group members -- skipping cross-server sync for tmdb_id=%s [%s]", library_id, tmdb_id, title_hint)
            return synced_server_ids

        cache_path = _render_cache_path_by_tmdb(media_type, tmdb_id, season_index)
        if not cache_path.exists():
            return synced_server_ids
        image_bytes = cache_path.read_bytes()

        for client in get_enabled_clients():
            if isinstance(client, PlexClient) or client.server_id not in allowed_servers:
                continue
            try:
                series_item_id = client.find_item_by_external_id(tmdb_id, tvdb_id, find_media_type, library_id=allowed_servers.get(client.server_id))
                if not series_item_id:
                    # Usually the server hasn't imported the file yet. Its next
                    # library scan delivers this cached render instead
                    # (auto_generate.process_new_media_server_content).
                    logger.info("[WEBHOOK_SYNC:%s] %s isn't on this server yet -- the poster will be sent after its next library scan", client.server_id, title_hint)
                    continue
                item_id = series_item_id if season_index is None else client.find_season_by_index(series_item_id, season_index)
                if not item_id:
                    logger.info("[WEBHOOK_SYNC:%s] %s season %s isn't on this server yet -- skipped", client.server_id, title_hint, season_index)
                    continue
                client.upload_image(item_id, ImageType.POSTER, image_bytes, "image/jpeg")
                logger.info("[WEBHOOK_SYNC:%s] Synced poster for tmdb_id=%s [%s]%s -> item_id=%s", client.server_id, tmdb_id, title_hint,
                            f" season {season_index}" if season_index is not None else "", item_id)
                # Keep the local disk cache/DB row in sync too, so the merged
                # grid (Quirk #65/#67) reflects this without needing a rescan --
                # mirrors media_server_send.py's identical post-upload pattern.
                try:
                    from .movies import _save_poster_cache, _poster_cache_url
                    saved = _save_poster_cache(item_id, image_bytes, "image/jpeg")
                    if saved:
                        cache.update_poster(item_id, _poster_cache_url(item_id, saved))
                except Exception as cache_err:
                    logger.debug("[WEBHOOK_SYNC:%s] Failed to update local cache for item_id=%s: %s", client.server_id, item_id, cache_err)
                try:
                    history_title = title_hint
                    if season_index is not None:
                        _season_label = season_title or ("Specials" if season_index == 0 else f"Season {season_index}")
                        history_title = f"{title_hint} - {_season_label}"
                    db.record_poster_history(
                        rating_key=item_id,
                        library_id=str(library_id or ""),
                        title=history_title,
                        year=year,
                        template_id=template_id,
                        preset_id=preset_id,
                        action="sent_to_media_server",
                        source="webhook",
                        poster_data=image_bytes,
                        server_id=client.server_id,
                    )
                except Exception as history_err:
                    logger.debug("[WEBHOOK_SYNC:%s] Failed to record history for item_id=%s: %s", client.server_id, item_id, history_err)
                synced_server_ids.append(client.server_id)
            except Exception as e:
                logger.warning("[WEBHOOK_SYNC:%s] Failed to sync poster for tmdb_id=%s [%s]: %s", client.server_id, tmdb_id, title_hint, e)
    except Exception as e:
        logger.debug("[WEBHOOK_SYNC] _sync_poster_to_other_servers failed for tmdb_id=%s [%s]: %s", tmdb_id, title_hint, e)
    return synced_server_ids


def process_webhook_poster_generation(
    rating_key: str,
    template_id: str,
    preset_id: str,
    auto_send: bool,
    auto_labels: List[str],
    library_id: Optional[str],
    is_tv: bool = False,
    include_seasons: bool = False,
    affected_seasons: Optional[List[int]] = None,
    server_id: str = "plex-1",
    source: str = "webhook",
):
    """
    Background task to generate and send poster to Plex (or, since Phase 8b,
    to a specific Jellyfin/Emby server instead -- see `server_id`).
    Also reused by auto_generate.process_new_media_server_content() for
    scan-discovered Jellyfin/Emby items, which passes source="auto_generate"
    so History/notifications label them correctly.
    This runs asynchronously after the webhook returns a response.

    Args:
        affected_seasons: For TV shows, only process these specific seasons.
                         If None or empty, process all seasons (for new series).
        server_id: Which configured server `rating_key` actually lives on and
                   should be rendered/sent to. Defaults to "plex-1" -- every
                   call site before Phase 8b implicitly assumed this, so the
                   default reproduces that exact behavior byte-for-byte.
                   `rating_key` for a non-"plex-1" server is NOT a Plex
                   rating_key -- it's whatever find_media_server_item_by_
                   external_id() resolved it to on that server. Several
                   Plex-only steps below (the cache-resend fast path, direct
                   Plex label add/remove) are skipped entirely for a non-Plex
                   server_id -- there is no equivalent "resend" fast path for
                   Jellyfin/Emby yet (Quirk #59: no label mechanism to key a
                   resend-skip off of), and _process_single_movie()/
                   _process_single_tv_show()'s own is_plex_item gating
                   (Quirk #106) already correctly routes a non-Plex item
                   through sync_render_to_linked_servers() instead of a
                   direct Plex POST.
    """
    _wh_start = time.time()
    # Best-effort display title for log readability — a cheap local DB cache lookup,
    # never a network call. Upgraded to the real title below once the batch functions
    # return one, but this covers every log line before that point too.
    title_hint = rating_key
    try:
        _cached_title, _ = db.get_title_for_rating_key(rating_key)
        if _cached_title:
            title_hint = _cached_title
    except Exception:
        pass
    try:
        # ------------------------------------------------------------------
        # Resend cached poster if the setting is "resend" and a cached
        # render exists for this item (i.e. it was previously sent by Simposter).
        # Plex-only -- it POSTs directly to Plex's own .../posters endpoint and
        # does Plex label add/remove, neither of which has a non-Plex
        # equivalent built yet. A non-Plex server_id falls straight through
        # to full generation below, same as if this setting were off.
        # ------------------------------------------------------------------
        if auto_send and server_id == "plex-1":
            try:
                _ui = db.get_ui_settings()
                if _ui.get("automation", {}).get("existingContentMode") == "resend":
                    cached = load_render_cache(rating_key)
                    if cached:
                        plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
                        plex_session.post(
                            plex_url,
                            headers={**plex_headers(), "Content-Type": "image/jpeg"},
                            data=cached,
                            timeout=20,
                        ).raise_for_status()
                        logger.info("[WEBHOOK] Resent cached poster for %s [%s] (existingContentMode=resend) in %.1fs",
                                    rating_key, title_hint, time.time() - _wh_start)
                        _title, _year = db.get_title_for_rating_key(rating_key)
                        try:
                            db.record_poster_history(
                                rating_key=rating_key,
                                library_id=str(library_id or ""),
                                title=_title,
                                year=_year,
                                template_id=template_id,
                                preset_id=preset_id,
                                action="resent_to_plex",
                                source=source,
                                poster_data=cached,
                            )
                        except Exception:
                            pass
                        # Remove configured labels after resend (same as full pipeline)
                        try:
                            resend_labels = list(auto_labels)
                            if library_id:
                                lib_default_labels = _get_default_remove_labels(str(library_id))
                                if lib_default_labels:
                                    resend_labels = list({*resend_labels, *lib_default_labels})
                            if resend_labels:
                                logger.info("[WEBHOOK] Removing labels %s from %s [%s] (resend)", resend_labels, rating_key, title_hint)
                                removed = []
                                for lbl in resend_labels:
                                    plex_remove_label(rating_key, lbl)
                                    logger.info("[WEBHOOK] Removed label '%s' from %s [%s]", lbl, rating_key, title_hint)
                                    removed.append(lbl.lower())
                                if removed:
                                    current = db.get_movie_labels(rating_key)
                                    updated = [l for l in current if l.lower() not in removed]
                                    db.update_movie_labels(rating_key, updated)
                        except Exception as lbl_err:
                            logger.warning("[WEBHOOK] Label removal after resend failed for %s [%s]: %s", rating_key, title_hint, lbl_err)
                        # Add tracking label if configured (opposite direction from the
                        # removal above — see get_label_to_add()'s docstring)
                        try:
                            label_to_add = get_label_to_add()
                            if label_to_add:
                                plex_add_label(rating_key, label_to_add, content_type="1")
                                logger.info("[WEBHOOK] Added label '%s' to %s [%s] (resend)", label_to_add, rating_key, title_hint)
                                current = db.get_movie_labels(rating_key)
                                if label_to_add.lower() not in [l.lower() for l in current]:
                                    db.update_movie_labels(rating_key, current + [label_to_add])
                        except Exception as lbl_err:
                            logger.warning("[WEBHOOK] Label add after resend failed for %s [%s]: %s", rating_key, title_hint, lbl_err)
                        return
            except Exception as resend_err:
                logger.warning("[WEBHOOK] Cache resend check failed for %s [%s]: %s — falling through to generation", rating_key, title_hint, resend_err)

        from .batch import _process_single_movie, _process_single_tv_show

        # Load preset options
        presets_data = load_presets()
        template_presets = presets_data.get(template_id, {}).get("presets", [])
        preset = next((p for p in template_presets if p.get("id") == preset_id), None)

        if not preset:
            logger.error(f"[WEBHOOK] Preset '{preset_id}' not found for template '{template_id}'")
            return

        # Merge global auto_labels with per-library default labels to remove
        if library_id:
            lib_default_labels = _get_default_remove_labels(library_id)
            if lib_default_labels:
                auto_labels = list({*auto_labels, *lib_default_labels})
                logger.debug("[WEBHOOK] Labels to remove for library %s: %s", library_id, auto_labels)

        # Read sendLogosToPlex global setting
        send_logos = False
        try:
            from .. import database as _db
            _ui = _db.get_ui_settings()
            send_logos = bool(_ui.get("plex", {}).get("sendLogosToPlex", False))
        except Exception:
            pass

        options = preset.get("options", {})

        # Non-Plex (Jellyfin/Emby) target: never a direct Plex send -- route
        # through _process_single_movie()/_process_single_tv_show()'s existing
        # is_plex_item-gated sync_render_to_linked_servers() path instead
        # (Quirk #106/#110), the same mechanism the non-Plex half of Batch
        # Edit's own "send to" picker already uses (Quirk #96). source_server_id
        # (Quirk #132) is what lets that sync correctly resolve this item's own
        # Library Group when `library_id` is itself a non-Plex-anchored library.
        is_plex_target = server_id == "plex-1"

        # For a non-Plex origin, deliver to the origin server AND every other
        # member of its Library Group (Plex included) in one go, via the
        # batch pipeline's sync_render_to_linked_servers() -- which already
        # resolves the group from any origin server (Quirk #132) and each
        # member's own copy of the item by tmdb/tvdb id (members that don't
        # have the item are skipped). Previously only the origin server got
        # the poster, so a 3+-server group's other members were never
        # updated by a Jellyfin/Emby-origin webhook or auto-generate. The
        # Plex-origin path keeps using _sync_poster_to_other_servers() below.
        nonplex_targets: List[str] = []
        if auto_send and not is_plex_target:
            nonplex_targets = [server_id]
            if library_id:
                try:
                    from ..config import get_library_group_members
                    for member_sid, _member_lib in get_library_group_members(server_id, str(library_id), "tv" if is_tv else "movie") or []:
                        if member_sid and member_sid not in nonplex_targets:
                            nonplex_targets.append(member_sid)
                except Exception as grp_err:
                    logger.debug("[WEBHOOK] Couldn't resolve library group for %s/%s: %s", server_id, library_id, grp_err)

        if is_tv:
            # Create TV show batch request
            request = TVShowBatchRequest(
                rating_keys=[rating_key],
                template_id=template_id,
                preset_id=preset_id,
                options=options,
                send_to_plex=auto_send and is_plex_target,
                save_locally=False,
                labels=auto_labels if is_plex_target else [],
                library_id=library_id,
                source_server_id=server_id,
                targets=nonplex_targets,
                include_seasons=include_seasons,
                fallbackPosterAction=options.get("fallbackPosterAction"),
                fallbackPosterTemplate=options.get("fallbackPosterTemplate"),
                fallbackPosterPreset=options.get("fallbackPosterPreset"),
                send_logos_to_plex=send_logos,
            )

            # Get base settings from preset
            base_options = dict(options)
            base_poster_filter = base_options.get("poster_filter", "all")
            base_logo_preference = base_options.get("logo_preference") or base_options.get("logo_mode", "white")
            base_logo_mode = base_options.get("logo_mode", "white")
            white_logo_fallback = base_options.get("fallbackLogoAction", "use_next")
            language_pref = base_options.get("language_preference", "en")

            # Extract season_options from preset if available (matching batch.py behavior)
            season_opts = preset.get("season_options", {})
            if season_opts:
                season_options = {**season_opts}
                season_poster_filter = season_options.get("poster_filter", base_poster_filter)
                logger.debug("[WEBHOOK] Extracted season_options with poster_filter='%s'", season_poster_filter)
            else:
                season_options = dict(base_options)
                season_poster_filter = base_poster_filter

            # Process the TV show
            result = _process_single_tv_show(
                idx=0,
                rating_key=rating_key,
                req=request,
                base_options=base_options,
                base_poster_filter=base_poster_filter,
                base_logo_preference=base_logo_preference,
                base_logo_mode=base_logo_mode,
                white_logo_fallback=white_logo_fallback,
                language_pref=language_pref,
                presets_data=presets_data,
                season_poster_filter=season_poster_filter,
                season_options=season_options,
                source=source,
                affected_seasons=affected_seasons
            )

            # Check result status - batch functions return "ok" on success
            result_status = result.get("status")
            if result_status == "ok":
                show_title = result.get("show_title") or title_hint
                logger.info("[WEBHOOK] Successfully processed TV show %s [%s] in %.1fs", rating_key, show_title, time.time() - _wh_start)
                # Enqueue for retry if ideal template conditions weren't met
                try:
                    _ui = db.get_ui_settings() or {}
                    if _ui.get("automation", {}).get("retryUntilTemplateMet", False):
                        sub_results = result.get("results", [])
                        needs_retry_items = [r for r in sub_results if r.get("needs_retry")]
                        if needs_retry_items:
                            db.add_to_retry_queue(
                                rating_key=rating_key,
                                media_type="tv",
                                library_id=library_id,
                                template_id=template_id,
                                preset_id=preset_id,
                                title=show_title,
                                reason=needs_retry_items[0].get("retry_reason", "unknown"),
                            )
                            logger.info("[WEBHOOK] Queued TV show %s for retry", show_title)
                        else:
                            db.remove_from_retry_queue(rating_key)
                except Exception as q_err:
                    logger.debug("[WEBHOOK] TV retry queue update failed for %s [%s]: %s", rating_key, show_title, q_err)
                # Update cache so the show appears in library view. Plex-only --
                # it re-fetches metadata live from Plex using `rating_key` as a
                # real Plex rating_key, which a non-Plex server_id's rating_key
                # isn't. For a non-Plex target, process_media_server_webhook_
                # with_retry() already seeded a correct cache row (title/year/
                # tmdb_id/tvdb_id straight from the webhook payload) BEFORE this
                # function ever ran, so there's nothing new to refresh here.
                if is_plex_target:
                    try:
                        logger.info("[WEBHOOK] Updating TV cache for %s [%s] (library_id=%s)", rating_key, show_title, library_id)
                        _update_tv_cache(rating_key, library_id)
                    except Exception as cache_err:
                        logger.warning("[WEBHOOK] Failed to update TV cache for %s [%s]: %s", rating_key, show_title, cache_err, exc_info=True)
                sub_results = result.get("results", [])
                # Phase 6c/Quirk #100 -- sync EVERY successfully-sent sub-result
                # (the series AND any season) to any other enabled server
                # (Jellyfin/Emby) that also has this show, closing the deferred
                # half of Quirk #71 (which was Radarr/movies only). Season-level
                # sync IS possible now (Quirk #100 -- JellyfinClient genuinely
                # has season-item resolution, contrary to what every prior
                # Quirk here assumed without ever checking against a real
                # server) -- each sub-result's own `season_index` (None for the
                # series, set explicitly by batch.py's per-season result dict
                # otherwise) is passed straight through, so a season sync that
                # fails to resolve on one server is skipped for just that
                # server/season, never blocking the rest.
                # Fully additive/best-effort, see _sync_poster_to_other_servers()'s
                # own docstring for why this can never affect the Plex result above.
                # Plex-origin only for now (is_plex_target) -- _sync_poster_to_
                # other_servers() has the IDENTICAL get_library_group_members()
                # "plex-1" hardcode Quirk #132 just fixed in sync_render_to_
                # linked_servers(), never fixed here too. A non-Plex origin's
                # single resolved target already got the render directly via
                # this request's own targets=[server_id] (Quirk #132/Phase 8b)
                # -- syncing from a non-Plex origin to OTHER members of the same
                # Library Group (a 3+-server group) is real, deferred follow-up
                # work, not yet needed for the common 2-member case.
                _tv_synced_server_ids: List[str] = []
                if auto_send and is_plex_target:
                    try:
                        _sync_cached = db.get_cached_tv_shows()
                        _sync_info = next((s for s in _sync_cached if s.get("key") == rating_key or s.get("rating_key") == rating_key), None)
                        _sync_tmdb_id = _sync_info.get("tmdb_id") if _sync_info else None
                        # tvdb_id is REQUIRED for find_item_by_external_id() to ever
                        # resolve a TV item on any target server (Quirk #111) -- this
                        # call site was missed when that fix landed elsewhere, so
                        # Sonarr-webhook-triggered TV sync still silently never worked.
                        _sync_tvdb_id = _sync_info.get("tvdb_id") if _sync_info else None
                        for _r in sub_results:
                            if _r.get("status") != "ok":
                                continue
                            _synced = _sync_poster_to_other_servers(
                                _sync_tmdb_id, "tv-show", show_title, library_id=library_id,
                                season_index=_r.get("season_index"), tvdb_id=_sync_tvdb_id,
                                template_id=template_id, preset_id=preset_id,
                                year=_sync_info.get("year") if _sync_info else None,
                                season_title=_r.get("season") if _r.get("season_index") is not None else None,
                            )
                            for _sid in _synced:
                                if _sid not in _tv_synced_server_ids:
                                    _tv_synced_server_ids.append(_sid)
                    except Exception as sync_err:
                        logger.debug("[WEBHOOK] TV cross-server sync failed for %s [%s]: %s", rating_key, show_title, sync_err)
                # Only notify if at least one poster was actually created/sent.
                # Sub-results with status != "ok" mean the season was skipped (already had a poster,
                # no poster found, etc.) — e.g. a Sonarr episode webhook for S01E03 when S01
                # already has a poster will return "ok" at the show level but all sub-results skipped.
                posters_created = [r for r in sub_results if r.get("status") == "ok"]
                if not posters_created:
                    logger.debug("[WEBHOOK] No new posters created for TV show %s [%s] — skipping notifications", rating_key, show_title)
                else:
                    _tv_notif_kwargs = dict(
                        title=result.get("show_title", "Unknown TV Show"),
                        template_id=template_id,
                        preset_id=preset_id,
                        library_id=library_id,
                        source=source,
                        action=("sent_to_plex" if is_plex_target else "sent_to_media_server") if auto_send else "saved",
                        server_id=server_id,
                        synced_server_ids=_tv_synced_server_ids,
                    )
                    try:
                        tv_poster_data = next((r.get("poster_data") for r in posters_created if r.get("poster_data")), None)
                        send_discord_notification(**_tv_notif_kwargs, poster_data=tv_poster_data)
                    except Exception as notif_err:
                        logger.debug(f"[WEBHOOK] Failed to send Discord notification: {notif_err}")
                    try:
                        send_apprise_notification(**_tv_notif_kwargs, poster_data=tv_poster_data)
                    except Exception as notif_err:
                        logger.debug(f"[WEBHOOK] Failed to send Apprise notification: {notif_err}")
            else:
                # Log full result for debugging
                logger.debug("[WEBHOOK] Result dict for %s [%s]: %s", rating_key, title_hint, result)
                error_msg = result.get('error') or result.get('message', 'Unknown error')
                logger.warning("[WEBHOOK] Unexpected result status for TV show %s [%s]: status=%s, error=%s", rating_key, title_hint, result_status, error_msg)

        else:
            # Create movie batch request
            request = MovieBatchRequest(
                rating_keys=[rating_key],
                template_id=template_id,
                preset_id=preset_id,
                options=options,
                send_to_plex=auto_send and is_plex_target,
                save_locally=False,
                labels=auto_labels if is_plex_target else [],
                library_id=library_id,
                source_server_id=server_id,
                targets=nonplex_targets,
                send_logos_to_plex=send_logos,
            )

            # Get base settings from preset
            base_options = dict(options)
            base_poster_filter = base_options.get("poster_filter", "all")
            base_logo_preference = base_options.get("logo_preference") or base_options.get("logo_mode", "white")
            base_logo_mode = base_options.get("logo_mode", "white")
            white_logo_fallback = base_options.get("fallbackLogoAction", "use_next")
            language_pref = base_options.get("language_preference", "en")

            # Process the movie
            result = _process_single_movie(
                idx=0,
                rating_key=rating_key,
                req=request,
                base_options=base_options,
                base_poster_filter=base_poster_filter,
                base_logo_preference=base_logo_preference,
                base_logo_mode=base_logo_mode,
                white_logo_fallback=white_logo_fallback,
                language_pref=language_pref,
                presets_data=presets_data,
                source=source
            )

            # Check result status - batch functions return "ok" on success
            result_status = result.get("status")
            if result_status == "ok":
                movie_title = result.get("title") or title_hint
                logger.info("[WEBHOOK] Successfully processed movie %s [%s] in %.1fs", rating_key, movie_title, time.time() - _wh_start)
                # Enqueue for retry if ideal template conditions weren't met
                try:
                    _ui = db.get_ui_settings() or {}
                    if _ui.get("automation", {}).get("retryUntilTemplateMet", False):
                        if result.get("needs_retry"):
                            db.add_to_retry_queue(
                                rating_key=rating_key,
                                media_type="movie",
                                library_id=library_id,
                                template_id=template_id,
                                preset_id=preset_id,
                                title=movie_title,
                                reason=result.get("retry_reason", "unknown"),
                            )
                            logger.info("[WEBHOOK] Queued %s for retry (reason=%s)", movie_title, result.get("retry_reason"))
                        else:
                            db.remove_from_retry_queue(rating_key)
                except Exception as q_err:
                    logger.debug("[WEBHOOK] Retry queue update failed for %s [%s]: %s", rating_key, movie_title, q_err)
                # Update cache so the movie appears in library view. Plex-only --
                # see the identical comment on the TV branch's _update_tv_cache()
                # call above for why a non-Plex server_id skips this (the cache
                # row was already correctly seeded before this function ran).
                if is_plex_target:
                    try:
                        logger.info("[WEBHOOK] Updating movie cache for %s [%s] (library_id=%s)", rating_key, movie_title, library_id)
                        _update_movie_cache(rating_key, library_id)
                    except Exception as cache_err:
                        logger.warning("[WEBHOOK] Failed to update movie cache for %s [%s]: %s", rating_key, movie_title, cache_err, exc_info=True)
                # Phase 6 (Quirk #71) -- sync the just-sent poster to any other
                # enabled server (Jellyfin/Emby) that also has this title.
                # Fully additive/best-effort, see _sync_poster_to_other_servers()'s
                # own docstring for why this can never affect the Plex result above.
                # _process_single_movie()'s result dict has no tmdb_id key, so this
                # resolves it the same way the notification block just below does
                # (a fresh cache lookup, now that _update_movie_cache() above has
                # just populated it) -- a small duplicated query, not worth
                # restructuring the existing notification code to share.
                # Plex-origin only for now -- see the identical is_plex_target
                # gate/comment on the TV branch's equivalent block above.
                _movie_synced_server_ids: List[str] = []
                if auto_send and is_plex_target:
                    try:
                        _sync_cached = db.get_cached_movies()
                        _sync_info = next((m for m in _sync_cached if m.get("key") == rating_key or m.get("rating_key") == rating_key), None)
                        _movie_synced_server_ids = _sync_poster_to_other_servers(_sync_info.get("tmdb_id") if _sync_info else None, "movie", movie_title, library_id=library_id, template_id=template_id, preset_id=preset_id, year=_sync_info.get("year") if _sync_info else None)
                    except Exception as sync_err:
                        logger.debug("[WEBHOOK] Cross-server poster sync failed for %s [%s]: %s", rating_key, movie_title, sync_err)
                # Send Discord notification (include poster image)
                try:
                    # Get movie title from cache if available
                    cached_movies = db.get_cached_movies()
                    movie_info = next((m for m in cached_movies if m.get("key") == rating_key or m.get("rating_key") == rating_key), None)
                    movie_title = movie_info.get("title") if movie_info else "Unknown Movie"
                    movie_year = movie_info.get("year") if movie_info else None
                    _movie_notif_kwargs = dict(
                        title=movie_title,
                        year=movie_year,
                        template_id=template_id,
                        preset_id=preset_id,
                        library_id=library_id,
                        source=source,
                        action=("sent_to_plex" if is_plex_target else "sent_to_media_server") if auto_send else "saved",
                        server_id=server_id,
                        synced_server_ids=_movie_synced_server_ids,
                    )
                    send_discord_notification(**_movie_notif_kwargs, poster_data=result.get("poster_data"))
                except Exception as notif_err:
                    logger.debug(f"[WEBHOOK] Failed to send Discord notification: {notif_err}")
                try:
                    send_apprise_notification(**_movie_notif_kwargs, poster_data=result.get("poster_data"))
                except Exception as notif_err:
                    logger.debug(f"[WEBHOOK] Failed to send Apprise notification: {notif_err}")
            else:
                # Log full result for debugging
                logger.debug("[WEBHOOK] Result dict for %s [%s]: %s", rating_key, title_hint, result)
                error_msg = result.get('error') or result.get('message', 'Unknown error')
                logger.warning("[WEBHOOK] Unexpected result status for movie %s [%s]: status=%s, error=%s", rating_key, title_hint, result_status, error_msg)

    except Exception as e:
        logger.error("[WEBHOOK] Error in background poster generation for %s [%s]: %s", rating_key, title_hint, e, exc_info=True)


# ============================================================================
# RADARR WEBHOOKS - Movie poster generation
# ============================================================================

@router.post("/webhook/radarr/{template_id}/{preset_id}", dependencies=[Depends(verify_webhook_secret)])
def radarr_webhook(
    template_id: str,
    preset_id: str,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    test: bool = Query(default=False),
    library_id: Optional[str] = Query(
        default=None,
        description="Optional Plex library section id to scope the TMDb-ID lookup to. "
                    "Omitted (the default) searches every movie library and uses whichever "
                    "one has a match first -- ambiguous if the same title exists in more "
                    "than one library. Generated by the Webhook URL Generator in Settings -> "
                    "Automation when a specific library is selected there. REQUIRED (not "
                    "optional) when `server_id` below names a non-Plex server.",
    ),
    server_id: Optional[str] = Query(
        default=None,
        description="Phase 8b: which configured media server (Settings -> Media Servers) "
                    "this webhook's content actually lives on. Omitted or 'plex-1' (the "
                    "default) reproduces the original Plex-only behavior exactly. Any other "
                    "value routes the lookup/render/send through that Jellyfin/Emby server "
                    "instead -- `library_id` above becomes required in that case, since "
                    "there's no 'search every library on this server' equivalent.",
    ),
    group_id: Optional[str] = Query(
        default=None,
        description="A Library Group id (Settings -> Libraries). The item is looked up "
                    "across the group's libraries and the poster is delivered to every "
                    "library in the group. Takes priority over library_id/server_id.",
    ),
    group: Optional[str] = Query(
        default=None,
        description="Same as group_id, but by the group's name (case-insensitive) -- "
                    "what the Webhook URL Generator produces, e.g. ?group=4k-Movies.",
    ),
):
    """
    Handle Radarr webhook events for movie imports/upgrades.

    Expected payload includes:
    - eventType: "MovieImport", "MovieDownload", etc.
    - movie: { tmdbId, title, year, ... }
    - movieFile: { path, releaseGroup, ... }

    Query params:
    - test: If true, performs a dry run with detailed logging but no poster generation
    - library_id: Optional -- scope the Plex lookup to one specific movie library
    - server_id: Optional (Phase 8b) -- target a specific non-Plex server instead of Plex
    """
    is_plex_webhook = not server_id or server_id == "plex-1"
    if not is_plex_webhook and not library_id:
        raise HTTPException(status_code=400, detail="library_id is required when server_id names a non-Plex server")
    # A URL that names no server (or one created before Plex was removed)
    # may still belong to a Jellyfin/Emby library -- see _resolve_webhook_target().
    _target_kind, _resolved_server, _resolved_library, webhook_candidates = _resolve_webhook_target(server_id, library_id, "movie", group_id or group)
    if _target_kind == "none":
        return {"status": "ignored", "reason": "No media server library found to look this item up on -- see the log for details"}
    plex_fallback = None
    if _target_kind == "media_server":
        is_plex_webhook = False
        server_id, library_id = _resolved_server, _resolved_library
    elif _target_kind == "plex" and (group_id or group):
        # Group webhook with a Plex member: look up in that Plex library, with
        # the group's Jellyfin/Emby libraries as the fallback.
        library_id = _resolved_library
        plex_fallback, webhook_candidates = webhook_candidates, None
    # Normalize template_id for backward compatibility
    template_id = _normalize_template_id(template_id)

    try:
        event_type = payload.get("eventType", "").lower()
        logger.info(f"[RADARR_WEBHOOK{'_TEST' if test else ''}] Received {event_type} event (template={template_id}, preset={preset_id})")

        # Only process relevant events
        if event_type not in ["movieimport", "moviedownload", "moviefileimported", "download", "grab"]:
            logger.debug(f"[RADARR_WEBHOOK] Skipping event type: {event_type}")
            return {"status": "ignored", "reason": f"Event type {event_type} not processed"}

        movie = payload.get("movie", {})
        tmdb_id = movie.get("tmdbId")
        title = movie.get("title", "Unknown")
        year = movie.get("year")

        if not tmdb_id:
            logger.warning("[RADARR_WEBHOOK] No TMDb ID found in payload")
            raise HTTPException(status_code=400, detail="Missing tmdbId in payload")

        logger.info(f"[RADARR_WEBHOOK{'_TEST' if test else ''}] Processing: {title} ({year}) - TMDb ID: {tmdb_id}")

        # Get automation settings
        auto_send = settings.WEBHOOK_AUTO_SEND
        auto_labels = [l.strip() for l in settings.WEBHOOK_AUTO_LABELS.split(",") if l.strip()] if settings.WEBHOOK_AUTO_LABELS else []

        if test:
            logger.info(f"[RADARR_WEBHOOK_TEST] === DRY RUN - NO POSTER GENERATION ===")
            logger.info(f"[RADARR_WEBHOOK_TEST] Movie: {title} ({year})")
            logger.info(f"[RADARR_WEBHOOK_TEST] TMDb ID: {tmdb_id}")
            logger.info(f"[RADARR_WEBHOOK_TEST] Template: {template_id}")
            logger.info(f"[RADARR_WEBHOOK_TEST] Preset: {preset_id}")
            logger.info(f"[RADARR_WEBHOOK_TEST] Auto-send to Plex: {auto_send}")
            logger.info(f"[RADARR_WEBHOOK_TEST] Labels to apply: {auto_labels}")

            # Try to find the movie on the target server (Plex, or a specific
            # Jellyfin/Emby server per Phase 8b's server_id param)
            if is_plex_webhook:
                result = find_plex_movie_by_tmdb_id(tmdb_id, library_id)
                if not result and plex_fallback:
                    _hit = _find_on_candidates(plex_fallback, tmdb_id, None, "movie")
                    if _hit:
                        result, server_id = (_hit[0], _hit[1]), _hit[2]
            else:
                if webhook_candidates:
                    _hit = _find_on_candidates(webhook_candidates, tmdb_id, None, "movie")
                    result = (_hit[0], _hit[1]) if _hit else None
                    if _hit:
                        server_id = _hit[2]
                else:
                    result = find_media_server_item_by_external_id(server_id, tmdb_id, None, "movie", library_id)
            if result:
                rating_key, lib_id = result
                logger.info(f"[RADARR_WEBHOOK_TEST] Found with rating_key: {rating_key}, library: {lib_id} (server={server_id or 'plex-1'})")
            else:
                rating_key = None
                lib_id = None
                logger.warning(f"[RADARR_WEBHOOK_TEST] Movie NOT found (server={server_id or 'plex-1'})")

            return {
                "status": "test_success",
                "movie": title,
                "year": year,
                "tmdb_id": tmdb_id,
                "rating_key": rating_key,
                "library_id": lib_id,
                "server_id": server_id or "plex-1",
                "template_id": template_id,
                "preset_id": preset_id,
                "auto_send": auto_send,
                "labels": auto_labels if is_plex_webhook else [],
                "message": "Test mode - no poster generated"
            }

        # Cooldown check - prevent duplicate poster generation
        cooldown_key = f"radarr:{tmdb_id}:{template_id}:{preset_id}"
        if _check_webhook_cooldown(cooldown_key):
            return {
                "status": "skipped",
                "reason": "Duplicate webhook within cooldown period",
                "event_type": event_type,
                "title": title,
                "tmdb_id": tmdb_id,
            }

        # Queue background task with delay/retry logic. This allows Plex (or,
        # per Phase 8b, the target Jellyfin/Emby server) time to import the
        # file before we try to find it.
        if is_plex_webhook:
            background_tasks.add_task(
                process_radarr_webhook_with_retry,
                tmdb_id=tmdb_id,
                title=title,
                year=year,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=auto_labels,
                library_id=library_id,
                fallback_candidates=plex_fallback,
            )
        else:
            background_tasks.add_task(
                process_media_server_webhook_with_retry,
                server_id=server_id,
                candidates=webhook_candidates,
                media_type="movie",
                tmdb_id=tmdb_id,
                tvdb_id=None,
                title=title,
                year=year,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                library_id=library_id,
            )

        return {
            "status": "queued",
            "event_type": event_type,
            "title": title,
            "tmdb_id": tmdb_id,
            "server_id": server_id or "plex-1",
            "template_id": template_id,
            "preset_id": preset_id,
            "auto_send": auto_send,
            "labels": auto_labels if is_plex_webhook else [],
            "message": "Poster generation queued (will wait for import)"
        }

    except Exception as e:
        logger.error(f"[RADARR_WEBHOOK] Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SONARR WEBHOOKS - TV show poster generation with season control
# ============================================================================

@router.post("/webhook/sonarr/{template_id}/{preset_id}", dependencies=[Depends(verify_webhook_secret)])
def sonarr_webhook(
    template_id: str,
    preset_id: str,
    background_tasks: BackgroundTasks,
    include_seasons: bool = Query(True, description="Generate posters for all seasons"),
    test: bool = Query(default=False),
    library_id: Optional[str] = Query(
        default=None,
        description="Optional Plex library section id to scope the TVDb-ID lookup to. "
                    "Omitted (the default) searches every TV library and uses whichever "
                    "one has a match first -- ambiguous if the same show exists in more "
                    "than one library. Generated by the Webhook URL Generator in Settings -> "
                    "Automation when a specific library is selected there. REQUIRED (not "
                    "optional) when `server_id` below names a non-Plex server.",
    ),
    server_id: Optional[str] = Query(
        default=None,
        description="Phase 8b: which configured media server (Settings -> Media Servers) "
                    "this webhook's content actually lives on. Omitted or 'plex-1' (the "
                    "default) reproduces the original Plex-only behavior exactly. Any other "
                    "value routes the lookup/render/send through that Jellyfin/Emby server "
                    "instead -- `library_id` above becomes required in that case.",
    ),
    group_id: Optional[str] = Query(
        default=None,
        description="A Library Group id (Settings -> Libraries). The item is looked up "
                    "across the group's libraries and the poster is delivered to every "
                    "library in the group. Takes priority over library_id/server_id.",
    ),
    group: Optional[str] = Query(
        default=None,
        description="Same as group_id, but by the group's name (case-insensitive) -- "
                    "what the Webhook URL Generator produces, e.g. ?group=4k-Movies.",
    ),
    payload: Dict[str, Any] = Body(...)
):
    """
    Handle Sonarr webhook events for TV show imports/upgrades.

    Expected payload includes:
    - eventType: "SeriesImport", "EpisodeFileImport", etc.
    - series: { tvdbId, title, year, ... }
    - episodes: [ { seasonNumber, episodeNumber, ... }, ... ]

    Query params:
    - include_seasons: If True, generate posters for all seasons. If False, only series poster.
    - test: If true, performs a dry run with detailed logging but no poster generation
    - library_id: Optional -- scope the Plex lookup to one specific TV library
    - server_id: Optional (Phase 8b) -- target a specific non-Plex server instead of Plex
    """
    is_plex_webhook = not server_id or server_id == "plex-1"
    if not is_plex_webhook and not library_id:
        raise HTTPException(status_code=400, detail="library_id is required when server_id names a non-Plex server")
    # A URL that names no server (or one created before Plex was removed)
    # may still belong to a Jellyfin/Emby library -- see _resolve_webhook_target().
    _target_kind, _resolved_server, _resolved_library, webhook_candidates = _resolve_webhook_target(server_id, library_id, "tv", group_id or group)
    if _target_kind == "none":
        return {"status": "ignored", "reason": "No media server library found to look this item up on -- see the log for details"}
    plex_fallback = None
    if _target_kind == "media_server":
        is_plex_webhook = False
        server_id, library_id = _resolved_server, _resolved_library
    elif _target_kind == "plex" and (group_id or group):
        # Group webhook with a Plex member: look up in that Plex library, with
        # the group's Jellyfin/Emby libraries as the fallback.
        library_id = _resolved_library
        plex_fallback, webhook_candidates = webhook_candidates, None
    # Normalize template_id for backward compatibility
    template_id = _normalize_template_id(template_id)

    try:
        event_type = payload.get("eventType", "").lower()
        logger.info(f"[SONARR_WEBHOOK{'_TEST' if test else ''}] Received {event_type} event (template={template_id}, preset={preset_id}, include_seasons={include_seasons})")

        # Only process relevant events
        if event_type not in ["seriesimport", "episodefileimport", "seriesdownload", "episodedownload", "download", "grab", "episodeimport"]:
            logger.debug(f"[SONARR_WEBHOOK] Skipping event type: {event_type}")
            return {"status": "ignored", "reason": f"Event type {event_type} not processed"}

        series = payload.get("series", {})
        tvdb_id = series.get("tvdbId")
        title = series.get("title", "Unknown")
        year = series.get("year")

        if not tvdb_id:
            logger.warning("[SONARR_WEBHOOK] No TVDb ID found in payload")
            raise HTTPException(status_code=400, detail="Missing tvdbId in payload")

        logger.info(f"[SONARR_WEBHOOK{'_TEST' if test else ''}] Processing: {title} ({year}) - TVDb ID: {tvdb_id}")

        # Get episodes from payload to determine which seasons were affected
        episodes = payload.get("episodes", [])
        affected_seasons = set()
        for ep in episodes:
            season_num = ep.get("seasonNumber")
            if season_num is not None:
                affected_seasons.add(season_num)

        logger.info(f"[SONARR_WEBHOOK{'_TEST' if test else ''}] Affected seasons: {sorted(affected_seasons) if affected_seasons else 'Series only'}")

        # Get automation settings
        auto_send = settings.WEBHOOK_AUTO_SEND
        auto_labels = [l.strip() for l in settings.WEBHOOK_AUTO_LABELS.split(",") if l.strip()] if settings.WEBHOOK_AUTO_LABELS else []

        if test:
            logger.info(f"[SONARR_WEBHOOK_TEST] === DRY RUN - NO POSTER GENERATION ===")
            logger.info(f"[SONARR_WEBHOOK_TEST] TV Show: {title} ({year})")
            logger.info(f"[SONARR_WEBHOOK_TEST] TVDb ID: {tvdb_id}")
            logger.info(f"[SONARR_WEBHOOK_TEST] Template: {template_id}")
            logger.info(f"[SONARR_WEBHOOK_TEST] Preset: {preset_id}")
            logger.info(f"[SONARR_WEBHOOK_TEST] Include all seasons: {include_seasons}")
            logger.info(f"[SONARR_WEBHOOK_TEST] Affected seasons from payload: {sorted(affected_seasons) if affected_seasons else 'None'}")
            logger.info(f"[SONARR_WEBHOOK_TEST] Auto-send to Plex: {auto_send}")
            logger.info(f"[SONARR_WEBHOOK_TEST] Labels to apply: {auto_labels}")

            # Try to find the show on the target server (Plex, or a specific
            # Jellyfin/Emby server per Phase 8b's server_id param)
            if is_plex_webhook:
                result = find_plex_show_by_tvdb_id(tvdb_id, library_id)
                if not result and plex_fallback:
                    _hit = _find_on_candidates(plex_fallback, None, tvdb_id, "tv")
                    if _hit:
                        result, server_id = (_hit[0], _hit[1]), _hit[2]
            else:
                if webhook_candidates:
                    _hit = _find_on_candidates(webhook_candidates, None, tvdb_id, "tv")
                    result = (_hit[0], _hit[1]) if _hit else None
                    if _hit:
                        server_id = _hit[2]
                else:
                    result = find_media_server_item_by_external_id(server_id, None, tvdb_id, "tv", library_id)
            if result:
                rating_key, lib_id = result
                logger.info(f"[SONARR_WEBHOOK_TEST] Found with rating_key: {rating_key}, library: {lib_id} (server={server_id or 'plex-1'})")
            else:
                rating_key = None
                lib_id = None
                logger.warning(f"[SONARR_WEBHOOK_TEST] TV show NOT found (server={server_id or 'plex-1'})")

            return {
                "status": "test_success",
                "tv_show": title,
                "year": year,
                "tvdb_id": tvdb_id,
                "rating_key": rating_key,
                "library_id": lib_id,
                "server_id": server_id or "plex-1",
                "template_id": template_id,
                "preset_id": preset_id,
                "include_seasons": include_seasons,
                "affected_seasons": sorted(affected_seasons) if affected_seasons else [],
                "auto_send": auto_send,
                "labels": auto_labels if is_plex_webhook else [],
                "message": "Test mode - no poster generated"
            }

        # Cooldown check - prevent duplicate poster generation when multiple
        # episodes for the same season arrive in quick succession
        seasons_key = ",".join(str(s) for s in sorted(affected_seasons)) if affected_seasons else "all"
        cooldown_key = f"sonarr:{tvdb_id}:{template_id}:{preset_id}:{seasons_key}"

        if _check_webhook_cooldown(cooldown_key):
            return {
                "status": "skipped",
                "reason": "Duplicate webhook within cooldown period",
                "event_type": event_type,
                "title": title,
                "tvdb_id": tvdb_id,
                "affected_seasons": sorted(list(affected_seasons)),
            }

        # Queue background task with delay/retry logic. This allows Plex (or,
        # per Phase 8b, the target Jellyfin/Emby server) time to import the
        # file before we try to find it.
        if is_plex_webhook:
            background_tasks.add_task(
                process_sonarr_webhook_with_retry,
                tvdb_id=tvdb_id,
                title=title,
                year=year,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=auto_labels,
                include_seasons=include_seasons,
                affected_seasons=list(affected_seasons) if affected_seasons else None,
                library_id=library_id,
                fallback_candidates=plex_fallback,
            )
        else:
            background_tasks.add_task(
                process_media_server_webhook_with_retry,
                server_id=server_id,
                candidates=webhook_candidates,
                media_type="tv",
                tmdb_id=None,
                tvdb_id=tvdb_id,
                title=title,
                year=year,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                library_id=library_id,
                include_seasons=include_seasons,
                affected_seasons=list(affected_seasons) if affected_seasons else None,
            )

        return {
            "status": "queued",
            "event_type": event_type,
            "title": title,
            "tvdb_id": tvdb_id,
            "server_id": server_id or "plex-1",
            "template_id": template_id,
            "preset_id": preset_id,
            "include_seasons": include_seasons,
            "affected_seasons": sorted(list(affected_seasons)),
            "auto_send": auto_send,
            "labels": auto_labels if is_plex_webhook else [],
            "message": "Poster generation queued (will wait for import)"
        }

    except Exception as e:
        logger.error(f"[SONARR_WEBHOOK] Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TAUTULLI WEBHOOKS - Plex library event poster generation
# ============================================================================

@router.post("/webhook/tautulli", dependencies=[Depends(verify_webhook_secret)])
def tautulli_webhook(
    background_tasks: BackgroundTasks,
    template_id: str = Query(..., description="Template ID to use for poster generation"),
    preset_id: str = Query(..., description="Preset ID to use"),
    event_types: str = Query("watched,added", description="Comma-separated list of events to process: watched, added, updated"),
    include_seasons: bool = Query(True, description="For TV shows: generate posters for all seasons"),
    test: bool = Query(default=False),
    # Named scope_library_id, NOT library_id -- this function already has its own local
    # `library_id` variable further down (the library the item is ultimately RESOLVED to,
    # reassigned once the search/rating_key is known and read by the label-skip-check /
    # poster-generation calls below). Naming this query param the same thing would have
    # been silently overwritten by that local variable's own `library_id = None`
    # initialization before ever being used to scope the search -- the param would have
    # had zero effect while looking like it should. Radarr/Sonarr's webhook functions
    # don't have this collision (they hand library_id straight to a background task
    # instead of using it locally), so this rename is Tautulli-specific.
    scope_library_id: Optional[str] = Query(
        default=None,
        alias="library_id",
        description="Optional Plex library section id to scope the TMDb/TVDb-ID lookup to, "
                    "used only when Tautulli's payload doesn't already include rating_key "
                    "directly (the default payload template does, so this rarely matters in "
                    "practice). Omitted searches every library of the right type and uses "
                    "whichever has a match first -- ambiguous if the same title exists in "
                    "more than one library.",
    ),
    payload: Dict[str, Any] = Body(...)
):
    """
    Handle Tautulli webhook events (Plex library notifications).

    Expected payload includes:
    - event: Event type (library.new, library.update, etc.)
    - media_type: movie or episode
    - title, year, tmdb_id/tvdb_id
    - rating_key: Plex rating key (if available)

    Query params:
    - template_id: Required - Template to use
    - preset_id: Required - Preset to use
    - event_types: Comma-separated events to process (watched, added, updated)
    - include_seasons: For TV shows, generate posters for all seasons
    - test: If true, performs a dry run with detailed logging but no poster generation
    - library_id: Optional -- scope the Plex lookup to one library (only used as a
      fallback when the payload has no rating_key)
    """
    # Normalize template_id for backward compatibility
    template_id = _normalize_template_id(template_id)

    try:
        event = payload.get("event", "").lower()
        media_type = payload.get("media_type", "").lower()

        logger.info(f"[TAUTULLI_WEBHOOK{'_TEST' if test else ''}] Received {event} event, media_type={media_type}")

        # Map Tautulli event names to our categories
        event_map = {
            "library.new": "added",
            "created": "added",  # Tautulli sometimes sends "created" for new items
            "library.update": "updated",
            "playback.stop": "watched"
        }

        event_category = event_map.get(event, "unknown")
        processing_events = [e.strip().lower() for e in event_types.split(",")]

        logger.info(f"[TAUTULLI_WEBHOOK] Event category: '{event_category}', Processing events: {processing_events}")

        # Check if we should process this event
        if event_category not in processing_events:
            logger.info(f"[TAUTULLI_WEBHOOK] Event '{event_category}' not in processing list: {processing_events} - IGNORING")
            return {"status": "ignored", "reason": f"Event type {event_category} not in processing list"}

        if media_type not in ["movie", "episode", "show", "season"]:
            logger.warning(f"[TAUTULLI_WEBHOOK] Unknown media type: {media_type}")
            raise HTTPException(status_code=400, detail=f"Unknown media type: {media_type}")

        # Extract title early for logging
        title = payload.get("title", "Unknown")
        year = payload.get("year")

        # Handle season media type - ignore gracefully as we process seasons via the show
        if media_type == "season":
            logger.info(f"[TAUTULLI_WEBHOOK] Ignoring season event for '{title}' - seasons are processed via their parent show")
            return {"status": "ignored", "reason": "Season events are handled when processing their parent TV show"}

        # Skip episode events for "added" category to avoid duplicate processing
        # (Tautulli sends an event for each episode, but we only want to process once per show/season)
        if media_type == "episode" and event_category == "added":
            logger.info(f"[TAUTULLI_WEBHOOK] Skipping episode '{title}' for 'added' event - only process show-level events to avoid duplicates")
            return {"status": "ignored", "reason": "Episode events for 'added' category are skipped to avoid duplicates. Configure Tautulli to send show-level events instead."}

        # Get automation settings
        auto_send = settings.WEBHOOK_AUTO_SEND
        auto_labels = [l.strip() for l in settings.WEBHOOK_AUTO_LABELS.split(",") if l.strip()] if settings.WEBHOOK_AUTO_LABELS else []

        # Test mode - detailed logging
        if test:
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] === DRY RUN - NO POSTER GENERATION ===")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Event: {event} (category: {event_category})")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Media type: {media_type}")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Title: {title} ({year})")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Template: {template_id}")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Preset: {preset_id}")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Processing events: {processing_events}")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Include seasons (TV): {include_seasons}")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Auto-send to Plex: {auto_send}")
            logger.info(f"[TAUTULLI_WEBHOOK_TEST] Labels to apply: {auto_labels}")

            rating_key = payload.get("rating_key")
            lib_id = None
            if media_type == "movie":
                tmdb_id = payload.get("tmdb_id")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] TMDb ID: {tmdb_id}")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from payload: {rating_key}")
                if not rating_key and tmdb_id:
                    result = find_plex_movie_by_tmdb_id(int(tmdb_id), scope_library_id)
                    if result:
                        rating_key, lib_id = result
                    logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from TMDb lookup: {rating_key}, library: {lib_id}")
            else:
                tvdb_id = payload.get("tvdb_id")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] TVDb ID: {tvdb_id}")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from payload: {rating_key}")
                if not rating_key and tvdb_id:
                    result = find_plex_show_by_tvdb_id(int(tvdb_id), scope_library_id)
                    if result:
                        rating_key, lib_id = result
                    logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from TVDb lookup: {rating_key}, library: {lib_id}")

            return {
                "status": "test_success",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "year": year,
                "rating_key": rating_key,
                "library_id": lib_id,
                "template_id": template_id,
                "preset_id": preset_id,
                "include_seasons": include_seasons if media_type != "movie" else None,
                "auto_send": auto_send,
                "labels": auto_labels,
                "message": "Test mode - no poster generated"
            }

        # Tautulli often provides rating_key directly
        rating_key = payload.get("rating_key")
        library_id = None

        if media_type == "movie":
            tmdb_id = payload.get("tmdb_id")

            # If no rating_key but have TMDb ID, search for it
            if not rating_key and tmdb_id:
                result = find_plex_movie_by_tmdb_id(int(tmdb_id), scope_library_id)
                if result:
                    rating_key, library_id = result

            if not rating_key:
                logger.warning("[TAUTULLI_WEBHOOK] No rating_key found for movie")
                raise HTTPException(status_code=400, detail="Missing rating_key for movie")

            # If we have a rating_key but no library_id, look it up from Plex metadata
            if rating_key and not library_id:
                try:
                    meta_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
                    r = plex_session.get(meta_url, headers=plex_headers(), timeout=10)
                    r.raise_for_status()
                    root = ET.fromstring(r.content)
                    video = root.find(".//Video")
                    if video is not None:
                        library_id = video.get("librarySectionID")
                        logger.debug(f"[TAUTULLI_WEBHOOK] Got library_id {library_id} from Plex metadata for movie {rating_key}")
                except Exception as e:
                    logger.warning(f"[TAUTULLI_WEBHOOK] Failed to get library_id from Plex metadata: {e}")

            logger.info(f"[TAUTULLI_WEBHOOK] Movie: {title} ({year}) - rating_key: {rating_key}, library: {library_id}")

            # Cooldown check - prevent duplicate poster generation
            cooldown_key = f"tautulli:movie:{rating_key}:{template_id}:{preset_id}"
            if _check_webhook_cooldown(cooldown_key):
                return {
                    "status": "skipped",
                    "reason": "Duplicate webhook within cooldown period",
                    "title": title,
                    "rating_key": rating_key,
                }

            # Check if item has ignore labels
            if library_id and _should_skip_webhook(rating_key, library_id, is_tv=False):
                logger.info(f"[TAUTULLI_WEBHOOK] Skipping poster generation for {title} - has webhook ignore label")
                return {
                    "status": "skipped",
                    "reason": "Item has webhook ignore label",
                    "title": title,
                    "rating_key": rating_key,
                }

            # Queue background task to generate and send poster
            background_tasks.add_task(
                process_webhook_poster_generation,
                rating_key=rating_key,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=auto_labels,
                library_id=library_id,
                is_tv=False
            )

            return {
                "status": "queued",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "rating_key": rating_key,
                "library_id": library_id,
                "template_id": template_id,
                "preset_id": preset_id,
                "auto_send": auto_send,
                "labels": auto_labels
            }

        else:  # episode or show
            tvdb_id = payload.get("tvdb_id")

            # For episodes, we need the show's rating_key, not the episode's
            # If rating_key is provided, it might be the episode - we need the show
            if rating_key and media_type == "episode":
                # Get the show's rating_key and library_id from the episode
                try:
                    ep_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
                    r = plex_session.get(ep_url, headers=plex_headers(), timeout=10)
                    r.raise_for_status()
                    root = ET.fromstring(r.content)
                    # Get grandparentRatingKey (show's rating key) and librarySectionID
                    video = root.find(".//Video")
                    if video is not None:
                        rating_key = video.get("grandparentRatingKey")
                        library_id = video.get("librarySectionID")
                        logger.debug(f"[TAUTULLI_WEBHOOK] Got show rating_key {rating_key}, library {library_id} from episode")
                except Exception as e:
                    logger.warning(f"[TAUTULLI_WEBHOOK] Failed to get show rating_key from episode: {e}")
                    rating_key = None

            # If still no rating_key but have TVDb ID, search for it
            if not rating_key and tvdb_id:
                result = find_plex_show_by_tvdb_id(int(tvdb_id), scope_library_id)
                if result:
                    rating_key, library_id = result

            # If we have rating_key but still no library_id, fetch from Plex metadata
            if rating_key and not library_id:
                try:
                    meta_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
                    r = plex_session.get(meta_url, headers=plex_headers(), timeout=10)
                    r.raise_for_status()
                    root = ET.fromstring(r.content)
                    # TV shows use <Directory> element, not <Video>
                    directory = root.find(".//Directory")
                    if directory is not None:
                        library_id = directory.get("librarySectionID")
                        logger.debug(f"[TAUTULLI_WEBHOOK] Got library_id {library_id} from Plex metadata for show {rating_key}")
                except Exception as e:
                    logger.warning(f"[TAUTULLI_WEBHOOK] Failed to get library_id from Plex metadata for show: {e}")

            if not rating_key:
                logger.warning("[TAUTULLI_WEBHOOK] No rating_key found for TV show")
                raise HTTPException(status_code=400, detail="Missing rating_key for TV show")

            season_num = payload.get("season")
            episode_num = payload.get("episode")

            logger.info(f"[TAUTULLI_WEBHOOK] TV Show: {title} - rating_key: {rating_key}, library: {library_id}")

            # Cooldown check - prevent duplicate poster generation
            cooldown_key = f"tautulli:tv:{rating_key}:{template_id}:{preset_id}"
            if _check_webhook_cooldown(cooldown_key):
                return {
                    "status": "skipped",
                    "reason": "Duplicate webhook within cooldown period",
                    "title": title,
                    "rating_key": rating_key,
                }

            # Check if item has ignore labels
            if library_id and _should_skip_webhook(rating_key, library_id, is_tv=True):
                logger.info(f"[TAUTULLI_WEBHOOK] Skipping poster generation for {title} - has webhook ignore label")
                return {
                    "status": "skipped",
                    "reason": "Item has webhook ignore label",
                    "title": title,
                    "rating_key": rating_key,
                }

            # Queue background task to generate and send poster
            background_tasks.add_task(
                process_webhook_poster_generation,
                rating_key=rating_key,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=auto_labels,
                library_id=library_id,
                is_tv=True,
                include_seasons=include_seasons
            )

            return {
                "status": "queued",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "rating_key": rating_key,
                "library_id": library_id,
                "season": season_num,
                "episode": episode_num,
                "template_id": template_id,
                "preset_id": preset_id,
                "include_seasons": include_seasons,
                "auto_send": auto_send,
                "labels": auto_labels
            }

    except Exception as e:
        logger.error(f"[TAUTULLI_WEBHOOK] Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhook/test")
def test_webhook():
    """Test endpoint to verify webhooks are working."""
    return {
        "status": "ok",
        "message": "Webhook endpoints are active",
        "endpoints": [
            "/webhook/radarr/{template_id}/{preset_id}",
            "/webhook/sonarr/{template_id}/{preset_id}?include_seasons=true|false",
            "/webhook/tautulli?template_id=...&preset_id=...&event_types=watched,added,updated&include_seasons=true|false"
        ]
    }
