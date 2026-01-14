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

from fastapi import APIRouter, HTTPException, Query, Body
from typing import Dict, Any, Optional, List
import requests

from ..config import logger, settings
from ..schemas import MovieBatchRequest, TVShowBatchRequest
from ..rendering import render_poster_image
from .. import database as db, cache

router = APIRouter()


# ============================================================================
# RADARR WEBHOOKS - Movie poster generation
# ============================================================================

@router.post("/webhook/radarr/{template_id}/{preset_id}")
def radarr_webhook(
    template_id: str,
    preset_id: str,
    payload: Dict[str, Any] = Body(...)
):
    """
    Handle Radarr webhook events for movie imports/upgrades.
    
    Expected payload includes:
    - eventType: "MovieImport", "MovieDownload", etc.
    - movie: { tmdbId, title, year, ... }
    - movieFile: { path, releaseGroup, ... }
    """
    try:
        event_type = payload.get("eventType", "").lower()
        logger.info(f"[RADARR_WEBHOOK] Received {event_type} event (template={template_id}, preset={preset_id})")
        
        # Only process relevant events
        if event_type not in ["movieimport", "moviedownload", "moviefileimported"]:
            logger.debug(f"[RADARR_WEBHOOK] Skipping event type: {event_type}")
            return {"status": "ignored", "reason": f"Event type {event_type} not processed"}
        
        movie = payload.get("movie", {})
        tmdb_id = movie.get("tmdbId")
        title = movie.get("title", "Unknown")
        year = movie.get("year")
        
        if not tmdb_id:
            logger.warning("[RADARR_WEBHOOK] No TMDb ID found in payload")
            raise HTTPException(status_code=400, detail="Missing tmdbId in payload")
        
        logger.info(f"[RADARR_WEBHOOK] Processing: {title} ({year}) - TMDb ID: {tmdb_id}")
        
        # Optional: Auto-send to Plex if configured
        auto_send = settings.WEBHOOK_AUTO_SEND
        auto_labels = settings.WEBHOOK_AUTO_LABELS.split(",") if settings.WEBHOOK_AUTO_LABELS else []
        
        return {
            "status": "received",
            "event_type": event_type,
            "title": title,
            "tmdb_id": tmdb_id,
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
    include_seasons: bool = Query(True, description="Generate posters for all seasons"),
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
    """
    try:
        event_type = payload.get("eventType", "").lower()
        logger.info(f"[SONARR_WEBHOOK] Received {event_type} event (template={template_id}, preset={preset_id}, include_seasons={include_seasons})")
        
        # Only process relevant events
        if event_type not in ["seriesimport", "episodefileimport", "seriesdownload", "episodedownload"]:
            logger.debug(f"[SONARR_WEBHOOK] Skipping event type: {event_type}")
            return {"status": "ignored", "reason": f"Event type {event_type} not processed"}
        
        series = payload.get("series", {})
        tvdb_id = series.get("tvdbId")
        title = series.get("title", "Unknown")
        year = series.get("year")
        
        if not tvdb_id:
            logger.warning("[SONARR_WEBHOOK] No TVDb ID found in payload")
            raise HTTPException(status_code=400, detail="Missing tvdbId in payload")
        
        logger.info(f"[SONARR_WEBHOOK] Processing: {title} ({year}) - TVDb ID: {tvdb_id}")
        
        # Get episodes from payload to determine which seasons were affected
        episodes = payload.get("episodes", [])
        affected_seasons = set()
        for ep in episodes:
            season_num = ep.get("seasonNumber")
            if season_num is not None:
                affected_seasons.add(season_num)
        
        logger.info(f"[SONARR_WEBHOOK] Affected seasons: {sorted(affected_seasons) if affected_seasons else 'Series only'}")
        
        auto_send = settings.WEBHOOK_AUTO_SEND
        auto_labels = settings.WEBHOOK_AUTO_LABELS.split(",") if settings.WEBHOOK_AUTO_LABELS else []
        
        return {
            "status": "received",
            "event_type": event_type,
            "title": title,
            "tvdb_id": tvdb_id,
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
    template_id: str = Query(..., description="Template ID to use for poster generation"),
    preset_id: str = Query(..., description="Preset ID to use"),
    event_types: str = Query("watched,added", description="Comma-separated list of events to process: watched, added, updated"),
    payload: Dict[str, Any] = Body(...)
):
    """
    Handle Tautulli webhook events (Plex library notifications).
    
    Expected payload includes:
    - event: Event type (library.new, library.update, etc.)
    - media_type: movie or episode
    - title, year, tmdb_id/tvdb_id
    
    Query params:
    - template_id: Required - Template to use
    - preset_id: Required - Preset to use
    - event_types: Comma-separated events to process (watched, added, updated)
    """
    try:
        event = payload.get("event", "").lower()
        media_type = payload.get("media_type", "").lower()
        
        logger.info(f"[TAUTULLI_WEBHOOK] Received {event} event, media_type={media_type}")
        
        # Map Tautulli event names to our categories
        event_map = {
            "library.new": "added",
            "library.update": "updated",
            "playback.stop": "watched"
        }
        
        event_category = event_map.get(event, "unknown")
        processing_events = [e.strip() for e in event_types.split(",")]
        
        # Check if we should process this event
        if event_category not in processing_events:
            logger.debug(f"[TAUTULLI_WEBHOOK] Event '{event_category}' not in processing list: {processing_events}")
            return {"status": "ignored", "reason": f"Event type {event_category} not in processing list"}
        
        if media_type not in ["movie", "episode"]:
            logger.warning(f"[TAUTULLI_WEBHOOK] Unknown media type: {media_type}")
            raise HTTPException(status_code=400, detail=f"Unknown media type: {media_type}")
        
        title = payload.get("title", "Unknown")
        year = payload.get("year")
        
        if media_type == "movie":
            tmdb_id = payload.get("tmdb_id")
            if not tmdb_id:
                logger.warning("[TAUTULLI_WEBHOOK] No TMDb ID found for movie")
                raise HTTPException(status_code=400, detail="Missing tmdb_id for movie")
            logger.info(f"[TAUTULLI_WEBHOOK] Movie: {title} ({year}) - TMDb ID: {tmdb_id}")
            
            return {
                "status": "received",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "tmdb_id": tmdb_id,
                "template_id": template_id,
                "preset_id": preset_id,
                "auto_send": settings.WEBHOOK_AUTO_SEND,
                "labels": [e.strip() for e in (settings.WEBHOOK_AUTO_LABELS or "").split(",") if e.strip()]
            }
        
        else:  # episode
            tvdb_id = payload.get("tvdb_id")
            if not tvdb_id:
                logger.warning("[TAUTULLI_WEBHOOK] No TVDb ID found for episode")
                raise HTTPException(status_code=400, detail="Missing tvdb_id for episode")
            
            season_num = payload.get("season")
            episode_num = payload.get("episode")
            
            logger.info(f"[TAUTULLI_WEBHOOK] Episode: {title} S{season_num}E{episode_num} - TVDb ID: {tvdb_id}")
            
            return {
                "status": "received",
                "event": event,
                "event_category": event_category,
                "media_type": media_type,
                "title": title,
                "tvdb_id": tvdb_id,
                "season": season_num,
                "episode": episode_num,
                "template_id": template_id,
                "preset_id": preset_id,
                "auto_send": settings.WEBHOOK_AUTO_SEND,
                "labels": [e.strip() for e in (settings.WEBHOOK_AUTO_LABELS or "").split(",") if e.strip()]
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
            "/webhook/tautulli?template_id=...&preset_id=...&event_types=watched,added,updated"
        ]
    }
