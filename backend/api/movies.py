import xml.etree.ElementTree as ET
from typing import List, Optional
from pathlib import Path
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Body
from fastapi.responses import Response, FileResponse, JSONResponse
from PIL import Image

import requests
from ..config import settings, plex_headers, logger, get_plex_movies, get_movie_tmdb_id, plex_session, POSTER_CACHE_DIR
from .. import cache, database as db
from ..schemas import Movie, MovieTMDbResponse, LabelsResponse, LabelsRemoveRequest
from ..tmdb_client import get_images_for_movie, get_movie_details, get_movie_external_ids, TMDBError
from ..fanart_client import get_images_for_movie as get_fanart_images
from .. import tvdb_client

router = APIRouter()

scan_status = {
    "state": "idle",
    "total": 0,
    "processed": 0,
    "current": "",
    "started_at": None,
    "finished_at": None,
    "error": None,
}


def _read_image_metadata(file_path: Path) -> dict:
    """
    Read library metadata from image file.
    Returns dict with library_id, library_name, movie_title, and movie_year if found.
    """
    try:
        img = Image.open(file_path)

        # Try to extract from PNG metadata first
        if hasattr(img, 'text'):
            library_id = img.text.get('simposter_library_id')
            library_name = img.text.get('simposter_library_name')
            movie_title = img.text.get('simposter_movie_title')
            movie_year = img.text.get('simposter_movie_year')
            if library_id or movie_title:
                result = {}
                if library_id:
                    result['library_id'] = library_id
                    result['library_name'] = library_name or library_id
                if movie_title:
                    result['movie_title'] = movie_title
                if movie_year:
                    result['movie_year'] = movie_year
                return result

        # Try from EXIF data (for JPEG files)
        try:
            exif = img.getexif()
            if exif and 0x9286 in exif:  # UserComment field
                import json
                user_comment = exif[0x9286]
                # Handle both bytes and string
                if isinstance(user_comment, bytes):
                    user_comment = user_comment.decode('utf-8', errors='ignore')
                try:
                    metadata = json.loads(user_comment)
                    library_id = metadata.get('simposter_library_id')
                    library_name = metadata.get('simposter_library_name')
                    movie_title = metadata.get('simposter_movie_title')
                    movie_year = metadata.get('simposter_movie_year')
                    if library_id or movie_title:
                        result = {}
                        if library_id:
                            result['library_id'] = library_id
                            result['library_name'] = library_name or library_id
                        if movie_title:
                            result['movie_title'] = movie_title
                        if movie_year:
                            result['movie_year'] = movie_year
                        return result
                except (json.JSONDecodeError, TypeError):
                    pass
        except Exception:
            pass

        # Try from img.info dict (fallback)
        if hasattr(img, 'info'):
            library_id = img.info.get('simposter_library_id')
            library_name = img.info.get('simposter_library_name')
            movie_title = img.info.get('simposter_movie_title')
            movie_year = img.info.get('simposter_movie_year')
            if library_id or movie_title:
                result = {}
                if library_id:
                    result['library_id'] = library_id
                    result['library_name'] = library_name or library_id
                if movie_title:
                    result['movie_title'] = movie_title
                if movie_year:
                    result['movie_year'] = movie_year
                return result

        return {}
    except Exception as e:
        logger.debug(f"[METADATA] Failed to read metadata from {file_path}: {e}")
        return {}


def _poster_cache_path(rating_key: str) -> Optional[Path]:
    cache_dir = Path(POSTER_CACHE_DIR)
    for ext in ("jpg", "jpeg", "png", "webp"):
        candidate = cache_dir / f"{rating_key}.{ext}"
        if candidate.exists():
            return candidate
    return None


def _poster_cache_url(rating_key: str, cached: Path) -> str:
    ts = int(cached.stat().st_mtime)
    return f"/api/movie/{rating_key}/poster?raw=1&v={ts}"


def _save_poster_cache(rating_key: str, content: bytes, content_type: str) -> Optional[Path]:
    cache_dir = Path(POSTER_CACHE_DIR)
    ext = (content_type.split("/")[-1] if "/" in content_type else "jpg").lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    target = cache_dir / f"{rating_key}.{ext}"
    try:
        target.write_bytes(content)
        return target
    except Exception as e:
        logger.debug("[CACHE] failed to write poster cache for %s: %s", rating_key, e)
        return None


def _remove_poster_cache(rating_key: str):
    cache_dir = Path(POSTER_CACHE_DIR)
    removed = False
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = cache_dir / f"{rating_key}.{ext}"
        if p.exists():
            try:
                p.unlink()
                removed = True
            except Exception:
                pass
    return removed


def fetch_and_cache_poster(rating_key: str, force_refresh: bool = False) -> Optional[Path]:
    """
    Fetch poster from cache or Plex and store it. Returns cached file path or None.
    """
    if force_refresh:
        _remove_poster_cache(rating_key)

    cached = _poster_cache_path(rating_key)
    if cached:
        return cached

    direct = f"{settings.PLEX_URL}/library/metadata/{rating_key}/thumb"

    # Try direct poster URL
    try:
        r = plex_session.get(direct, headers=plex_headers(), timeout=5)
        if r.status_code == 200:
            content_type = r.headers.get('content-type', 'image/jpeg')
            try:
                cache.update_poster(rating_key, direct)
            except Exception:
                logger.debug("[CACHE] update_poster failed for %s", rating_key, exc_info=True)
            saved = _save_poster_cache(rating_key, r.content, content_type)
            return saved
    except Exception as e:
        logger.debug(f"Failed to fetch poster directly for {rating_key}: {e}")

    # Fallback: parse metadata for thumb path
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for video in root.findall(".//Video"):
            thumb = video.get("thumb")
            if thumb:
                thumb_url = f"{settings.PLEX_URL}{thumb}"
                poster_r = plex_session.get(thumb_url, headers=plex_headers(), timeout=5)
                if poster_r.status_code == 200:
                    content_type = poster_r.headers.get('content-type', 'image/jpeg')
                    try:
                        cache.update_poster(rating_key, thumb_url)
                    except Exception:
                        logger.debug("[CACHE] update_poster failed for %s", rating_key, exc_info=True)
                    saved = _save_poster_cache(rating_key, poster_r.content, content_type)
                    return saved
    except Exception as e:
        logger.debug(f"Failed to fetch poster via metadata for {rating_key}: {e}")

    return None


@router.get("/test-plex-connection")
def test_plex_connection(plex_url: str = None, plex_token: str = None):
    """Test Plex server connection and return diagnostics."""
    # Use provided parameters or fall back to settings
    test_url = plex_url or settings.PLEX_URL
    test_token = plex_token or settings.PLEX_TOKEN

    try:
        url = f"{test_url}/library/sections"
        logger.info(f"[TEST] Testing Plex connection to {test_url}")
        logger.info(f"[TEST] PLEX_VERIFY_TLS = {settings.PLEX_VERIFY_TLS}")

        headers = {"X-Plex-Token": test_token} if test_token else {}
        r = plex_session.get(url, headers=headers, timeout=10)
        r.raise_for_status()

        root = ET.fromstring(r.text)
        sections = []
        for directory in root.findall(".//Directory"):
            sections.append({
                "title": directory.get("title"),
                "key": directory.get("key"),
                "type": directory.get("type")
            })

        return {
            "status": "ok",
            "plex_url": test_url,
            "has_token": bool(test_token),
            "verify_tls": settings.PLEX_VERIFY_TLS,
            "sections": sections
        }
    except requests.exceptions.SSLError as e:
        logger.error(f"[TEST] SSL Error: {e}")
        return {
            "status": "error",
            "error": "SSL Certificate Error",
            "message": f"SSL verification failed. Try setting PLEX_VERIFY_TLS=false in your .env file. Error: {str(e)}",
            "plex_url": test_url,
            "verify_tls": settings.PLEX_VERIFY_TLS
        }
    except requests.exceptions.ConnectionError as e:
        logger.error(f"[TEST] Connection Error: {e}")
        hint = ""
        url_lower = test_url.lower()
        if "localhost" in url_lower or "127.0.0.1" in url_lower:
            hint = " (inside Docker containers localhost points to the container; use the host IP or host networking)"
        return {
            "status": "error",
            "error": "Connection Error",
            "message": f"Could not connect to Plex server. Check PLEX_URL and network connectivity{hint}. Error: {str(e)}",
            "plex_url": test_url
        }
    except Exception as e:
        logger.error(f"[TEST] Plex connection test failed: {e}")
        return {
            "status": "error",
            "error": str(type(e).__name__),
            "message": str(e),
            "plex_url": test_url
        }


def _cache_fresh(max_age_seconds: int, library_id: Optional[str] = None) -> bool:
    stats = db.get_movie_cache_stats(library_id=library_id)
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


def _collections_cache_fresh(max_age_seconds: int, library_id: Optional[str] = None) -> bool:
    stats = cache.get_collection_cache_stats(library_id=library_id)
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


# --- Plex Collections ---
def _get_plex_collections(lib_ids: Optional[List[str]] = None) -> List[dict]:
    """Fetch collections from Plex libraries."""
    if lib_ids is None:
        lib_ids = getattr(settings, "PLEX_MOVIE_LIB_IDS", []) or [settings.PLEX_MOVIE_LIBRARY_NAME]

    items: List[dict] = []
    for lib_id in lib_ids:
        try:
            url = f"{settings.PLEX_URL}/library/sections/{lib_id}/all?type=18"
            r = plex_session.get(url, headers=plex_headers(), timeout=10)
            r.raise_for_status()
            root = ET.fromstring(r.text)

            for directory in root.findall(".//Directory"):
                key = directory.get("ratingKey")
                title = directory.get("title")
                thumb = directory.get("thumb")
                added_at = directory.get("addedAt")

                if not key or not title:
                    continue

                # Prefer cached poster if we already have it; otherwise fall back to proxy endpoint for caching
                cached = _poster_cache_path(key)
                poster_url = _poster_cache_url(key, cached) if cached else f"/api/movie/{key}/poster"

                items.append(
                    {
                        "key": key,
                        "title": title,
                        "year": None,
                        "addedAt": int(added_at) if added_at else None,
                        "poster": poster_url,
                        "library_id": lib_id,
                    }
                )
        except Exception as e:
            logger.warning("[PLEX] Failed to fetch collections for library %s: %s", lib_id, e)

    logger.info("[PLEX] Loaded %d collections from %d libraries (%s)", len(items), len(lib_ids), ",".join(lib_ids))
    return items


@router.get("/movies", response_model=List[Movie])
def api_movies(force_refresh: bool = False, max_age: int = 900, library_id: str = None):
    """
    Return movies. Uses cached DB if it is fresh (default 15 minutes) unless force_refresh=true.
    """
    # Normalize library_id: treat "default" or empty string as None (fetch all libraries)
    if library_id in ("default", ""):
        library_id = None

    if not force_refresh and _cache_fresh(max_age, library_id=library_id):
        cached = cache.get_cached_movies(library_id=library_id)
        if cached:
            return [
                {
                    "key": m["rating_key"],
                    "title": m["title"],
                    "year": m["year"],
                    "addedAt": m["addedAt"],
                    "poster": m.get("poster_url"),
                    "tmdb_id": m.get("tmdb_id"),
                    "labels": m.get("labels") or [],
                    "updated_at": m.get("updated_at"),
                    "library_id": m.get("library_id"),
                }
                for m in cached
            ]

    # Otherwise hit Plex and refresh the cache
    lib_ids = [library_id] if library_id else None
    movies = get_plex_movies(lib_ids)
    return [{**m.model_dump(), "poster": None} for m in movies]


@router.get("/collections")
def api_collections(force_refresh: bool = False, library_id: str = None):
    """Return Plex collections for the specified library (or all movie libraries by default)."""
    if library_id in ("default", ""):
        library_id = None

    lib_ids = [library_id] if library_id else None

    if not force_refresh and _collections_cache_fresh(max_age_seconds=900, library_id=library_id):
        cached = cache.get_cached_collections(library_id=library_id)
        if cached:
            return [
                {
                    "key": c.get("rating_key"),
                    "title": c.get("title"),
                    "year": c.get("year"),
                    "addedAt": c.get("addedAt"),
                    "poster": c.get("poster_url"),
                    "library_id": c.get("library_id"),
                }
                for c in cached
            ]

    items = _get_plex_collections(lib_ids)
    if items:
        cache.refresh_collections_from_list(items)
    return items


@router.delete("/cache")
def api_clear_cache():
    """Clear backend cache: DB movie_cache and on-disk poster cache."""
    try:
        # Clear DB cache
        db.clear_movie_cache()
        db.clear_tv_cache()
        db.clear_collection_cache()

        # Clear poster cache on disk
        poster_dir = Path(POSTER_CACHE_DIR)
        removed_files = 0
        if poster_dir.exists():
            for child in poster_dir.iterdir():
                if child.is_file():
                    try:
                        child.unlink()
                        removed_files += 1
                    except Exception:
                        pass
        logger.info("[CACHE] Cleared movie_cache/tv_cache tables and removed %d poster files", removed_files)
        return {"status": "ok", "removed_posters": removed_files}
    except Exception as e:
        logger.error(f"[CACHE] Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")


@router.get("/scan-progress")
def api_scan_progress():
    """Return last known scan progress."""
    return scan_status


@router.get("/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


@router.get("/movie/{rating_key}/labels", response_model=LabelsResponse)
def api_movie_labels(rating_key: str):
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch labels for %s: %s", rating_key, e)
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

    labels_list = sorted(labels)
    try:
        cache.update_labels(rating_key, labels_list)
    except Exception:
        logger.debug("[CACHE] update_labels failed for %s", rating_key, exc_info=True)
    return LabelsResponse(labels=labels_list)


@router.post("/movie/{rating_key}/labels/remove")
def api_movie_labels_remove(rating_key: str, req: LabelsRemoveRequest):
    from ..config import plex_remove_label

    for label in req.labels:
        plex_remove_label(rating_key, label)
    return {"status": "ok", "removed": req.labels}


@router.get("/tmdb/{tmdb_id}/images")
def api_tmdb_images(tmdb_id: int):
    try:
        details = get_movie_details(tmdb_id)
        tmdb_imgs = get_images_for_movie(tmdb_id, details.get("original_language"))
        fanart_imgs = get_fanart_images(tmdb_id)
        tvdb_imgs = {"posters": [], "backdrops": [], "logos": []}
        tvdb_id: Optional[int] = None

        logger.info("[TVDB] Starting TVDB lookup for movie tmdb_id=%s", tmdb_id)
        # Try to get TVDB ID from TMDB external IDs
        try:
            external_ids = get_movie_external_ids(tmdb_id)
            logger.info("[TVDB] Movie external IDs for tmdb_id=%s: %s", tmdb_id, external_ids)
            # For movies, TVDB might not always have an entry, so we check imdb_id first
            # TVDB movie IDs might be stored differently than TV show IDs
            tvdb_id = external_ids.get("tvdb_id")
            logger.info("[TVDB] Extracted TVDB ID: %s", tvdb_id)
        except Exception as e:
            logger.info("[TVDB] Failed to get external IDs for tmdb_id=%s: %s", tmdb_id, e)
            tvdb_id = None

        # Only call TVDB if key is set and we have an id
        if tvdb_id and settings.TVDB_API_KEY:
            try:
                logger.debug("[TVDB] Fetching movie images for tvdb_id=%s", tvdb_id)
                tvdb_imgs = tvdb_client.get_movie_images(int(tvdb_id))
                logger.debug("[TVDB] Movie images result: %d posters, %d logos, %d backdrops",
                            len(tvdb_imgs.get("posters", [])),
                            len(tvdb_imgs.get("logos", [])),
                            len(tvdb_imgs.get("backdrops", [])))
            except Exception as tvdb_err:
                logger.warning("[TVDB] Failed to fetch movie images for tvdb_id=%s: %s", tvdb_id, tvdb_err)
        else:
            if not tvdb_id:
                logger.debug("[TVDB] No TVDB ID found for tmdb_id=%s", tmdb_id)
            if not settings.TVDB_API_KEY:
                logger.debug("[TVDB] TVDB_API_KEY not configured")

        # Get API order from settings
        from ..api.ui_settings import _read_settings
        try:
            ui_settings = _read_settings(include_env=False)
            api_order = ui_settings.apiOrder or ["tmdb", "fanart", "tvdb"]
        except Exception:
            api_order = ["tmdb", "fanart", "tvdb"]

        # Build image sources dictionary
        image_sources = {
            "tmdb": {"logos": tmdb_imgs.get("logos") or [], "posters": tmdb_imgs.get("posters") or [], "backdrops": tmdb_imgs.get("backdrops") or []},
            "fanart": {"logos": fanart_imgs.get("logos") or [], "posters": fanart_imgs.get("posters") or [], "backdrops": fanart_imgs.get("backdrops") or []},
            "tvdb": {"logos": tvdb_imgs.get("logos") or [], "posters": tvdb_imgs.get("posters") or [], "backdrops": tvdb_imgs.get("backdrops") or []}
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
            "[IMAGES] Movie tmdb_id=%s posters=%d backdrops=%d logos=%d",
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


@router.get("/movie/{rating_key}/poster")
def api_movie_poster(rating_key: str, request: Request, meta: bool = False, raw: bool = False, force_refresh: bool = False):
    """
    Return Plex poster, cached on disk. If `meta=1` (or Accept: application/json),
    returns {"url": "<cached endpoint>"} instead of bytes so the UI can show without re-download.
    If force_refresh is true, it will re-fetch from Plex and overwrite cache.
    """

    def _cached_url(candidate: Path) -> str:
        ts = int(candidate.stat().st_mtime)
        return f"/api/movie/{rating_key}/poster?raw=1&v={ts}"

    def _return_file(candidate: Path, cache_header: str):
        resp = FileResponse(candidate)
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        resp.headers["X-Poster-Cache"] = cache_header
        return resp

    wants_json = meta or "application/json" in (request.headers.get("accept") or "").lower()
    cached = fetch_and_cache_poster(rating_key, force_refresh=force_refresh)
    cache_header = "miss" if force_refresh else ("hit" if cached else "miss")

    if cached:
        if raw and not wants_json:
            return _return_file(cached, cache_header)
        if wants_json:
            return JSONResponse({"url": _cached_url(cached)})
        return _return_file(cached, cache_header)

    # If still nothing, 404
    raise HTTPException(status_code=404, detail="Poster not found")


@router.get("/movies/tmdb")
def api_movies_tmdb():
    movies = get_plex_movies()
    return [
        {"title": m.title, "year": m.year, "rating_key": m.key, "tmdb_id": None}
        for m in movies
    ]


@router.post("/movies/labels/bulk")
def api_movie_labels_bulk(movie_keys: List[str] = Body(...)):
    """Get labels for multiple movies at once."""
    try:
        results = {}
        
        # Batch process the labels to avoid individual API calls
        for movie_key in movie_keys:
            try:
                # Direct label fetching without going through the API endpoint
                url = f"{settings.PLEX_URL}/library/metadata/{movie_key}"
                r = plex_session.get(url, headers=plex_headers(), timeout=10)
                r.raise_for_status()
                
                root = ET.fromstring(r.text)
                labels_list = []
                for label in root.findall(".//Label"):
                    tag = label.get('tag', '').strip()
                    if tag:
                        labels_list.append(tag)
                
                results[movie_key] = labels_list
            except Exception as e:
                logger.debug(f"[BULK LABELS] Failed to fetch labels for {movie_key}: {e}")
                results[movie_key] = []
                
        logger.info(f"[BULK LABELS] Successfully fetched labels for {len(results)} movies")
        return {"labels": results}
    except Exception as e:
        logger.error(f"[BULK LABELS] Failed to fetch bulk labels: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch bulk labels: {e}")


@router.post("/scan-library")
def api_scan_library():
    """Scan entire Plex library and return full data for caching."""
    try:
        # Prevent multiple simultaneous scans
        if scan_status.get("state") == "running":
            logger.warning("[SCAN] Scan already in progress, rejecting new scan request")
            raise HTTPException(status_code=409, detail="Scan already in progress")
        
        movies = get_plex_movies()
        logger.info(f"[SCAN] Starting library scan for {len(movies)} movies")
        scan_status.update({
            "state": "running",
            "total": len(movies),
            "processed": 0,
            "current": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "error": None,
        })

        # Build complete response with posters and labels
        result = {
            "status": "ok",
            "count": len(movies),
            "movies": [],
            "posters": {},
            "labels": {}
        }

        total = len(movies)
        for idx, movie in enumerate(movies, start=1):
            title_for_log = (movie.title or "").strip()
            if len(title_for_log) > 60:
                title_for_log = title_for_log[:57] + "..."
            logger.debug("[SCAN] %d/%d %s", idx, total, title_for_log or "(untitled)")
            # Add movie data
            result["movies"].append({
                "key": movie.key,
                "title": movie.title,
                "year": movie.year,
                "addedAt": movie.addedAt
            })

            # Fetch poster URL
            try:
                poster_path = fetch_and_cache_poster(movie.key, force_refresh=False)
                if poster_path:
                    result["posters"][movie.key] = _poster_cache_url(movie.key, poster_path)
                else:
                    result["posters"][movie.key] = None
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch poster for {movie.key}: {e}")
                result["posters"][movie.key] = None

            # Fetch labels
            try:
                labels_data = api_movie_labels(movie.key)
                result["labels"][movie.key] = labels_data.labels
                
                # Also update the backend cache with this data
                try:
                    poster_url = result["posters"].get(movie.key)
                    cache.upsert_movie(
                        movie,
                        tmdb_id=None,
                        poster_url=poster_url,
                        labels=labels_data.labels
                    )
                except Exception as cache_err:
                    logger.debug(f"[SCAN] Failed to cache data for {movie.key}: {cache_err}")
                    
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch labels for {movie.key}: {e}")
                result["labels"][movie.key] = []

            if idx % 50 == 0 or idx == total:
                logger.info("[SCAN] Progress %d/%d (posters=%d labels=%d)", idx, total, len(result["posters"]), len(result["labels"]))
            scan_status.update({
                "processed": idx,
                "current": movie.title or "",
            })

        logger.info(f"[SCAN] Completed library scan - {len(movies)} movies, {len(result['posters'])} posters, {len(result['labels'])} label sets")
        scan_status.update({
            "state": "done",
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        return result
    except Exception as e:
        logger.error(f"[SCAN] Failed to scan library: {e}")
        scan_status.update({
            "state": "error",
            "error": str(e),
            "finished_at": datetime.now(timezone.utc).isoformat(),
        })
        raise HTTPException(status_code=500, detail=f"Failed to scan library: {e}")


@router.get("/local-assets")
def api_local_assets():
    """List all saved poster assets from the output folder defined in UI settings."""
    try:
        # Get save location from UI settings
        from ..api.ui_settings import _read_settings
        ui_settings = _read_settings()
        save_location = ui_settings.saveLocation or "/output"

        # Resolve the save location path (strip {library}, {title}, {year}, {key} template variables)
        base_path = save_location.split("{")[0].rstrip("/")

        if base_path.startswith("/output"):
            # Map /output to OUTPUT_ROOT if configured, otherwise use CONFIG_DIR/output
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            tail = base_path[len("/output"):].lstrip("/")
            output_root = Path(output_base) / tail if tail else Path(output_base)
        elif base_path.startswith("/config"):
            # Map /config to CONFIG_DIR
            tail = base_path[len("/config"):].lstrip("/")
            output_root = Path(settings.CONFIG_DIR) / tail if tail else Path(settings.CONFIG_DIR)
        elif base_path.startswith("config/"):
            tail = base_path.split("/", 1)[1] if "/" in base_path else ""
            output_root = Path(settings.CONFIG_DIR) / tail
        elif base_path.startswith("output/"):
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            tail = base_path.split("/", 1)[1] if "/" in base_path else ""
            output_root = Path(output_base) / tail
        else:
            # Relative path - anchor under CONFIG_DIR/output
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            output_root = Path(output_base) / base_path.lstrip("/\\")

        output_root = output_root.resolve()

        if not output_root.exists():
            return {"assets": [], "count": 0, "output_path": str(output_root)}

        assets = []
        # Supported image extensions
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}

        # Walk through output directory
        for root, dirs, files in os.walk(output_root):
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix.lower() in image_extensions:
                    try:
                        stat = file_path.stat()
                        rel_path = file_path.relative_to(output_root)

                        # Read library metadata from the image
                        metadata = _read_image_metadata(file_path)

                        asset = {
                            "filename": file,
                            "path": str(rel_path),
                            "full_path": str(file_path),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "folder": str(rel_path.parent) if rel_path.parent != Path('.') else ""
                        }

                        # Add library metadata if available
                        if metadata:
                            asset["library_id"] = metadata.get("library_id")
                            asset["library_name"] = metadata.get("library_name")
                            asset["movie_title"] = metadata.get("movie_title")
                            asset["movie_year"] = metadata.get("movie_year")

                        assets.append(asset)
                    except Exception as e:
                        logger.debug(f"[LOCAL_ASSETS] Failed to stat {file_path}: {e}")

        # Sort by modified time (newest first)
        assets.sort(key=lambda x: x['modified'], reverse=True)

        logger.info(f"[LOCAL_ASSETS] Found {len(assets)} assets in {output_root}")
        return {
            "assets": assets,
            "count": len(assets),
            "output_path": str(output_root)
        }
    except Exception as e:
        logger.error(f"[LOCAL_ASSETS] Failed to list assets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list local assets: {e}")


@router.get("/local-assets/{path:path}")
def api_local_asset_file(path: str):
    """Serve a local asset file."""
    try:
        # Get save location from UI settings
        from ..api.ui_settings import _read_settings
        ui_settings = _read_settings()
        save_location = ui_settings.saveLocation or "/output"

        # Resolve the save location path (strip template variables)
        base_path = save_location.split("{")[0].rstrip("/")

        if base_path.startswith("/output"):
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            tail = base_path[len("/output"):].lstrip("/")
            output_root = Path(output_base) / tail if tail else Path(output_base)
        elif base_path.startswith("/config"):
            tail = base_path[len("/config"):].lstrip("/")
            output_root = Path(settings.CONFIG_DIR) / tail if tail else Path(settings.CONFIG_DIR)
        elif base_path.startswith("config/"):
            tail = base_path.split("/", 1)[1] if "/" in base_path else ""
            output_root = Path(settings.CONFIG_DIR) / tail
        elif base_path.startswith("output/"):
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            tail = base_path.split("/", 1)[1] if "/" in base_path else ""
            output_root = Path(output_base) / tail
        else:
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            output_root = Path(output_base) / base_path.lstrip("/\\")

        output_root = output_root.resolve()
        file_path = output_root / path

        # Security check: ensure the resolved path is still within output_root
        if not file_path.resolve().is_relative_to(output_root.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(file_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LOCAL_ASSETS] Failed to serve file {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to serve file: {e}")


@router.delete("/local-assets/{path:path}")
def api_delete_local_asset(path: str):
    """Delete a local asset file."""
    try:
        # Get save location from UI settings
        from ..api.ui_settings import _read_settings
        ui_settings = _read_settings()
        save_location = ui_settings.saveLocation or "/output"

        # Resolve the save location path (strip template variables)
        base_path = save_location.split("{")[0].rstrip("/")

        if base_path.startswith("/output"):
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            tail = base_path[len("/output"):].lstrip("/")
            output_root = Path(output_base) / tail if tail else Path(output_base)
        elif base_path.startswith("/config"):
            tail = base_path[len("/config"):].lstrip("/")
            output_root = Path(settings.CONFIG_DIR) / tail if tail else Path(settings.CONFIG_DIR)
        elif base_path.startswith("config/"):
            tail = base_path.split("/", 1)[1] if "/" in base_path else ""
            output_root = Path(settings.CONFIG_DIR) / tail
        elif base_path.startswith("output/"):
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            tail = base_path.split("/", 1)[1] if "/" in base_path else ""
            output_root = Path(output_base) / tail
        else:
            output_base = settings.OUTPUT_ROOT if settings.OUTPUT_ROOT else str(Path(settings.CONFIG_DIR) / "output")
            output_root = Path(output_base) / base_path.lstrip("/\\")

        output_root = output_root.resolve()
        file_path = output_root / path

        # Security check: ensure the resolved path is still within output_root
        if not file_path.resolve().is_relative_to(output_root.resolve()):
            raise HTTPException(status_code=403, detail="Access denied")

        if not file_path.exists() or not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")

        # Delete the file
        file_path.unlink()
        logger.info(f"[LOCAL_ASSETS] Deleted file: {file_path}")

        # Clean up empty parent folders
        deleted_folders = []
        parent_dir = file_path.parent
        while parent_dir != output_root and parent_dir > output_root:
            try:
                # Check if directory is empty
                if not any(parent_dir.iterdir()):
                    parent_dir.rmdir()
                    deleted_folders.append(str(parent_dir.relative_to(output_root)))
                    logger.info(f"[LOCAL_ASSETS] Deleted empty folder: {parent_dir}")
                    parent_dir = parent_dir.parent
                else:
                    # Directory not empty, stop cleanup
                    break
            except Exception as e:
                logger.debug(f"[LOCAL_ASSETS] Could not delete folder {parent_dir}: {e}")
                break

        result = {"success": True, "message": f"Deleted {path}"}
        if deleted_folders:
            result["deleted_folders"] = deleted_folders
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LOCAL_ASSETS] Failed to delete file {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")
