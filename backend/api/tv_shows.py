import xml.etree.ElementTree as ET
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..config import settings, plex_headers, logger, plex_session, POSTER_CACHE_DIR, extract_tmdb_id_from_metadata, extract_tvdb_id_from_metadata
from ..schemas import LabelsResponse
from ..tmdb_client import get_images_for_tv_show, get_tv_show_details, get_tv_season_images, TMDBError, get_tv_external_ids
from ..fanart_client import get_images_for_movie as get_fanart_images, get_images_for_tv_show as get_fanart_tv_images
from .. import cache, database as db, tvdb_client

router = APIRouter()


def _get_plex_tv_shows(lib_ids: Optional[List[str]] = None) -> List[dict]:
    """Fetch TV shows from Plex server."""
    # Use TV show library IDs from settings if not specified
    if lib_ids is None:
        lib_ids = []
        tvLibMappings = getattr(settings, "PLEX_TV_LIBRARY_MAPPINGS", [])
        if tvLibMappings:
            lib_ids = [str(lib.get("id")) for lib in tvLibMappings if lib.get("id")]
        if not lib_ids:
            # Fallback to PLEX_TV_SHOW_LIB_IDS if it exists
            lib_ids = getattr(settings, "PLEX_TV_SHOW_LIB_IDS", [])

    shows = []
    for lib_id in lib_ids:
        try:
            url = f"{settings.PLEX_URL}/library/sections/{lib_id}/all"
            r = plex_session.get(url, headers=plex_headers(), timeout=30)
            r.raise_for_status()
            root = ET.fromstring(r.text)

            for directory in root.findall(".//Directory"):
                key = directory.get("ratingKey")
                title = directory.get("title")
                year = directory.get("year")
                added_at = directory.get("addedAt")

                if key and title:
                    shows.append({
                        "key": key,
                        "title": title,
                        "year": int(year) if year else None,
                        "addedAt": int(added_at) if added_at else None,
                        "library_id": lib_id
                    })
        except Exception as e:
            logger.error(f"Failed to fetch TV shows from library {lib_id}: {e}")

    return shows


def _tv_cache_fresh(max_age_seconds: int, library_id: Optional[str] = None) -> bool:
    stats = db.get_tv_cache_stats(library_id=library_id)
    if not stats.get("count"):
        return False
    ts = stats.get("max_updated")
    if not ts:
        return False
    try:
        last = datetime.fromisoformat(ts)
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
    except Exception:
        return False
    age = (datetime.now(timezone.utc) - last).total_seconds()
    return age <= max_age_seconds


def _poster_cache_path(rating_key: str, prefix: str = "tv") -> Optional[Path]:
    cache_dir = Path(POSTER_CACHE_DIR)
    for ext in ("jpg", "jpeg", "png", "webp"):
        candidate = cache_dir / f"{prefix}_{rating_key}.{ext}"
        if candidate.exists():
            return candidate
    return None


def _poster_cache_url(rating_key: str, cached: Path) -> str:
    ts = int(cached.stat().st_mtime)
    return f"/api/tv-show/{rating_key}/poster?raw=1&v={ts}"


def _save_poster_cache(rating_key: str, content: bytes, content_type: str, prefix: str = "tv") -> Optional[Path]:
    cache_dir = Path(POSTER_CACHE_DIR)
    ext = (content_type.split("/")[-1] if "/" in content_type else "jpg").lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    target = cache_dir / f"{prefix}_{rating_key}.{ext}"
    try:
        target.write_bytes(content)
        return target
    except Exception as e:
        logger.debug("[CACHE] failed to write TV show poster cache for %s: %s", rating_key, e)
        return None


def _remove_poster_cache(rating_key: str, prefix: str = "tv"):
    cache_dir = Path(POSTER_CACHE_DIR)
    removed = False
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = cache_dir / f"{prefix}_{rating_key}.{ext}"
        if p.exists():
            try:
                p.unlink()
                removed = True
            except Exception:
                pass
    return removed


def fetch_and_cache_tv_poster(rating_key: str, force_refresh: bool = False) -> Optional[Path]:
    """
    Fetch poster from cache or Plex and store it. Returns cached file path or None.
    """
    if force_refresh:
        _remove_poster_cache(rating_key, "tv")

    cached = _poster_cache_path(rating_key, "tv")
    if cached:
        return cached

    direct = f"{settings.PLEX_URL}/library/metadata/{rating_key}/thumb"

    # Try direct poster URL
    try:
        r = plex_session.get(direct, headers=plex_headers(), timeout=5)
        if r.status_code == 200:
            content_type = r.headers.get('content-type', 'image/jpeg')
            saved = _save_poster_cache(rating_key, r.content, content_type, "tv")
            return saved
    except Exception as e:
        logger.debug(f"Failed to fetch TV show poster directly for {rating_key}: {e}")

    # Fallback: parse metadata for thumb path
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for directory in root.findall(".//Directory"):
            thumb = directory.get("thumb")
            if thumb:
                thumb_url = f"{settings.PLEX_URL}{thumb}"
                poster_r = plex_session.get(thumb_url, headers=plex_headers(), timeout=5)
                if poster_r.status_code == 200:
                    content_type = poster_r.headers.get('content-type', 'image/jpeg')
                    saved = _save_poster_cache(rating_key, poster_r.content, content_type, "tv")
                    return saved
    except Exception as e:
        logger.debug(f"Failed to fetch TV show poster via metadata for {rating_key}: {e}")

    return None


@router.get("/tv-shows")
def api_tv_shows(force_refresh: bool = False, max_age: int = 900, library_id: str = None):
    """
    Return TV shows from cache. Always returns from cache - use /scan-library to refresh.
    The force_refresh parameter is deprecated but kept for backwards compatibility.
    """
    try:
        # Normalize library_id: treat "default" or empty string as None (fetch all libraries)
        if library_id in ("default", ""):
            library_id = None

        # Always return from cache (which includes labels populated by scans)
        cached = cache.get_cached_tv_shows(library_id=library_id)
        return [
            {
                "key": s["rating_key"],
                "title": s["title"],
                "year": s["year"],
                "addedAt": s["addedAt"],
                "poster": s.get("poster_url"),
                "tmdb_id": s.get("tmdb_id"),
                "tvdb_id": s.get("tvdb_id"),
                "labels": s.get("labels") or [],
                "seasons": s.get("seasons") or [],
                "updated_at": s.get("updated_at"),
                "library_id": s.get("library_id"),
            }
            for s in cached
        ]
    except Exception as e:
        logger.error(f"Failed to fetch TV shows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch TV shows: {e}")


@router.get("/tv-shows/labels/all")
def api_all_tv_labels(library_id: str = None):
    """Get all unique labels for TV shows (or all libraries if not specified)."""
    if library_id in ("default", ""):
        library_id = None
    
    cached = cache.get_cached_tv_shows(library_id=library_id)
    labels_set = set()
    
    for show in cached:
        if show.get("labels") and isinstance(show.get("labels"), list):
            labels_set.update(show.get("labels"))
    
    return {"labels": sorted(list(labels_set))}


@router.get("/tv-show/{rating_key}/poster")
def api_tv_show_poster(rating_key: str, request: Request, meta: bool = False, raw: bool = False, force_refresh: bool = False):
    """
    Return Plex TV show poster, cached on disk. If `meta=1` (or Accept: application/json),
    returns {"url": "<cached endpoint>"} instead of bytes so the UI can show without re-download.
    If force_refresh is true, it will re-fetch from Plex and overwrite cache.
    """

    def _cached_url(candidate: Path) -> str:
        ts = int(candidate.stat().st_mtime)
        return f"/api/tv-show/{rating_key}/poster?raw=1&v={ts}"

    def _return_file(candidate: Path, cache_header: str):
        resp = FileResponse(candidate)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        resp.headers["X-Poster-Cache"] = cache_header
        return resp

    wants_json = meta or "application/json" in (request.headers.get("accept") or "").lower()
    cached = fetch_and_cache_tv_poster(rating_key, force_refresh=force_refresh)
    cache_header = "miss" if force_refresh else ("hit" if cached else "miss")

    if cached:
        try:
            cache.update_tv_poster(rating_key, _cached_url(cached))
        except Exception:
            pass
        if raw and not wants_json:
            return _return_file(cached, cache_header)
        if wants_json:
            return JSONResponse({"url": _cached_url(cached)})
        return _return_file(cached, cache_header)

    # If still nothing, 404
    raise HTTPException(status_code=404, detail="Poster not found")


@router.get("/tv-show/{rating_key}/select-poster")
def api_tv_show_select_poster(
    rating_key: str,
    poster_filter: str = "all",
    season_index: Optional[int] = None
):
    """
    Select a poster for a TV show or season based on poster_filter (textless, text, all).
    Returns {"url": str, "has_text": bool} for the selected poster.
    """
    from ..assets.selection import pick_poster

    # Get TMDB/TVDB IDs for the show
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=6)
        r.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch TV show metadata: {e}")

    tmdb_id = extract_tmdb_id_from_metadata(r.text)
    tvdb_id = extract_tvdb_id_from_metadata(r.text)

    if tmdb_id and not tvdb_id:
        try:
            external_ids = get_tv_external_ids(tmdb_id)
            tvdb_id = external_ids.get("tvdb_id") or external_ids.get("id")
        except Exception:
            pass

    if not tmdb_id:
        raise HTTPException(status_code=404, detail="No TMDB ID found for TV show")

    # Get show details
    show_details = get_tv_show_details(tmdb_id)
    original_lang = show_details.get("original_language")

    # Fetch images based on whether we're selecting for a season or the series
    if season_index is not None:
        # Get season-specific images
        try:
            season_imgs = get_tv_season_images(tmdb_id, season_index, original_lang)
            season_posters = season_imgs.get("posters", [])
        except Exception as e:
            # Season 0 (specials) often don't have images on TMDB
            logger.warning("[TMDB] Failed to fetch season %d images: %s", season_index, e)
            season_posters = []

        # Also get series-level images as fallback
        series_imgs = get_images_for_tv_show(tmdb_id, original_lang)
        series_posters = series_imgs.get("posters", [])

        # Add TVDB season images if available
        if tvdb_id and settings.TVDB_API_KEY:
            try:
                tvdb_season_imgs = tvdb_client.get_season_images(int(tvdb_id), season_index)
                season_posters.extend(tvdb_season_imgs.get("posters", []))
            except Exception as e:
                logger.warning("[TVDB] Failed to fetch season images: %s", e)

        # Add TVDB series images to fallback
        if tvdb_id and settings.TVDB_API_KEY:
            try:
                tvdb_series_imgs = tvdb_client.get_series_images(int(tvdb_id))
                series_posters.extend(tvdb_series_imgs.get("posters", []))
            except Exception:
                pass

        # Combine for selection with textless fallback logic
        poster = None
        if poster_filter == "textless":
            # Try season textless first
            poster = next((p for p in season_posters if p.get("has_text") == False), None)
            # Fall back to series textless
            if not poster:
                poster = next((p for p in series_posters if p.get("has_text") == False), None)
                logger.debug("[SELECT-POSTER] Season %d: No textless season poster, using series textless", season_index)
        else:
            # Use combined list for other filters
            all_posters = season_posters + series_posters
            poster = pick_poster(all_posters, poster_filter)

        if not poster and (season_posters or series_posters):
            # Fallback to first available
            poster = season_posters[0] if season_posters else series_posters[0] if series_posters else None
    else:
        # Get series-level images only
        series_imgs = get_images_for_tv_show(tmdb_id, original_lang)
        posters = series_imgs.get("posters", [])

        # Add TVDB series images
        if tvdb_id and settings.TVDB_API_KEY:
            try:
                tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                posters.extend(tvdb_imgs.get("posters", []))
            except Exception:
                pass

        # Select poster with textless preference
        if poster_filter == "textless":
            poster = next((p for p in posters if p.get("has_text") == False), None)
        else:
            poster = pick_poster(posters, poster_filter)

        if not poster and posters:
            poster = posters[0]

    if not poster:
        raise HTTPException(status_code=404, detail="No poster found")

    return {
        "url": poster.get("url"),
        "has_text": poster.get("has_text", None)
    }


@router.get("/tv-show/{rating_key}/labels", response_model=LabelsResponse)
def api_tv_show_labels(rating_key: str):
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch labels for TV show %s: %s", rating_key, e)
        return LabelsResponse(labels=[])

    try:
        root = ET.fromstring(r.text)
    except Exception:
        return LabelsResponse(labels=[])

    labels = set()

    # Modern Plex: <Tag tagType="label">
    for tag in root.findall(".//Tag"):
        tag_type = (tag.get("tagType") or tag.get("type") or "").lower()
        if tag_type == "label":
            name = tag.get("tag")
            if name:
                labels.add(name)

    # Some versions: <Label tag="...">
    for tag in root.findall(".//Label"):
        name = tag.get("tag")
        if name:
            labels.add(name)

    labels_sorted = sorted(labels)
    cache.update_tv_labels(rating_key, labels_sorted)
    return LabelsResponse(labels=labels_sorted)


@router.get("/tv-show/{rating_key}/tmdb")
def api_tv_show_tmdb(rating_key: str):
    """Get TMDB ID for a TV show."""
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"

    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=6)
        r.raise_for_status()
        logger.debug("[PLEX] GET %s -> %s", url, r.status_code)
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch metadata for TV show %s: %s", rating_key, e)
        return {"tmdb_id": None, "tvdb_id": None}

    tmdb_id = extract_tmdb_id_from_metadata(r.text)
    tvdb_id = extract_tvdb_id_from_metadata(r.text)

    if tmdb_id and not tvdb_id:
        try:
            external_ids = get_tv_external_ids(tmdb_id)
            tvdb_id = external_ids.get("tvdb_id") or external_ids.get("id")
        except Exception:
            tvdb_id = tvdb_id

    cache.update_tv_tmdb(rating_key, tmdb_id)
    if tvdb_id:
        cache.update_tv_tvdb(rating_key, tvdb_id)
    return {"tmdb_id": tmdb_id, "tvdb_id": tvdb_id}


@router.get("/tv-show/{rating_key}/seasons")
def api_tv_show_seasons(rating_key: str, force_refresh: bool = False):
    """Get seasons for a TV show from Plex (cached if available)."""
    if not force_refresh:
        cached = db.get_cached_tv_show(rating_key)
        if cached and cached.get("seasons"):
            return {"seasons": cached["seasons"]}

    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/children"

    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)

        seasons = []
        for directory in root.findall(".//Directory"):
            season_key = directory.get("ratingKey")
            season_title = directory.get("title", "")
            season_index = directory.get("index")
            thumb = directory.get("thumb")

            if season_key and season_index is not None:
                seasons.append({
                    "key": season_key,
                    "title": season_title,
                    "index": int(season_index),
                    "thumb": thumb
                })

        # Sort by season index
        seasons.sort(key=lambda s: s["index"])

        cache.update_tv_seasons(rating_key, seasons)
        logger.debug("[PLEX] TV show %s has %d seasons", rating_key, len(seasons))
        return {"seasons": seasons}
    except Exception as e:
        logger.error(f"Failed to fetch seasons for TV show {rating_key}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch seasons: {e}")


@router.get("/tmdb/tv/{tmdb_id}/images")
def api_tmdb_tv_images(tmdb_id: int, season: Optional[int] = None, tvdb_id: Optional[int] = None):
    """Get images for a TV show or specific season from TMDB."""
    try:
        if season is not None:
            # Get season-specific images
            details = get_tv_show_details(tmdb_id)
            season_imgs = get_tv_season_images(tmdb_id, season, details.get("original_language"))
            tv_imgs = get_images_for_tv_show(tmdb_id, details.get("original_language"))

            # TVDB images (season-specific if available)
            tvdb_imgs = {"posters": [], "backdrops": [], "logos": []}
            fanart_imgs = {"posters": [], "backdrops": [], "logos": []}
            provided_tvdb_id = tvdb_id
            try:
                external_ids = get_tv_external_ids(tmdb_id)
                tvdb_id = provided_tvdb_id or external_ids.get("tvdb_id") or external_ids.get("id")
            except Exception:
                tvdb_id = provided_tvdb_id or None

            logger.debug(
                "[TVDB] Series external ids -> tvdb_id=%s api_key_present=%s",
                tvdb_id,
                bool(getattr(settings, "TVDB_API_KEY", "")),
            )

            logger.debug(
                "[TVDB] Season %s external ids -> tvdb_id=%s api_key_present=%s",
                season,
                tvdb_id,
                bool(getattr(settings, "TVDB_API_KEY", "")),
            )
            if tvdb_id and settings.TVDB_API_KEY:
                try:
                    logger.info("[TVDB] Fetching season %d images for tvdb_id=%s", season, tvdb_id)
                    # Fetch season-specific images from TVDB
                    tvdb_imgs = tvdb_client.get_season_images(int(tvdb_id), season)
                    logger.debug("[TVDB] Season %d result: %d posters, %d logos, %d backdrops",
                                season,
                                len(tvdb_imgs.get("posters", [])),
                                len(tvdb_imgs.get("logos", [])),
                                len(tvdb_imgs.get("backdrops", [])))
                except Exception as tvdb_err:
                    logger.warning("[TVDB] Failed to fetch season %d images for tvdb_id=%s: %s", season, tvdb_id, tvdb_err)
            else:
                if not tvdb_id:
                    logger.debug("[TVDB] No TVDB ID found for tmdb_id=%s", tmdb_id)
                if not settings.TVDB_API_KEY:
                    logger.debug("[TVDB] TVDB_API_KEY not configured")
                if tvdb_id and not settings.TVDB_API_KEY:
                    logger.info("[TVDB] TVDB ID present (%s) but TVDB_API_KEY is missing; skipping TVDB assets for season", tvdb_id)
                logger.debug("[TVDB] Skipping TVDB season fetch (tvdb_id=%s key_present=%s)", tvdb_id, bool(getattr(settings, "TVDB_API_KEY", "")))
                logger.debug("[TVDB] Skipping TVDB series fetch (tvdb_id=%s key_present=%s)", tvdb_id, bool(getattr(settings, "TVDB_API_KEY", "")))

            if tvdb_id and settings.FANART_API_KEY:
                try:
                    fanart_imgs = get_fanart_tv_images(int(tvdb_id))
                    logger.debug("[FANART] Season %d fanart result: posters=%d logos=%d backdrops=%d",
                                season,
                                len(fanart_imgs.get("posters", [])),
                                len(fanart_imgs.get("logos", [])),
                                len(fanart_imgs.get("backdrops", [])))
                except Exception as fanart_err:
                    logger.warning("[FANART] Failed to fetch season %d fanart for tvdb_id=%s: %s", season, tvdb_id, fanart_err)

            # Get API order from settings
            from ..api.ui_settings import _read_settings
            try:
                ui_settings = _read_settings(include_env=False)
                api_order = ui_settings.apiOrder or ["tmdb", "fanart", "tvdb"]
            except Exception:
                api_order = ["tmdb", "fanart", "tvdb"]

            image_sources = {
                "tmdb": {"logos": tv_imgs.get("logos") or [], "posters": season_imgs.get("posters") or [], "backdrops": tv_imgs.get("backdrops") or []},
                "fanart": fanart_imgs,
                "tvdb": tvdb_imgs,
            }

            merged_logos: List[dict] = []
            merged_posters: List[dict] = []
            merged_backdrops: List[dict] = []
            for source in api_order:
                if source in image_sources:
                    merged_logos.extend(image_sources[source]["logos"])
                    merged_posters.extend(image_sources[source]["posters"])
                    merged_backdrops.extend(image_sources[source]["backdrops"])

            return {
                "posters": merged_posters,
                "backdrops": merged_backdrops,
                "logos": merged_logos
            }
        else:
            # Get show-level images
            details = get_tv_show_details(tmdb_id)
            tv_imgs = get_images_for_tv_show(tmdb_id, details.get("original_language"))
            tvdb_imgs = {"posters": [], "backdrops": [], "logos": []}
            fanart_imgs = {"posters": [], "backdrops": [], "logos": []}
            provided_tvdb_id = tvdb_id

            try:
                external_ids = get_tv_external_ids(tmdb_id)
                tvdb_id = provided_tvdb_id or external_ids.get("tvdb_id") or external_ids.get("id")
            except Exception:
                tvdb_id = provided_tvdb_id or None

            # Only call TVDB if key is set and we have an id
            if tvdb_id and settings.TVDB_API_KEY:
                try:
                    logger.info("[TVDB] Fetching series images for tvdb_id=%s", tvdb_id)
                    tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                    logger.info("[TVDB] Series images result: %d posters, %d logos, %d backdrops",
                                len(tvdb_imgs.get("posters", [])),
                                len(tvdb_imgs.get("logos", [])),
                                len(tvdb_imgs.get("backdrops", [])))
                except Exception as tvdb_err:
                    logger.warning("[TVDB] Failed to fetch images for tvdb_id=%s: %s", tvdb_id, tvdb_err)
            else:
                if not tvdb_id:
                    logger.debug("[TVDB] No TVDB ID found for tmdb_id=%s", tmdb_id)
                if not settings.TVDB_API_KEY:
                    logger.debug("[TVDB] TVDB_API_KEY not configured")
                if tvdb_id and not settings.TVDB_API_KEY:
                    logger.info("[TVDB] TVDB ID present (%s) but TVDB_API_KEY is missing; skipping TVDB assets for series", tvdb_id)

            if tvdb_id and settings.FANART_API_KEY:
                try:
                    fanart_imgs = get_fanart_tv_images(int(tvdb_id))
                    logger.debug("[FANART] Series fanart result: posters=%d logos=%d backdrops=%d",
                                len(fanart_imgs.get("posters", [])),
                                len(fanart_imgs.get("logos", [])),
                                len(fanart_imgs.get("backdrops", [])))
                except Exception as fanart_err:
                    logger.warning("[FANART] Failed to fetch fanart for tvdb_id=%s: %s", tvdb_id, fanart_err)
            else:
                if not tvdb_id:
                    logger.debug("[FANART] No TVDB ID available for Fanart.tv lookup (tmdb_id=%s)", tmdb_id)
                if not settings.FANART_API_KEY:
                    logger.debug("[FANART] FANART_API_KEY not configured")

            # Get API order from settings
            from ..api.ui_settings import _read_settings
            try:
                ui_settings = _read_settings(include_env=False)
                api_order = ui_settings.apiOrder or ["tmdb", "fanart", "tvdb"]
            except Exception:
                api_order = ["tmdb", "fanart", "tvdb"]

            # Build image sources dictionary
            image_sources = {
                "tmdb": {"logos": tv_imgs.get("logos") or [], "posters": tv_imgs.get("posters") or [], "backdrops": tv_imgs.get("backdrops") or []},
                "fanart": fanart_imgs,
                "tvdb": tvdb_imgs,
            }

            # Merge images based on API order
            merged_logos = []
            merged_posters = []
            merged_backdrops = []

            for source in api_order:
                if source in image_sources:
                    merged_logos.extend(image_sources[source]["logos"])
                    merged_posters.extend(image_sources[source]["posters"])
                    merged_backdrops.extend(image_sources[source]["backdrops"])

            logger.info(
                "[IMAGES] TV show tmdb_id=%s posters=%d backdrops=%d logos=%d",
                tmdb_id,
                len(merged_posters),
                len(merged_backdrops),
                len(merged_logos),
            )

            return {
                "posters": merged_posters,
                "backdrops": merged_backdrops,
                "logos": merged_logos,
            }
    except TMDBError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tmdb/tv/{tmdb_id}/details")
def api_tmdb_tv_details(tmdb_id: int):
    """Get details for a TV show from TMDB."""
    try:
        details = get_tv_show_details(tmdb_id)
        return details
    except TMDBError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/plex/upload-season-poster")
async def api_upload_season_poster(request: Request):
    """Upload a season poster to Plex directly from an image URL."""
    import requests
    from io import BytesIO
    
    try:
        body = await request.json()
        rating_key = body.get("rating_key")
        image_url = body.get("image_url")
        
        if not rating_key or not image_url:
            raise HTTPException(status_code=400, detail="rating_key and image_url are required")
        
        if not settings.PLEX_URL or not settings.PLEX_TOKEN:
            raise HTTPException(status_code=400, detail="PLEX_URL and PLEX_TOKEN must be configured")
        
        # Download the image
        logger.info(f"[SEASON] Downloading season poster from {image_url}")
        img_response = requests.get(image_url, timeout=30)
        img_response.raise_for_status()
        
        # Upload to Plex
        plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
        headers = {
            "X-Plex-Token": settings.PLEX_TOKEN,
            "Content-Type": "image/jpeg",
        }
        
        logger.info(f"[SEASON] Uploading poster to Plex for season {rating_key}")
        upload_response = requests.post(plex_url, headers=headers, data=img_response.content, timeout=20)
        upload_response.raise_for_status()
        
        logger.info(f"[SEASON] Successfully uploaded poster for season {rating_key}")
        return {"status": "ok", "message": "Season poster uploaded successfully"}
        
    except requests.RequestException as e:
        logger.error(f"[SEASON] Failed to upload poster: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload poster: {str(e)}")
    except Exception as e:
        logger.error(f"[SEASON] Unexpected error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tv-show/{rating_key}/select-poster")
def api_select_tv_poster(
    rating_key: str,
    poster_filter: str = "all",
    season_index: Optional[int] = None,
    library_id: Optional[str] = None
):
    """
    Select and return the best poster URL for a TV show or season based on filter preferences.
    This respects poster_filter settings (textless, text, all) and returns TMDB/TVDB poster URLs.
    
    Args:
        rating_key: Plex rating key for the show
        poster_filter: 'textless', 'text', or 'all' (default: 'all')
        season_index: If provided, selects a season poster; otherwise selects series poster
        library_id: Optional library ID for context
    
    Returns:
        {"url": "<poster_url>", "has_text": bool, "source": "tmdb|tvdb"}
    """
    try:
        from ..assets.selection import pick_poster
        
        # Get show metadata to find TMDB/TVDB IDs
        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        
        tmdb_id = extract_tmdb_id_from_metadata(r.text)
        tvdb_id = extract_tvdb_id_from_metadata(r.text)
        
        if not tmdb_id:
            raise HTTPException(status_code=404, detail="No TMDB ID found for this show")
        
        # Get show details for original language
        show_details = get_tv_show_details(tmdb_id)
        original_language = show_details.get("original_language")
        
        posters = []
        
        # Fetch posters based on whether we're selecting for season or series
        if season_index is not None:
            # Get season-specific posters
            logger.info("[SELECT] Fetching season %d posters for show %s (TMDB: %s)", season_index, rating_key, tmdb_id)
            try:
                season_imgs = get_tv_season_images(tmdb_id, season_index, original_language)
                posters.extend(season_imgs.get("posters", []))
            except Exception as e:
                logger.warning("[SELECT] Failed to get TMDB season images: %s", e)
            
            # Also get TVDB season posters if available
            if tvdb_id and settings.TVDB_API_KEY:
                try:
                    tvdb_season_imgs = tvdb_client.get_season_images(int(tvdb_id), season_index)
                    posters.extend(tvdb_season_imgs.get("posters", []))
                except Exception as e:
                    logger.warning("[SELECT] Failed to get TVDB season images: %s", e)
            
            # Fallback to series posters if no season posters found
            if not posters:
                logger.info("[SELECT] No season posters found, falling back to series posters")
                series_imgs = get_images_for_tv_show(tmdb_id, original_language)
                posters.extend(series_imgs.get("posters", []))
        else:
            # Get series-level posters
            logger.info("[SELECT] Fetching series posters for show %s (TMDB: %s)", rating_key, tmdb_id)
            series_imgs = get_images_for_tv_show(tmdb_id, original_language)
            posters.extend(series_imgs.get("posters", []))
            
            # Also get TVDB series posters if available
            if tvdb_id and settings.TVDB_API_KEY:
                try:
                    tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                    posters.extend(tvdb_imgs.get("posters", []))
                except Exception as e:
                    logger.warning("[SELECT] Failed to get TVDB series images: %s", e)
        
        logger.info("[SELECT] Found %d total posters with filter '%s'", len(posters), poster_filter)
        
        if not posters:
            raise HTTPException(status_code=404, detail="No posters found")
        
        # Apply filter selection logic
        selected_poster = None
        if poster_filter == "textless":
            # Prefer textless posters
            selected_poster = next((p for p in posters if p.get("has_text") == False), None)
            if not selected_poster:
                logger.info("[SELECT] No textless poster found, using first available")
                selected_poster = posters[0]
        else:
            selected_poster = pick_poster(posters, poster_filter)
            if not selected_poster:
                selected_poster = posters[0]
        
        logger.info("[SELECT] Selected poster: has_text=%s, url=%s", selected_poster.get("has_text"), selected_poster.get("url")[:100])
        
        return {
            "url": selected_poster.get("url"),
            "has_text": selected_poster.get("has_text", None),
            "source": selected_poster.get("source", "unknown")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("[SELECT] Error selecting poster: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
