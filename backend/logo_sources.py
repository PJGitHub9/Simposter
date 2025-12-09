# backend/logo_sources.py
from typing import List, Dict, Any, Optional
from .config import logger
from . import tmdb_client, fanart_client, database as db


def get_logos_merged(
    tmdb_id: int,
    logo_source: Optional[str] = None,
    original_language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetch logos from TMDB and/or Fanart.tv based on source priority.

    Args:
        tmdb_id: TMDB movie ID
        logo_source: Source priority mode. If None, uses global setting.
                    Options: "tmdb", "fanart", "tmdb_fanart", "fanart_tmdb", "both"
        original_language: Movie's original language (for TMDB)

    Returns:
        List of logo dictionaries with 'source' field indicating origin
    """
    # Get logo source preference
    if not logo_source:
        logo_source = db.get_setting("pref.logo_source") or "tmdb_fanart"
        logger.info("[LOGO_SOURCES] Using logo source from database: %s", logo_source)
    else:
        logger.info("[LOGO_SOURCES] Using logo source from override: %s", logo_source)

    logger.debug("[LOGO_SOURCES] Fetching logos for tmdb_id=%s with source=%s", tmdb_id, logo_source)

    tmdb_logos = []
    fanart_logos = []

    # Fetch from sources based on priority
    if logo_source == "tmdb":
        # TMDB only
        imgs = tmdb_client.get_images_for_movie(tmdb_id, original_language)
        tmdb_logos = imgs.get("logos", [])
        for logo in tmdb_logos:
            logo["source"] = "tmdb"
        return tmdb_logos

    elif logo_source == "fanart":
        # Fanart.tv only
        fanart_logos = fanart_client.get_logos_for_movie(tmdb_id)
        logger.info("[LOGO_SOURCES] Fanart-only returned %d logos", len(fanart_logos))
        return fanart_logos

    elif logo_source == "tmdb_fanart":
        # TMDB first, then Fanart as fallback
        imgs = tmdb_client.get_images_for_movie(tmdb_id, original_language)
        tmdb_logos = imgs.get("logos", [])
        for logo in tmdb_logos:
            logo["source"] = "tmdb"

        if tmdb_logos:
            logger.debug("[LOGO_SOURCES] Using %d TMDB logos (fallback not needed)", len(tmdb_logos))
            return tmdb_logos

        logger.debug("[LOGO_SOURCES] No TMDB logos, fetching from Fanart.tv")
        fanart_logos = fanart_client.get_logos_for_movie(tmdb_id)
        logger.info("[LOGO_SOURCES] Fallback to Fanart.tv returned %d logos", len(fanart_logos))
        return fanart_logos

    elif logo_source == "fanart_tmdb":
        # Fanart first, then TMDB as fallback
        fanart_logos = fanart_client.get_logos_for_movie(tmdb_id)

        if fanart_logos:
            logger.debug("[LOGO_SOURCES] Using %d Fanart logos (fallback not needed)", len(fanart_logos))
            return fanart_logos

        logger.debug("[LOGO_SOURCES] No Fanart logos, fetching from TMDB")
        imgs = tmdb_client.get_images_for_movie(tmdb_id, original_language)
        tmdb_logos = imgs.get("logos", [])
        for logo in tmdb_logos:
            logo["source"] = "tmdb"
        logger.info("[LOGO_SOURCES] Fanart miss; TMDB fallback returned %d logos", len(tmdb_logos))
        return tmdb_logos

    elif logo_source == "both":
        # Merge results from both sources
        imgs = tmdb_client.get_images_for_movie(tmdb_id, original_language)
        tmdb_logos = imgs.get("logos", [])
        for logo in tmdb_logos:
            logo["source"] = "tmdb"

        fanart_logos = fanart_client.get_logos_for_movie(tmdb_id)

        # Merge: Fanart HD logos first, then TMDB, then remaining Fanart
        merged = []

        # Add Fanart HD logos first (they're high quality)
        merged.extend(fanart_logos)

        # Add TMDB logos
        merged.extend(tmdb_logos)

        logger.debug(
            "[LOGO_SOURCES] Merged logos: %d from Fanart + %d from TMDB = %d total",
            len(fanart_logos),
            len(tmdb_logos),
            len(merged)
        )

        return merged

    else:
        # Default to tmdb_fanart if invalid option
        logger.warning("[LOGO_SOURCES] Invalid logo_source '%s', defaulting to tmdb_fanart", logo_source)
        return get_logos_merged(tmdb_id, "tmdb_fanart", original_language)
