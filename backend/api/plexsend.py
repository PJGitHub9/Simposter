import requests
from fastapi import APIRouter, HTTPException
from io import BytesIO

from ..config import settings, plex_headers, plex_remove_label, logger
from ..rendering import render_poster_image
from ..schemas import PlexSendRequest
from .movies import fetch_and_cache_poster

router = APIRouter()


@router.post("/plex/send")
def api_plex_send(req: PlexSendRequest):
    # Validate Plex settings
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")

    # Allow ANY URL (TMDB, uploaded, custom)
    if not (
        req.background_url.startswith("http://")
        or req.background_url.startswith("https://")
        or req.background_url.startswith("/uploads/")
    ):
        raise HTTPException(400, "Invalid background_url")

    # Render poster using template + preset
    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        req.options,
    )

    # Encode for Plex
    buf = BytesIO()
    # Get JPEG quality from settings
    quality = 95
    try:
        from .. import database as db
        ui_settings_data = db.get_ui_settings()
        if ui_settings_data and "imageQuality" in ui_settings_data:
            quality = ui_settings_data["imageQuality"].get("jpgQuality", 95)
    except Exception:
        pass
    img.convert("RGB").save(buf, "JPEG", quality=quality)
    payload = buf.getvalue()

    plex_url = f"{settings.PLEX_URL}/library/metadata/{req.rating_key}/posters"
    headers = {
        "X-Plex-Token": settings.PLEX_TOKEN,
        "Content-Type": "image/jpeg",
    }

    logger.info("[PLEX] Uploading poster rating_key=%s template=%s preset=%s", req.rating_key, req.template_id, req.preset_id)
    try:
        r = requests.post(plex_url, headers=headers, data=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logger.error("[PLEX] Upload failed rating_key=%s err=%s", req.rating_key, e)
        raise

    # Remove labels if requested
    for label in req.labels or []:
        plex_remove_label(req.rating_key, label)

    # Refresh cached poster so future calls use the updated image
    try:
        fetch_and_cache_poster(req.rating_key, force_refresh=True)
    except Exception as e:
        logger.debug("[CACHE] poster refresh after send failed for %s: %s", req.rating_key, e)

    # Record history entry for manual send
    try:
        from .. import database as db
        import xml.etree.ElementTree as ET

        # Get metadata from Plex API directly
        movie_details = {}
        try:
            metadata_url = f"{settings.PLEX_URL}/library/metadata/{req.rating_key}"
            resp = requests.get(metadata_url, headers=plex_headers(), timeout=5)
            if resp.ok:
                root = ET.fromstring(resp.text)
                # Could be Video (movie/episode) or Directory (show/season)
                item = root.find('.//Video') or root.find('.//Directory')
                if item is not None:
                    title = item.get('title', '')
                    year = item.get('year')
                    parent_title = item.get('parentTitle')  # For seasons/episodes
                    grandparent_title = item.get('grandparentTitle')  # For episodes

                    # Build display title based on type
                    if grandparent_title:  # Episode
                        title = f"{grandparent_title} - {parent_title} - {title}"
                    elif parent_title:  # Season
                        title = f"{parent_title} - {title}"

                    movie_details = {
                        'title': title,
                        'year': int(year) if year and year.isdigit() else None,
                        'library_id': req.library_id
                    }
        except Exception as plex_err:
            logger.debug("[HISTORY] Failed to get metadata from Plex: %s", plex_err)

            # Fallback to cache
            try:
                from .. import cache
                cached_movies = cache.get_cached_movies()
                for m in cached_movies:
                    if m.get("rating_key") == req.rating_key:
                        movie_details = m
                        break
                if not movie_details:
                    cached_tv = cache.get_cached_tv_shows()
                    for s in cached_tv:
                        if s.get("rating_key") == req.rating_key:
                            movie_details = s
                            break
            except Exception as cache_err:
                logger.debug("[HISTORY] Failed to get details from cache: %s", cache_err)

        db.record_poster_history(
            rating_key=req.rating_key,
            library_id=req.library_id or movie_details.get("library_id"),
            title=movie_details.get("title"),
            year=movie_details.get("year"),
            template_id=req.template_id,
            preset_id=req.preset_id,
            action="sent_to_plex",
            save_path=None,
            source='manual',
        )
    except Exception as history_err:
        logger.debug("[HISTORY] Failed to record manual send: %s", history_err)

    logger.info(f"Sent poster to Plex for ratingKey={req.rating_key}")
    return {"status": "ok"}
