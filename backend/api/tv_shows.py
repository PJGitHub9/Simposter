import xml.etree.ElementTree as ET
from typing import List, Optional
from pathlib import Path
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from ..config import settings, plex_headers, logger, plex_session, POSTER_CACHE_DIR, extract_tmdb_id_from_metadata, extract_tvdb_id_from_metadata
from ..schemas import LabelsResponse
from ..tmdb_client import get_images_for_tv_show, get_tv_show_details, get_tv_season_images, TMDBError, get_tv_external_ids
from ..fanart_client import get_images_for_movie as get_fanart_images
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
    Return TV shows from Plex. Uses cached DB if it is fresh (default 15 minutes) unless force_refresh=true.
    """
    try:
        if not force_refresh and _tv_cache_fresh(max_age, library_id=library_id):
            cached = cache.get_cached_tv_shows(library_id=library_id)
            if cached:
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

        lib_ids = [library_id] if library_id else None
        shows = _get_plex_tv_shows(lib_ids)
        cache.refresh_tv_from_list(shows)
        return shows
    except Exception as e:
        logger.error(f"Failed to fetch TV shows: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch TV shows: {e}")


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
def api_tmdb_tv_images(tmdb_id: int, season: Optional[int] = None):
    """Get images for a TV show or specific season from TMDB."""
    try:
        if season is not None:
            # Get season-specific images
            details = get_tv_show_details(tmdb_id)
            season_imgs = get_tv_season_images(tmdb_id, season, details.get("original_language"))
            tv_imgs = get_images_for_tv_show(tmdb_id, details.get("original_language"))

            # For seasons, we want season posters but show-level backdrops and logos
            return {
                "posters": season_imgs.get("posters") or [],
                "backdrops": tv_imgs.get("backdrops") or [],
                "logos": tv_imgs.get("logos") or []
            }
        else:
            # Get show-level images
            details = get_tv_show_details(tmdb_id)
            tv_imgs = get_images_for_tv_show(tmdb_id, details.get("original_language"))
            tvdb_imgs = {"posters": [], "backdrops": [], "logos": []}
            tvdb_id: Optional[int] = None
            try:
                external_ids = get_tv_external_ids(tmdb_id)
                tvdb_id = external_ids.get("tvdb_id") or external_ids.get("id")
            except Exception:
                tvdb_id = None

            if tvdb_id:
                try:
                    tvdb_imgs = tvdb_client.get_series_images(tvdb_id)
                except Exception as tvdb_err:
                    logger.debug("[TVDB] Failed to fetch images for tvdb_id=%s: %s", tvdb_id, tvdb_err)

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
                "fanart": {"logos": [], "posters": [], "backdrops": []},
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
