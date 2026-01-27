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
from typing import Dict, Any, Optional, List
import xml.etree.ElementTree as ET

from ..config import logger, settings, plex_headers, plex_session, load_presets
from ..schemas import MovieBatchRequest, TVShowBatchRequest
from .. import database as db

router = APIRouter()


# ============================================================================
# HELPER FUNCTIONS - Find Plex items by external IDs
# ============================================================================

def find_plex_movie_by_tmdb_id(tmdb_id: int, library_id: Optional[str] = None) -> Optional[str]:
    """
    Find a Plex movie's rating_key by its TMDb ID.

    Args:
        tmdb_id: The TMDb ID to search for
        library_id: Optional library ID to search in (defaults to all movie libraries)

    Returns:
        rating_key if found, None otherwise
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
            url = f"{settings.PLEX_URL}/library/sections/{lib_key}/all"
            r = plex_session.get(url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)

            for video in root.findall(".//Video"):
                rating_key = video.get("ratingKey")
                # Check GUID for TMDb match
                for guid in video.findall("Guid"):
                    guid_id = guid.get("id", "")
                    if f"tmdb://{tmdb_id}" in guid_id:
                        logger.info(f"[WEBHOOK] Found movie rating_key={rating_key} for TMDb ID {tmdb_id}")
                        return rating_key

        logger.warning(f"[WEBHOOK] Could not find Plex movie with TMDb ID {tmdb_id}")
        return None

    except Exception as e:
        logger.error(f"[WEBHOOK] Error searching for movie with TMDb ID {tmdb_id}: {e}")
        return None


def find_plex_show_by_tvdb_id(tvdb_id: int, library_id: Optional[str] = None) -> Optional[str]:
    """
    Find a Plex TV show's rating_key by its TVDb ID.

    Args:
        tvdb_id: The TVDb ID to search for
        library_id: Optional library ID to search in (defaults to all TV libraries)

    Returns:
        rating_key if found, None otherwise
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
            url = f"{settings.PLEX_URL}/library/sections/{lib_key}/all"
            r = plex_session.get(url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.content)

            for video in root.findall(".//Directory[@type='show']"):
                rating_key = video.get("ratingKey")
                # Check GUID for TVDb match
                for guid in video.findall("Guid"):
                    guid_id = guid.get("id", "")
                    if f"tvdb://{tvdb_id}" in guid_id:
                        logger.info(f"[WEBHOOK] Found TV show rating_key={rating_key} for TVDb ID {tvdb_id}")
                        return rating_key

        logger.warning(f"[WEBHOOK] Could not find Plex TV show with TVDb ID {tvdb_id}")
        return None

    except Exception as e:
        logger.error(f"[WEBHOOK] Error searching for TV show with TVDb ID {tvdb_id}: {e}")
        return None


def process_webhook_poster_generation(
    rating_key: str,
    template_id: str,
    preset_id: str,
    auto_send: bool,
    auto_labels: List[str],
    library_id: Optional[str],
    is_tv: bool = False,
    include_seasons: bool = False
):
    """
    Background task to generate and send poster to Plex.
    This runs asynchronously after the webhook returns a response.
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
                source='webhook'
            )

            # Check result status
            result_status = result.get("status")
            if result_status == "success":
                logger.info(f"[WEBHOOK] Successfully processed TV show {rating_key}")
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

            # Check result status
            result_status = result.get("status")
            if result_status == "success":
                logger.info(f"[WEBHOOK] Successfully processed movie {rating_key}")
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
            rating_key = find_plex_movie_by_tmdb_id(tmdb_id)
            if rating_key:
                logger.info(f"[RADARR_WEBHOOK_TEST] Found in Plex with rating_key: {rating_key}")
            else:
                logger.warning(f"[RADARR_WEBHOOK_TEST] Movie NOT found in Plex library")

            return {
                "status": "test_success",
                "movie": title,
                "year": year,
                "tmdb_id": tmdb_id,
                "rating_key": rating_key,
                "template_id": template_id,
                "preset_id": preset_id,
                "auto_send": auto_send,
                "labels": auto_labels,
                "message": "Test mode - no poster generated"
            }

        # Find the movie in Plex by TMDb ID
        rating_key = find_plex_movie_by_tmdb_id(tmdb_id)

        if not rating_key:
            logger.warning(f"[RADARR_WEBHOOK] Could not find movie in Plex library (TMDb ID: {tmdb_id})")
            return {
                "status": "error",
                "error": "Movie not found in Plex library",
                "tmdb_id": tmdb_id,
                "title": title
            }

        # Queue background task to generate and send poster
        background_tasks.add_task(
            process_webhook_poster_generation,
            rating_key=rating_key,
            template_id=template_id,
            preset_id=preset_id,
            auto_send=auto_send,
            auto_labels=auto_labels,
            library_id=None,
            is_tv=False
        )

        return {
            "status": "queued",
            "event_type": event_type,
            "title": title,
            "tmdb_id": tmdb_id,
            "rating_key": rating_key,
            "template_id": template_id,
            "preset_id": preset_id,
            "auto_send": auto_send,
            "labels": auto_labels
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
            rating_key = find_plex_show_by_tvdb_id(tvdb_id)
            if rating_key:
                logger.info(f"[SONARR_WEBHOOK_TEST] Found in Plex with rating_key: {rating_key}")
            else:
                logger.warning(f"[SONARR_WEBHOOK_TEST] TV show NOT found in Plex library")

            return {
                "status": "test_success",
                "tv_show": title,
                "year": year,
                "tvdb_id": tvdb_id,
                "rating_key": rating_key,
                "template_id": template_id,
                "preset_id": preset_id,
                "include_seasons": include_seasons,
                "affected_seasons": sorted(affected_seasons) if affected_seasons else [],
                "auto_send": auto_send,
                "labels": auto_labels,
                "message": "Test mode - no poster generated"
            }

        # Find the TV show in Plex by TVDb ID
        rating_key = find_plex_show_by_tvdb_id(tvdb_id)

        if not rating_key:
            logger.warning(f"[SONARR_WEBHOOK] Could not find TV show in Plex library (TVDb ID: {tvdb_id})")
            return {
                "status": "error",
                "error": "TV show not found in Plex library",
                "tvdb_id": tvdb_id,
                "title": title
            }

        # Queue background task to generate and send poster
        background_tasks.add_task(
            process_webhook_poster_generation,
            rating_key=rating_key,
            template_id=template_id,
            preset_id=preset_id,
            auto_send=auto_send,
            auto_labels=auto_labels,
            library_id=None,
            is_tv=True,
            include_seasons=include_seasons
        )

        return {
            "status": "queued",
            "event_type": event_type,
            "title": title,
            "tvdb_id": tvdb_id,
            "rating_key": rating_key,
            "template_id": template_id,
            "preset_id": preset_id,
            "include_seasons": include_seasons,
            "affected_seasons": sorted(list(affected_seasons)),
            "auto_send": auto_send,
            "labels": auto_labels
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

        if media_type not in ["movie", "episode", "show"]:
            logger.warning(f"[TAUTULLI_WEBHOOK] Unknown media type: {media_type}")
            raise HTTPException(status_code=400, detail=f"Unknown media type: {media_type}")

        # Skip episode events for "added" category to avoid duplicate processing
        # (Tautulli sends an event for each episode, but we only want to process once per show/season)
        if media_type == "episode" and event_category == "added":
            logger.info(f"[TAUTULLI_WEBHOOK] Skipping episode '{title}' for 'added' event - only process show-level events to avoid duplicates")
            return {"status": "ignored", "reason": "Episode events for 'added' category are skipped to avoid duplicates. Configure Tautulli to send show-level events instead."}

        title = payload.get("title", "Unknown")
        year = payload.get("year")

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
            if media_type == "movie":
                tmdb_id = payload.get("tmdb_id")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] TMDb ID: {tmdb_id}")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from payload: {rating_key}")
                if not rating_key and tmdb_id:
                    rating_key = find_plex_movie_by_tmdb_id(int(tmdb_id))
                    logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from TMDb lookup: {rating_key}")
            else:
                tvdb_id = payload.get("tvdb_id")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] TVDb ID: {tvdb_id}")
                logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from payload: {rating_key}")
                if not rating_key and tvdb_id:
                    rating_key = find_plex_show_by_tvdb_id(int(tvdb_id))
                    logger.info(f"[TAUTULLI_WEBHOOK_TEST] Rating key from TVDb lookup: {rating_key}")

            return {
                "status": "test_success",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "year": year,
                "rating_key": rating_key,
                "template_id": template_id,
                "preset_id": preset_id,
                "include_seasons": include_seasons if media_type != "movie" else None,
                "auto_send": auto_send,
                "labels": auto_labels,
                "message": "Test mode - no poster generated"
            }

        # Tautulli often provides rating_key directly
        rating_key = payload.get("rating_key")

        if media_type == "movie":
            tmdb_id = payload.get("tmdb_id")

            # If no rating_key but have TMDb ID, search for it
            if not rating_key and tmdb_id:
                rating_key = find_plex_movie_by_tmdb_id(int(tmdb_id))

            if not rating_key:
                logger.warning("[TAUTULLI_WEBHOOK] No rating_key found for movie")
                raise HTTPException(status_code=400, detail="Missing rating_key for movie")

            logger.info(f"[TAUTULLI_WEBHOOK] Movie: {title} ({year}) - rating_key: {rating_key}")

            # Queue background task to generate and send poster
            background_tasks.add_task(
                process_webhook_poster_generation,
                rating_key=rating_key,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=auto_labels,
                library_id=None,
                is_tv=False
            )

            return {
                "status": "queued",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "rating_key": rating_key,
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
                # Get the show's rating_key from the episode
                try:
                    ep_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
                    r = plex_session.get(ep_url, headers=plex_headers(), timeout=10)
                    r.raise_for_status()
                    root = ET.fromstring(r.content)
                    # Get grandparentRatingKey (show's rating key)
                    video = root.find(".//Video")
                    if video is not None:
                        rating_key = video.get("grandparentRatingKey")
                        logger.debug(f"[TAUTULLI_WEBHOOK] Got show rating_key {rating_key} from episode")
                except Exception as e:
                    logger.warning(f"[TAUTULLI_WEBHOOK] Failed to get show rating_key from episode: {e}")
                    rating_key = None

            # If still no rating_key but have TVDb ID, search for it
            if not rating_key and tvdb_id:
                rating_key = find_plex_show_by_tvdb_id(int(tvdb_id))

            if not rating_key:
                logger.warning("[TAUTULLI_WEBHOOK] No rating_key found for TV show")
                raise HTTPException(status_code=400, detail="Missing rating_key for TV show")

            season_num = payload.get("season")
            episode_num = payload.get("episode")

            logger.info(f"[TAUTULLI_WEBHOOK] TV Show: {title} - rating_key: {rating_key}")

            # Queue background task to generate and send poster
            background_tasks.add_task(
                process_webhook_poster_generation,
                rating_key=rating_key,
                template_id=template_id,
                preset_id=preset_id,
                auto_send=auto_send,
                auto_labels=auto_labels,
                library_id=None,
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
