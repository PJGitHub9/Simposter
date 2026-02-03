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

from fastapi import APIRouter, HTTPException, Query, Body, BackgroundTasks
from typing import Dict, Any, Optional, List, Callable
import xml.etree.ElementTree as ET
import time
import threading

from ..config import logger, settings, plex_headers, plex_session, load_presets
from ..schemas import MovieBatchRequest, TVShowBatchRequest, Movie
from .. import database as db
from .. import cache
from .notifications import send_discord_notification

router = APIRouter()


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
            logger.info(f"[WEBHOOK] Skipping {rating_key} - has ignore label '{label}'")
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
                # Check GUID for TMDb match
                for guid in video.findall("Guid"):
                    guid_id = guid.get("id", "")
                    if f"tmdb://{tmdb_id}" in guid_id:
                        logger.info(f"[WEBHOOK] Found movie rating_key={rating_key} in library={lib_key} for TMDb ID {tmdb_id}")
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
                # Check GUID for TVDb match
                for guid in video.findall("Guid"):
                    guid_id = guid.get("id", "")
                    if f"tvdb://{tvdb_id}" in guid_id:
                        logger.info(f"[WEBHOOK] Found TV show rating_key={rating_key} in library={lib_key} for TVDb ID {tvdb_id}")
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
    # Initial delay to give Plex time to import the file
    logger.info(f"[WEBHOOK] Waiting {initial_delay}s for Plex to import {item_type} (ID: {external_id})")
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


def process_radarr_webhook_with_retry(
    tmdb_id: int,
    title: str,
    year: Optional[int],
    template_id: str,
    preset_id: str,
    auto_send: bool,
    auto_labels: List[str]
):
    """
    Background task for Radarr webhooks that waits for Plex import, then generates poster.
    """
    logger.info(f"[RADARR_WEBHOOK] Starting delayed processing for: {title} ({year}) - TMDb ID: {tmdb_id}")

    # Find movie with retry logic - returns (rating_key, library_id) tuple
    result = find_plex_item_with_retry(
        find_func=find_plex_movie_by_tmdb_id,
        external_id=tmdb_id,
        item_type="movie",
        library_id=None,
        initial_delay=30,
        max_retries=5,
        retry_delay=15
    )

    if not result:
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
    affected_seasons: Optional[List[int]] = None
):
    """
    Background task for Sonarr webhooks that waits for Plex import, then generates poster.
    """
    logger.info(f"[SONARR_WEBHOOK] Starting delayed processing for: {title} ({year}) - TVDb ID: {tvdb_id}, affected_seasons: {affected_seasons}")

    # Find TV show with retry logic - returns (rating_key, library_id) tuple
    result = find_plex_item_with_retry(
        find_func=find_plex_show_by_tvdb_id,
        external_id=tvdb_id,
        item_type="TV show",
        library_id=None,
        initial_delay=30,
        max_retries=5,
        retry_delay=15
    )

    if not result:
        logger.error(f"[SONARR_WEBHOOK] Could not find TV show in Plex after retries: {title} (TVDb ID: {tvdb_id})")
        return

    rating_key, library_id = result

    # Check if item has ignore labels
    if library_id and _should_skip_webhook(rating_key, library_id, is_tv=True):
        logger.info(f"[SONARR_WEBHOOK] Skipping poster generation for {title} - has webhook ignore label")
        return

    # Now process the poster generation
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


def process_webhook_poster_generation(
    rating_key: str,
    template_id: str,
    preset_id: str,
    auto_send: bool,
    auto_labels: List[str],
    library_id: Optional[str],
    is_tv: bool = False,
    include_seasons: bool = False,
    affected_seasons: Optional[List[int]] = None
):
    """
    Background task to generate and send poster to Plex.
    This runs asynchronously after the webhook returns a response.

    Args:
        affected_seasons: For TV shows, only process these specific seasons.
                         If None or empty, process all seasons (for new series).
    """
    try:
        from .batch import _process_single_movie, _process_single_tv_show

        # Load preset options
        presets_data = load_presets()
        template_presets = presets_data.get(template_id, {}).get("presets", [])
        preset = next((p for p in template_presets if p.get("id") == preset_id), None)

        if not preset:
            logger.error(f"[WEBHOOK] Preset '{preset_id}' not found for template '{template_id}'")
            return

        options = preset.get("options", {})

        if is_tv:
            # Create TV show batch request
            request = TVShowBatchRequest(
                rating_keys=[rating_key],
                template_id=template_id,
                preset_id=preset_id,
                options=options,
                send_to_plex=auto_send,
                save_locally=False,
                labels=auto_labels,
                library_id=library_id,
                include_seasons=include_seasons,
                fallbackPosterAction=options.get("fallbackPosterAction"),
                fallbackPosterTemplate=options.get("fallbackPosterTemplate"),
                fallbackPosterPreset=options.get("fallbackPosterPreset")
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
                source='webhook',
                affected_seasons=affected_seasons
            )

            # Check result status - batch functions return "ok" on success
            result_status = result.get("status")
            if result_status == "ok":
                logger.info(f"[WEBHOOK] Successfully processed TV show {rating_key}")
                # Update cache so the show appears in library view
                try:
                    logger.info(f"[WEBHOOK] Updating TV cache for {rating_key} (library_id={library_id})")
                    _update_tv_cache(rating_key, library_id)
                except Exception as cache_err:
                    logger.warning(f"[WEBHOOK] Failed to update TV cache for {rating_key}: {cache_err}", exc_info=True)
                # Send Discord notification
                try:
                    send_discord_notification(
                        title=result.get("show_title", "Unknown TV Show"),
                        template_id=template_id,
                        preset_id=preset_id,
                        library_id=library_id,
                        source="webhook",
                        action="sent_to_plex" if auto_send else "saved"
                    )
                except Exception as notif_err:
                    logger.debug(f"[WEBHOOK] Failed to send Discord notification: {notif_err}")
            else:
                # Log full result for debugging
                logger.debug(f"[WEBHOOK] Result dict for {rating_key}: {result}")
                error_msg = result.get('error') or result.get('message', 'Unknown error')
                logger.warning(f"[WEBHOOK] Unexpected result status for TV show {rating_key}: status={result_status}, error={error_msg}")

        else:
            # Create movie batch request
            request = MovieBatchRequest(
                rating_keys=[rating_key],
                template_id=template_id,
                preset_id=preset_id,
                options=options,
                send_to_plex=auto_send,
                save_locally=False,
                labels=auto_labels,
                library_id=library_id
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
                source='webhook'
            )

            # Check result status - batch functions return "ok" on success
            result_status = result.get("status")
            if result_status == "ok":
                logger.info(f"[WEBHOOK] Successfully processed movie {rating_key}")
                # Update cache so the movie appears in library view
                try:
                    logger.info(f"[WEBHOOK] Updating movie cache for {rating_key} (library_id={library_id})")
                    _update_movie_cache(rating_key, library_id)
                except Exception as cache_err:
                    logger.warning(f"[WEBHOOK] Failed to update movie cache for {rating_key}: {cache_err}", exc_info=True)
                # Send Discord notification
                try:
                    # Get movie title from cache if available
                    cached_movies = db.get_cached_movies()
                    movie_info = next((m for m in cached_movies if m.get("key") == rating_key or m.get("rating_key") == rating_key), None)
                    movie_title = movie_info.get("title") if movie_info else "Unknown Movie"
                    movie_year = movie_info.get("year") if movie_info else None
                    send_discord_notification(
                        title=movie_title,
                        year=movie_year,
                        template_id=template_id,
                        preset_id=preset_id,
                        library_id=library_id,
                        source="webhook",
                        action="sent_to_plex" if auto_send else "saved"
                    )
                except Exception as notif_err:
                    logger.debug(f"[WEBHOOK] Failed to send Discord notification: {notif_err}")
            else:
                # Log full result for debugging
                logger.debug(f"[WEBHOOK] Result dict for {rating_key}: {result}")
                error_msg = result.get('error') or result.get('message', 'Unknown error')
                logger.warning(f"[WEBHOOK] Unexpected result status for movie {rating_key}: status={result_status}, error={error_msg}")

    except Exception as e:
        logger.error(f"[WEBHOOK] Error in background poster generation: {e}", exc_info=True)


# ============================================================================
# RADARR WEBHOOKS - Movie poster generation
# ============================================================================

@router.post("/webhook/radarr/{template_id}/{preset_id}")
def radarr_webhook(
    template_id: str,
    preset_id: str,
    background_tasks: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    test: bool = Query(default=False)
):
    """
    Handle Radarr webhook events for movie imports/upgrades.

    Expected payload includes:
    - eventType: "MovieImport", "MovieDownload", etc.
    - movie: { tmdbId, title, year, ... }
    - movieFile: { path, releaseGroup, ... }

    Query params:
    - test: If true, performs a dry run with detailed logging but no poster generation
    """
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

            # Try to find the movie in Plex
            result = find_plex_movie_by_tmdb_id(tmdb_id)
            if result:
                rating_key, lib_id = result
                logger.info(f"[RADARR_WEBHOOK_TEST] Found in Plex with rating_key: {rating_key}, library: {lib_id}")
            else:
                rating_key = None
                lib_id = None
                logger.warning(f"[RADARR_WEBHOOK_TEST] Movie NOT found in Plex library")

            return {
                "status": "test_success",
                "movie": title,
                "year": year,
                "tmdb_id": tmdb_id,
                "rating_key": rating_key,
                "library_id": lib_id,
                "template_id": template_id,
                "preset_id": preset_id,
                "auto_send": auto_send,
                "labels": auto_labels,
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

        # Queue background task with delay/retry logic
        # This allows Plex time to import the file before we try to find it
        background_tasks.add_task(
            process_radarr_webhook_with_retry,
            tmdb_id=tmdb_id,
            title=title,
            year=year,
            template_id=template_id,
            preset_id=preset_id,
            auto_send=auto_send,
            auto_labels=auto_labels
        )

        return {
            "status": "queued",
            "event_type": event_type,
            "title": title,
            "tmdb_id": tmdb_id,
            "template_id": template_id,
            "preset_id": preset_id,
            "auto_send": auto_send,
            "labels": auto_labels,
            "message": "Poster generation queued (will wait for Plex import)"
        }

    except Exception as e:
        logger.error(f"[RADARR_WEBHOOK] Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SONARR WEBHOOKS - TV show poster generation with season control
# ============================================================================

@router.post("/webhook/sonarr/{template_id}/{preset_id}")
def sonarr_webhook(
    template_id: str,
    preset_id: str,
    background_tasks: BackgroundTasks,
    include_seasons: bool = Query(True, description="Generate posters for all seasons"),
    test: bool = Query(default=False),
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
    """
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

            # Try to find the show in Plex
            result = find_plex_show_by_tvdb_id(tvdb_id)
            if result:
                rating_key, lib_id = result
                logger.info(f"[SONARR_WEBHOOK_TEST] Found in Plex with rating_key: {rating_key}, library: {lib_id}")
            else:
                rating_key = None
                lib_id = None
                logger.warning(f"[SONARR_WEBHOOK_TEST] TV show NOT found in Plex library")

            return {
                "status": "test_success",
                "tv_show": title,
                "year": year,
                "tvdb_id": tvdb_id,
                "rating_key": rating_key,
                "library_id": lib_id,
                "template_id": template_id,
                "preset_id": preset_id,
                "include_seasons": include_seasons,
                "affected_seasons": sorted(affected_seasons) if affected_seasons else [],
                "auto_send": auto_send,
                "labels": auto_labels,
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

        # Queue background task with delay/retry logic
        # This allows Plex time to import the file before we try to find it
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
            affected_seasons=list(affected_seasons) if affected_seasons else None
        )

        return {
            "status": "queued",
            "event_type": event_type,
            "title": title,
            "tvdb_id": tvdb_id,
            "template_id": template_id,
            "preset_id": preset_id,
            "include_seasons": include_seasons,
            "affected_seasons": sorted(list(affected_seasons)),
            "auto_send": auto_send,
            "labels": auto_labels,
            "message": "Poster generation queued (will wait for Plex import)"
        }

    except Exception as e:
        logger.error(f"[SONARR_WEBHOOK] Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TAUTULLI WEBHOOKS - Plex library event poster generation
# ============================================================================

@router.post("/webhook/tautulli")
def tautulli_webhook(
    background_tasks: BackgroundTasks,
    template_id: str = Query(..., description="Template ID to use for poster generation"),
    preset_id: str = Query(..., description="Preset ID to use"),
    event_types: str = Query("watched,added", description="Comma-separated list of events to process: watched, added, updated"),
    include_seasons: bool = Query(True, description="For TV shows: generate posters for all seasons"),
    test: bool = Query(default=False),
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
    """
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
                    result = find_plex_movie_by_tmdb_id(int(tmdb_id))
                    if result:
                        rating_key, lib_id = result
                    logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from TMDb lookup: {rating_key}, library: {lib_id}")
            else:
                tvdb_id = payload.get("tvdb_id")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] TVDb ID: {tvdb_id}")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from payload: {rating_key}")
                if not rating_key and tvdb_id:
                    result = find_plex_show_by_tvdb_id(int(tvdb_id))
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
                result = find_plex_movie_by_tmdb_id(int(tmdb_id))
                if result:
                    rating_key, library_id = result

            if not rating_key:
                logger.warning("[TAUTULLI_WEBHOOK] No rating_key found for movie")
                raise HTTPException(status_code=400, detail="Missing rating_key for movie")

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
                result = find_plex_show_by_tvdb_id(int(tvdb_id))
                if result:
                    rating_key, library_id = result

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
