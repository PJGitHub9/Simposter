import xml.etree.ElementTree as ET
from typing import List, Optional
from pathlib import Path
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request, Body, Query
from fastapi.responses import Response, FileResponse, JSONResponse
from pydantic import BaseModel
from PIL import Image

import requests
from ..config import settings, plex_headers, logger, get_plex_movies, get_movie_tmdb_id, plex_session, POSTER_CACHE_DIR, LOGO_CACHE_DIR
from .. import cache, database as db
from ..schemas import Movie, MovieTMDbResponse, LabelsResponse, LabelsRemoveRequest
from ..tmdb_client import get_images_for_movie, get_movie_details, get_movie_external_ids, search_collection, get_collection_images, TMDBError
from ..fanart_client import get_images_for_movie as get_fanart_images, get_logos_for_movie as get_fanart_logos
from .. import tvdb_client
from .tv_shows import _get_plex_tv_shows, api_tv_show_labels
from ..middleware.validation import (
    validate_rating_key,
    validate_tmdb_id,
    validate_library_id,
    validate_labels
)
from ..save_paths import resolve_save_root

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


# Local Assets can hold thousands of saved posters, and every listing/resend request
# used to re-open and re-parse every single file from scratch — on network-backed
# storage (NFS/SMB volumes, common for these self-hosted setups) that made "Refresh"
# visibly slow. Cache metadata per file, keyed by (mtime, size) so it's invalidated
# automatically the moment a file actually changes, without needing a TTL or an
# explicit cache-clear button. Lives for the life of the backend process.
_image_metadata_cache: dict = {}  # path_str -> (mtime, size, metadata)


def _read_image_metadata(file_path: Path, stat_result: Optional[os.stat_result] = None) -> dict:
    """
    Read library metadata from image file (cached — see _image_metadata_cache above).

    Args:
        file_path: path to the saved poster
        stat_result: pass this in if the caller already has a fresh os.stat() for the
            file (e.g. from an os.walk loop) to avoid a second stat() call.
    """
    path_str = str(file_path)
    try:
        stat_result = stat_result or file_path.stat()
    except OSError:
        stat_result = None

    if stat_result is not None:
        cached = _image_metadata_cache.get(path_str)
        if cached and cached[0] == stat_result.st_mtime and cached[1] == stat_result.st_size:
            return cached[2]

    metadata = _read_image_metadata_uncached(file_path)

    if stat_result is not None:
        _image_metadata_cache[path_str] = (stat_result.st_mtime, stat_result.st_size, metadata)
    return metadata


def _read_image_metadata_uncached(file_path: Path) -> dict:
    """
    Actually read library metadata from an image file's embedded PNG/EXIF data.
    Returns dict with library_id, library_name, movie_title, movie_year, rating_key,
    and is_tv if found. Called through _read_image_metadata()'s cache, not directly.
    """
    try:
        img = Image.open(file_path)

        # Try to extract from PNG metadata first
        if hasattr(img, 'text'):
            library_id = img.text.get('simposter_library_id')
            library_name = img.text.get('simposter_library_name')
            movie_title = img.text.get('simposter_movie_title')
            movie_year = img.text.get('simposter_movie_year')
            rating_key = img.text.get('simposter_rating_key')
            is_tv = img.text.get('simposter_is_tv')
            if library_id or movie_title:
                result = {}
                if library_id:
                    result['library_id'] = library_id
                    result['library_name'] = library_name or library_id
                if movie_title:
                    result['movie_title'] = movie_title
                if movie_year:
                    result['movie_year'] = movie_year
                if rating_key:
                    result['rating_key'] = rating_key
                    result['is_tv'] = is_tv == '1'
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
                    rating_key = metadata.get('simposter_rating_key')
                    is_tv = metadata.get('simposter_is_tv')
                    if library_id or movie_title:
                        result = {}
                        if library_id:
                            result['library_id'] = library_id
                            result['library_name'] = library_name or library_id
                        if movie_title:
                            result['movie_title'] = movie_title
                        if movie_year:
                            result['movie_year'] = movie_year
                        if rating_key:
                            result['rating_key'] = rating_key
                            result['is_tv'] = is_tv == '1'
                        return result
                except (json.JSONDecodeError, TypeError):
                    pass
        except (AttributeError, UnicodeDecodeError) as e:
            logger.debug("Failed to extract poster metadata: %s", e)

        # Try from img.info dict (fallback)
        if hasattr(img, 'info'):
            library_id = img.info.get('simposter_library_id')
            library_name = img.info.get('simposter_library_name')
            movie_title = img.info.get('simposter_movie_title')
            movie_year = img.info.get('simposter_movie_year')
            rating_key = img.info.get('simposter_rating_key')
            is_tv = img.info.get('simposter_is_tv')
            if library_id or movie_title:
                result = {}
                if library_id:
                    result['library_id'] = library_id
                    result['library_name'] = library_name or library_id
                if movie_title:
                    result['movie_title'] = movie_title
                if movie_year:
                    result['movie_year'] = movie_year
                if rating_key:
                    result['rating_key'] = rating_key
                    result['is_tv'] = is_tv == '1'
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
            except OSError as e:
                logger.warning("Failed to remove cached poster %s: %s", p, e)
    return removed


_LOGO_CACHE_DIR = Path(LOGO_CACHE_DIR)


def _logo_cache_path(rating_key: str) -> Optional[Path]:
    for ext in ("png", "jpg", "jpeg", "webp"):
        candidate = _LOGO_CACHE_DIR / f"{rating_key}.{ext}"
        if candidate.exists():
            return candidate
    return None


def _logo_cache_url(rating_key: str, cached: Path) -> str:
    ts = int(cached.stat().st_mtime)
    return f"/api/logo/{rating_key}?raw=1&v={ts}"


def _save_logo_cache(rating_key: str, content: bytes, content_type: str) -> Optional[Path]:
    ext = (content_type.split("/")[-1] if "/" in content_type else "png").lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "png"
    target = _LOGO_CACHE_DIR / f"{rating_key}.{ext}"
    try:
        target.write_bytes(content)
        return target
    except Exception as e:
        logger.debug("[LOGO] Failed to write logo cache for %s: %s", rating_key, e)
        return None


def fetch_and_cache_logo(rating_key: str, force_refresh: bool = False) -> Optional[Path]:
    """Fetch Plex clearlogo and cache locally. Returns cached file path or None."""
    if not force_refresh:
        cached = _logo_cache_path(rating_key)
        if cached:
            return cached
    try:
        # Plex returns image metadata as JSON with an Image[] array
        metadata_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        json_headers = {**plex_headers(), "Accept": "application/json"}
        r = plex_session.get(metadata_url, headers=json_headers, timeout=5)
        if r.status_code != 200:
            return None

        logo_url = None
        try:
            data = r.json()
            container = data.get("MediaContainer", {})
            # Image array may be at the top level or inside each Metadata item
            images = container.get("Image", [])
            if not images:
                for item in container.get("Metadata", []):
                    images = item.get("Image", [])
                    if images:
                        break
            for img in images:
                if img.get("type") == "clearLogo":
                    logo_url = img.get("url")
                    break
        except Exception:
            pass

        if not logo_url:
            return None

        # Plex returns a relative path (/library/metadata/.../clearLogo/...).
        # Prepend the Plex base URL and use the authenticated session.
        if logo_url.startswith("/"):
            logo_url = f"{settings.PLEX_URL}{logo_url}"
            logo_r = plex_session.get(logo_url, headers=plex_headers(), timeout=10)
        else:
            # Absolute external URL (rare) — no auth needed
            logo_r = requests.get(logo_url, timeout=10)
        if logo_r.status_code != 200:
            logger.debug("[LOGO] Failed to download clearlogo for %s: HTTP %s", rating_key, logo_r.status_code)
            return None
        content_type = logo_r.headers.get("content-type", "image/png")
        return _save_logo_cache(rating_key, logo_r.content, content_type)
    except Exception as e:
        logger.debug("[LOGO] Failed to fetch Plex clearlogo for %s: %s", rating_key, e)
        return None


def fetch_and_cache_poster(rating_key: str, force_refresh: bool = False) -> Optional[Path]:
    """
    Fetch poster from cache or Plex and store it. Returns cached file path or None.
    """
    if force_refresh:
        _remove_poster_cache(rating_key)
    else:
        # Only use cached version if not forcing refresh
        cached = _poster_cache_path(rating_key)
        if cached:
            return cached

    # Add cache-busting parameter when force refreshing to bypass Plex's cache
    import time
    cache_buster = f"?X-Plex-Token={settings.PLEX_TOKEN}&t={int(time.time())}" if force_refresh else ""
    direct = f"{settings.PLEX_URL}/library/metadata/{rating_key}/thumb{cache_buster}"

    # Try direct poster URL
    try:
        r = plex_session.get(direct, headers=plex_headers(), timeout=5)
        if r.status_code == 200:
            content_type = r.headers.get('content-type', 'image/jpeg')
            saved = _save_poster_cache(rating_key, r.content, content_type)
            if saved:
                # Store the Simposter proxy URL in cache, not the direct Plex URL
                proxy_url = _poster_cache_url(rating_key, saved)
                try:
                    cache.update_poster(rating_key, proxy_url)
                except (sqlite3.Error, AttributeError) as e:
                    logger.debug("[CACHE] update_poster failed for %s: %s", rating_key, e, exc_info=True)
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
                    saved = _save_poster_cache(rating_key, poster_r.content, content_type)
                    if saved:
                        # Store the Simposter proxy URL in cache, not the direct Plex URL
                        proxy_url = _poster_cache_url(rating_key, saved)
                        try:
                            cache.update_poster(rating_key, proxy_url)
                        except (sqlite3.Error, AttributeError) as e:
                            logger.debug("[CACHE] update_poster failed for %s: %s", rating_key, e, exc_info=True)
                    return saved
    except Exception as e:
        logger.debug(f"Failed to fetch poster via metadata for {rating_key}: {e}")

    return None


@router.get("/test-plex-connection")
def test_plex_connection(plex_url: str = None, plex_token: str = None):
    """Test Plex server connection and return diagnostics."""
    from ..config import SECRET_MASK

    # Use provided parameters or fall back to settings. If the caller echoed back the
    # masked placeholder (Settings UI never sees the real saved token), treat that the
    # same as "not provided" so we test the actual stored token instead of the literal
    # placeholder string.
    test_url = plex_url or settings.PLEX_URL
    test_token = plex_token if (plex_token and plex_token != SECRET_MASK) else settings.PLEX_TOKEN

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


@router.get("/plex-status")
def api_plex_status():
    """
    Lightweight Plex reachability check for the header status indicator — polled
    periodically by the frontend, so this deliberately hits the cheap, usually-
    unauthenticated `/identity` endpoint rather than `/library/sections` (what
    test_plex_connection above uses), and never raises: any failure just means "down".
    """
    if not settings.PLEX_URL:
        return {"status": "unconfigured"}

    try:
        r = plex_session.get(f"{settings.PLEX_URL}/identity", headers=plex_headers(), timeout=5)
        r.raise_for_status()
        return {"status": "up"}
    except Exception as e:
        logger.debug(f"[PLEX_STATUS] Plex unreachable: {e}")
        return {"status": "down", "message": str(e)}


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
    except (ValueError, TypeError) as e:
        logger.debug("Invalid timestamp format: %s", e)
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
    except (ValueError, TypeError) as e:
        logger.debug("Invalid timestamp format: %s", e)
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
def api_movies(force_refresh: bool = False, max_age: int = 900, library_id: str = None, deduplicate: bool = False):
    """
    Return movies from cache. Always returns from cache - use /scan-library to refresh.
    The force_refresh parameter is deprecated but kept for backwards compatibility.

    Args:
        deduplicate: If True, removes duplicate movies with the same TMDb ID (keeps most recently added)
    """
    # Normalize library_id: treat "default" or empty string as None (fetch all libraries)
    if library_id in ("default", ""):
        library_id = None

    # Always return from cache (which includes labels populated by scans)
    cached = cache.get_cached_movies(library_id=library_id)

    movies = [
        {
            "key": m["rating_key"],
            "title": m["title"],
            "year": m["year"],
            "addedAt": m["addedAt"],
            "poster": m.get("poster_url"),
            "logo_url": m.get("logo_url"),
            "tmdb_id": m.get("tmdb_id"),
            "labels": m.get("labels") or [],
            "updated_at": m.get("updated_at"),
            "library_id": m.get("library_id"),
            "edition": m.get("edition"),
        }
        for m in cached
    ]

    # Deduplicate by TMDb ID if requested (keep most recently added)
    if deduplicate:
        seen_tmdb = {}
        deduped = []

        for movie in movies:
            tmdb_id = movie.get("tmdb_id")

            # If no TMDb ID, always include (can't deduplicate)
            if not tmdb_id:
                deduped.append(movie)
                continue

            # If we haven't seen this TMDb ID, add it
            if tmdb_id not in seen_tmdb:
                seen_tmdb[tmdb_id] = movie
                deduped.append(movie)
            else:
                # If this version is more recent, replace the older one
                existing = seen_tmdb[tmdb_id]
                current_added = movie.get("addedAt", 0) or 0
                existing_added = existing.get("addedAt", 0) or 0

                if current_added > existing_added:
                    # Remove old version and add new one
                    deduped.remove(existing)
                    seen_tmdb[tmdb_id] = movie
                    deduped.append(movie)
                    logger.debug(f"[DEDUPE] Replaced {existing['title']} (key={existing['key']}) with newer edition (key={movie['key']})")

        logger.info(f"[DEDUPE] Deduplication reduced {len(movies)} movies to {len(deduped)} unique movies")
        return deduped

    return movies


@router.get("/movies/labels/all")
def api_all_movie_labels(library_id: str = None):
    """Get all unique labels for a movie library (or all libraries if not specified)."""
    if library_id in ("default", ""):
        library_id = None
    
    cached = cache.get_cached_movies(library_id=library_id)
    labels_set = set()
    
    for movie in cached:
        if movie.get("labels") and isinstance(movie.get("labels"), list):
            labels_set.update(movie.get("labels"))
    
    return {"labels": sorted(list(labels_set))}


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
                    except OSError as e:
                        logger.warning("Failed to remove cached poster file %s: %s", child, e)
        logger.info("[CACHE] Cleared movie_cache/tv_cache tables and removed %d poster files", removed_files)
        return {"status": "ok", "removed_posters": removed_files}
    except Exception as e:
        logger.error(f"[CACHE] Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {e}")


@router.delete("/library/{library_id}")
def api_remove_library(library_id: str):
    """
    Purge everything cache-layer for a library that's being removed in Settings
    (LibrariesTab.vue's Remove button). Deliberately scoped to what actually goes
    stale/orphaned once a library is no longer tracked: DB cache rows (movie/TV/
    collection), on-disk poster+logo cache files, and pending retry-queue entries.

    Deliberately does NOT touch poster_history (History is a record of past
    activity, kept intentionally even after the library's gone) or on-disk saved
    output files (those are the user's actual exported posters, a different and
    much more destructive thing to delete than "cache"). Settings persistence
    (actually removing the library from libraryMappings) happens separately via
    the normal POST /api/ui-settings save -- this endpoint is purely the cache
    cleanup half of "remove a library".
    """
    try:
        from .tv_shows import _remove_poster_cache as _remove_tv_poster_cache

        movies = db.get_cached_movies(library_id=library_id)
        tv_shows = db.get_cached_tv_shows(library_id=library_id)

        removed_files = 0
        for item, is_tv in [(m, False) for m in movies] + [(s, True) for s in tv_shows]:
            rating_key = item.get("rating_key")
            if not rating_key:
                continue
            removed = _remove_tv_poster_cache(rating_key, "tv") if is_tv else _remove_poster_cache(rating_key)
            if removed:
                removed_files += 1
            logo_path = _logo_cache_path(rating_key)
            if logo_path:
                try:
                    logo_path.unlink()
                    removed_files += 1
                except OSError as e:
                    logger.warning("[LIBRARY] Failed to remove cached logo %s: %s", logo_path, e)

        db.clear_movie_cache(library_id)
        db.clear_tv_cache(library_id)
        db.clear_collection_cache(library_id)
        retry_removed = db.clear_retry_queue_for_library(library_id)

        logger.info(
            "[LIBRARY] Removed library %s: %d movies, %d TV shows, %d cache files, %d retry queue entries",
            library_id, len(movies), len(tv_shows), removed_files, retry_removed
        )
        return {
            "status": "ok",
            "movies_removed": len(movies),
            "tv_shows_removed": len(tv_shows),
            "cache_files_removed": removed_files,
            "retry_queue_removed": retry_removed,
        }
    except Exception as e:
        logger.error("[LIBRARY] Failed to remove library %s: %s", library_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove library cache: {e}")


@router.get("/scan-progress")
def api_scan_progress():
    """Return last known scan progress."""
    return scan_status


@router.get("/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    rating_key = validate_rating_key(rating_key)
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


def _best_collection_match(title: str, results: List[dict]) -> Optional[dict]:
    """Pick the right TMDb collection out of /search/collection's results for a
    plain title like Plex's ("The Lord of the Rings"). Naive exact-string-or-
    first-result matching picks the wrong thing here: TMDb's own results for
    that exact query are, in order, 'The Making of The Lord of the Rings
    Collection' (a documentary), 'The Lord of the Rings Collection' (the
    actual trilogy), and 'The Lord of the Rings (Animated) Collection' — i.e.
    TMDb's relevance ranking is not "the main franchise first", and TMDb's own
    naming convention (an appended "Collection", sometimes with a qualifier
    prefix/suffix) means a plain title never exactly matches any real entry
    either. Normalizing away the "Collection" suffix and preferring the
    shortest name that starts with (or at minimum contains) the target title
    reliably picks the main collection over "Making of"/spin-off variants,
    which are always longer, qualified names."""
    if not results:
        return None

    def normalize(name: str) -> str:
        n = (name or "").strip().lower()
        if n.endswith(" collection"):
            n = n[: -len(" collection")]
        return n.strip()

    target = normalize(title)

    exact = [r for r in results if normalize(r.get("name") or "") == target]
    if exact:
        return exact[0]

    starts_with = [r for r in results if normalize(r.get("name") or "").startswith(target)]
    if starts_with:
        return min(starts_with, key=lambda r: len(r.get("name") or ""))

    contains = [r for r in results if target in normalize(r.get("name") or "")]
    if contains:
        return min(contains, key=lambda r: len(r.get("name") or ""))

    return results[0]


@router.get("/collection/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_collection_tmdb(rating_key: str):
    """Resolve a Plex collection to a TMDb collection ID, for the Simposter
    Creator's poster browsing. Plex collections carry no TMDb ID of their own,
    so this is a one-time title search against TMDb's /search/collection,
    cached afterward in collection_cache.tmdb_collection_id (0 = looked up,
    no match found — distinct from None/never looked up) so repeat editor
    opens for the same collection don't repeat the search."""
    rating_key = validate_rating_key(rating_key)

    cached = db.get_collection_tmdb_id(rating_key)
    if cached is not None:
        return MovieTMDbResponse(tmdb_id=cached or None)

    title = None
    with db.get_db() as conn:
        row = conn.execute("SELECT title FROM collection_cache WHERE rating_key = ?", (rating_key,)).fetchone()
        if row:
            title = row["title"]

    tmdb_collection_id = None
    if title:
        try:
            results = search_collection(title)
            best = _best_collection_match(title, results)
            if best:
                tmdb_collection_id = best.get("id")
        except TMDBError as e:
            logger.warning("[TMDB] Collection search failed for '%s': %s", title, e)

    try:
        db.set_collection_tmdb_id(rating_key, tmdb_collection_id or 0)
    except Exception as e:
        logger.debug("[DB] Failed to cache tmdb_collection_id for %s: %s", rating_key, e)

    return MovieTMDbResponse(tmdb_id=tmdb_collection_id)


@router.get("/tmdb/collection/{collection_id}/images")
def api_tmdb_collection_images(collection_id: int):
    """Poster/backdrop candidates for a TMDb collection — TMDb only (no
    Fanart/TVDB equivalent for collections), unlike the movie/TV image merge."""
    collection_id = validate_tmdb_id(collection_id)
    try:
        imgs = get_collection_images(collection_id)
    except TMDBError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "posters": imgs.get("posters") or [],
        "backdrops": imgs.get("backdrops") or [],
        "logos": [],
    }


@router.get("/tmdb/collection/{collection_id}/fanart-logos")
def api_tmdb_collection_fanart_logos(collection_id: int):
    """Franchise-wide logo/clearart candidates for a TMDb collection.

    Fanart.tv has no dedicated "collection" resource in its v3 API, but its
    contributor community tags collection-wide art (hdmovielogo, clearart,
    etc.) under the collection's own TMDb ID in the same /v3/movies/{id}
    namespace used for individual films — the endpoint is agnostic to what
    kind of TMDb ID it's given. Verified live against the LOTR collection
    (id 119): returns 12 hdmovielogo + 3 hdmovieclearart entries, none of
    which belong to any single film. `get_logos_for_movie()` already handles
    this shape unmodified — no new Fanart client code needed."""
    collection_id = validate_tmdb_id(collection_id)
    try:
        logos = get_fanart_logos(collection_id)
    except Exception as e:
        logger.warning("[FANART] Collection logo fetch failed for tmdb_collection_id=%s: %s", collection_id, e)
        logos = []
    return {"logos": logos}


@router.get("/collection/{rating_key}/movies")
def api_collection_movies(rating_key: str):
    """List the movies belonging to a Plex collection — same Plex '/children'
    pattern used for TV show seasons (api_tv_show_seasons), just returning
    <Video> (leaf/movie) elements instead of <Directory> (season) ones. Used
    by the Simposter Creator's Logo section: TMDb/Fanart have no logo image
    type for a collection itself (see get_collection_images — posters/
    backdrops only), but franchise logos on an individual member movie (e.g.
    a "THE LORD OF THE RINGS" clearlogo on the first film) often represent the
    whole series well enough to reuse as the collection's own logo. Won't be
    meaningful for a studio/genre/etc. collection with unrelated movies —
    that's a per-collection judgment call for whoever's using it, not
    something this endpoint can determine."""
    rating_key = validate_rating_key(rating_key)
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/children"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
        root = ET.fromstring(r.text)
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch movies for collection %s: %s", rating_key, e)
        raise HTTPException(status_code=502, detail=f"Failed to fetch collection movies: {e}")

    movies = []
    for video in root.findall(".//Video"):
        key = video.get("ratingKey")
        title = video.get("title") or ""
        year = video.get("year")
        if key and title:
            movies.append({"key": key, "title": title, "year": int(year) if year and year.isdigit() else None})

    return {"movies": movies}


@router.get("/movie/{rating_key}/labels", response_model=LabelsResponse)
def api_movie_labels(rating_key: str):
    rating_key = validate_rating_key(rating_key)
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=10)
        r.raise_for_status()
    except Exception as e:
        logger.warning("[PLEX] Failed to fetch labels for %s: %s", rating_key, e)
        return LabelsResponse(labels=[])

    try:
        root = ET.fromstring(r.text)
    except ET.ParseError as e:
        logger.debug("Failed to parse labels XML for %s: %s", rating_key, e)
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
    except (sqlite3.Error, AttributeError) as e:
        logger.debug("[CACHE] update_labels failed for %s: %s", rating_key, e, exc_info=True)

    # Piggyback: cache media info from the same response
    try:
        from ..config import extract_media_info_from_metadata
        media_info = extract_media_info_from_metadata(r.text)
        if media_info:
            from .. import database as db
            db.update_movie_media_info(
                rating_key,
                media_info.get("video_resolution"),
                media_info.get("audio_codec"),
                media_info.get("audio_channels"),
                video_codec=media_info.get("video_codec"),
                audio_language=media_info.get("audio_language"),
                edition=media_info.get("edition"),
            )
    except Exception:
        pass  # Non-critical

    return LabelsResponse(labels=labels_list)


@router.post("/movie/{rating_key}/labels/remove")
def api_movie_labels_remove(rating_key: str, req: LabelsRemoveRequest):
    from ..config import plex_remove_label

    for label in req.labels:
        plex_remove_label(rating_key, label)
    return {"status": "ok", "removed": req.labels}


@router.get("/tmdb/{tmdb_id}/images")
def api_tmdb_images(tmdb_id: int):
    tmdb_id = validate_tmdb_id(tmdb_id)
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
        except (AttributeError, ImportError, sqlite3.Error) as e:
            logger.debug("Failed to load API order from settings: %s", e)
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


@router.get("/logo/{rating_key}")
def api_logo(rating_key: str, force_refresh: bool = False):
    """Serve cached clearlogo file. Pass force_refresh=1 to re-fetch from Plex first."""
    if force_refresh:
        fetch_and_cache_logo(rating_key, force_refresh=True)
    cached = _logo_cache_path(rating_key)
    if cached:
        resp = FileResponse(cached)
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    raise HTTPException(status_code=404, detail="Logo not found")


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
def api_scan_library(library_id: Optional[str] = Query(None), force_poster_refresh: bool = Query(True)):
    """Comprehensive full-library sync: fetch movies, TV shows, and collections. If library_id provided, scan only that library. force_poster_refresh re-downloads all posters from Plex (default: True)."""
    try:
        # Prevent multiple simultaneous scans
        if scan_status.get("state") == "running":
            logger.warning("[SCAN] Scan already in progress, rejecting new scan request")
            raise HTTPException(status_code=409, detail="Scan already in progress")
        
        # Normalize library_id
        if library_id in ("default", ""):
            library_id = None
        
        logger.info(f"[SCAN] Scan request for library_id={library_id}")

        # Snapshot cache keys BEFORE fetching from Plex.
        # get_plex_movies() eagerly calls cache.refresh_from_list() as a side effect,
        # so if we read the cache after calling it, new items appear already-cached
        # and are never detected as "new" — breaking auto-generate.
        pre_scan_movie_keys = {item.get("rating_key") for item in cache.get_cached_movies()}
        pre_scan_tv_keys = {item.get("rating_key") for item in cache.get_cached_tv_shows()}
        logger.debug("[SCAN] Pre-scan cache: %d movies, %d TV shows", len(pre_scan_movie_keys), len(pre_scan_tv_keys))

        # Fetch all content types
        lib_ids = [library_id] if library_id else None
        movies = get_plex_movies(library_ids=lib_ids)
        tv_shows = _get_plex_tv_shows(lib_ids=lib_ids)
        collections_list = _get_plex_collections(lib_ids=lib_ids)
        
        total_items = len(movies) + len(tv_shows) + len(collections_list)
        logger.info(f"[SCAN] Starting full library sync: {len(movies)} movies, {len(tv_shows)} TV shows, {len(collections_list)} collections")
        scan_status.update({
            "state": "running",
            "total": total_items,
            "processed": 0,
            "current": "",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": None,
            "error": None,
        })

        result = {
            "status": "ok",
            "movies_count": len(movies),
            "tv_shows_count": len(tv_shows),
            "collections_count": len(collections_list),
            "total_count": total_items,
        }

        # Process movies per library
        processed = 0
        movie_cache_by_lib = {}

        # Bulk fetch labels for all movies to avoid N+1 queries
        movie_keys = [movie.key for movie in movies]
        bulk_labels = {}
        if movie_keys:
            try:
                logger.info(f"[SCAN] Bulk fetching labels for {len(movie_keys)} movies")
                for label_idx, movie_key in enumerate(movie_keys, start=1):
                    try:
                        url = f"{settings.PLEX_URL}/library/metadata/{movie_key}"
                        r = plex_session.get(url, headers=plex_headers(), timeout=10)
                        r.raise_for_status()
                        root = ET.fromstring(r.text)
                        labels_list = []
                        for label in root.findall(".//Label"):
                            tag = label.get('tag', '').strip()
                            if tag:
                                labels_list.append(tag)
                        bulk_labels[movie_key] = labels_list
                    except Exception as e:
                        logger.debug(f"[SCAN] Failed to fetch labels for {movie_key}: {e}")
                        bulk_labels[movie_key] = []
                    # This is a sequential per-movie network call and can be the slowest
                    # part of a scan for large libraries — without this, scan_status stayed
                    # unchanged (looking stalled) for the entire label-fetch phase.
                    scan_status.update({"current": f"Fetching labels ({label_idx}/{len(movie_keys)})"})
                logger.info(f"[SCAN] Successfully fetched labels for {len(bulk_labels)} movies")
            except Exception as e:
                logger.warning(f"[SCAN] Bulk label fetch failed, will skip labels: {e}")

        # Parallelize poster + logo fetching using ThreadPoolExecutor
        from concurrent.futures import ThreadPoolExecutor, as_completed
        poster_results = {}
        logo_results = {}

        def fetch_poster_for_movie(movie_key):
            try:
                poster_path = fetch_and_cache_poster(movie_key, force_refresh=force_poster_refresh)
                if poster_path:
                    return movie_key, _poster_cache_url(movie_key, poster_path)
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch poster for movie {movie_key}: {e}")
            return movie_key, None

        def fetch_logo_for_movie(movie_key):
            try:
                logo_path = fetch_and_cache_logo(movie_key, force_refresh=force_poster_refresh)
                if logo_path:
                    return movie_key, _logo_cache_url(movie_key, logo_path)
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch logo for movie {movie_key}: {e}")
            return movie_key, None

        if movie_keys:
            logger.info(f"[SCAN] Parallel fetching posters + logos for {len(movie_keys)} movies")
            # This is typically the slowest phase of a scan (an image download per movie,
            # doubled for logos, especially with force_poster_refresh — the default). Track
            # completions as they land so scan_status.processed climbs smoothly through it
            # instead of sitting at 0 for the whole phase and then jumping at the very end.
            poster_logo_done = 0
            poster_logo_total = len(movie_keys) * 2
            with ThreadPoolExecutor(max_workers=10) as executor:
                poster_futures = {executor.submit(fetch_poster_for_movie, key): key for key in movie_keys}
                logo_futures = {executor.submit(fetch_logo_for_movie, key): key for key in movie_keys}
                for future in as_completed(poster_futures):
                    movie_key, poster_url = future.result()
                    poster_results[movie_key] = poster_url
                    poster_logo_done += 1
                    scan_status.update({
                        "processed": min(len(movies), round(len(movies) * poster_logo_done / poster_logo_total)),
                        "current": f"Fetching posters/logos ({poster_logo_done}/{poster_logo_total})",
                    })
                for future in as_completed(logo_futures):
                    movie_key, logo_url_result = future.result()
                    logo_results[movie_key] = logo_url_result
                    poster_logo_done += 1
                    scan_status.update({
                        "processed": min(len(movies), round(len(movies) * poster_logo_done / poster_logo_total)),
                        "current": f"Fetching posters/logos ({poster_logo_done}/{poster_logo_total})",
                    })
            logo_count = sum(1 for v in logo_results.values() if v)
            logger.info(f"[SCAN] Completed poster + logo fetching for {len(poster_results)} movies ({logo_count} logos found)")

        # Now assemble the movie cache using pre-fetched data. This loop is fast (no I/O —
        # posters/logos/labels were already fetched above), so it doesn't report progress
        # per-item; scan_status.processed is set to its final value once at the end instead.
        for movie in movies:
            lib_id = getattr(movie, "library_id", None) or "default"
            if lib_id not in movie_cache_by_lib:
                movie_cache_by_lib[lib_id] = []

            movie_cache_by_lib[lib_id].append({
                "rating_key": movie.key,
                "title": movie.title,
                "year": movie.year,
                "added_at": movie.addedAt,
                "poster_url": poster_results.get(movie.key),
                "logo_url": logo_results.get(movie.key),
                "labels": bulk_labels.get(movie.key, []),
                "library_id": lib_id,
            })

            processed += 1

        logger.info("[SCAN] Movies progress %d/%d", processed, len(movies))
        scan_status.update({"processed": processed, "current": ""})

        # Bulk refresh movie cache per library and detect new content
        from .. import auto_generate
        for lib_id, cached_movies in movie_cache_by_lib.items():
            # Use pre-scan snapshot so new items added since last scan are detected correctly.
            # Cannot use cache.get_cached_movies() here — get_plex_movies() already refreshed it.
            new_movies = [m for m in cached_movies if m.get("rating_key") not in pre_scan_movie_keys]

            # Refresh cache
            cache.refresh_from_list(cached_movies)
            logger.info(f"[SCAN] Cached {len(cached_movies)} movies for library {lib_id} ({len(new_movies)} new)")

            # Trigger auto-generation for new movies
            if new_movies:
                try:
                    results = auto_generate.process_new_content_for_library(
                        library_id=lib_id,
                        new_movies=new_movies,
                        new_tv_shows=[],
                        auto_send=True
                    )
                    logger.info(f"[SCAN] Auto-generation complete for library {lib_id}: {results}")
                except Exception as e:
                    logger.error(f"[SCAN] Auto-generation failed for library {lib_id}: {e}")

            # Pre-populate streaming provider cache for new movies (best-effort)
            if new_movies:
                try:
                    from ..tmdb_client import get_watch_providers
                    from .. import database as _db
                    overlay_region = "US"
                    for cfg in _db.get_all_overlay_configs():
                        if any(e.get("type") == "streaming_platform_badge" for e in cfg.get("elements", [])):
                            overlay_region = cfg.get("streaming_region") or "US"
                            break
                    for movie in new_movies:
                        tmdb_id = movie.get("tmdb_id")
                        if tmdb_id:
                            get_watch_providers(int(tmdb_id), "movie", overlay_region)
                except Exception:
                    pass  # Never block scan for this

        # Process TV shows per library
        tv_cache_by_lib = {}
        for show in tv_shows:
            lib_id = show.get("library_id") or "default"
            if lib_id not in tv_cache_by_lib:
                tv_cache_by_lib[lib_id] = []
            
            # Fetch poster
            poster_url = None
            try:
                poster_path = fetch_and_cache_poster(show.get("key"), force_refresh=force_poster_refresh)
                if poster_path:
                    poster_url = _poster_cache_url(show.get("key"), poster_path)
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch poster for TV show {show.get('key')}: {e}")

            # Fetch clearlogo from Plex
            logo_url = None
            try:
                logo_path = fetch_and_cache_logo(show.get("key"), force_refresh=force_poster_refresh)
                if logo_path:
                    logo_url = _logo_cache_url(show.get("key"), logo_path)
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch logo for TV show {show.get('key')}: {e}")

            # Fetch labels
            labels = []
            try:
                labels_data = api_tv_show_labels(show.get("key"))
                labels = labels_data.labels
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch labels for TV show {show.get('key')}: {e}")

            tv_cache_by_lib[lib_id].append({
                "rating_key": show.get("key"),
                "title": show.get("title"),
                "year": show.get("year"),
                "added_at": show.get("addedAt"),
                "poster_url": poster_url,
                "logo_url": logo_url,
                "labels": labels,
                "library_id": lib_id,
            })
            
            processed += 1
            if processed % 50 == 0 or processed == total_items:
                logger.info("[SCAN] Overall progress %d/%d", processed, total_items)
            scan_status.update({"processed": processed, "current": show.get("title") or ""})
        
        # Bulk refresh TV cache per library and detect new content
        for lib_id, cached_shows in tv_cache_by_lib.items():
            # Use pre-scan snapshot for the same reason as movies above.
            new_shows = [s for s in cached_shows if s.get("rating_key") not in pre_scan_tv_keys]

            # Refresh cache
            cache.refresh_tv_from_list(cached_shows)
            logger.info(f"[SCAN] Cached {len(cached_shows)} TV shows for library {lib_id} ({len(new_shows)} new)")

            # Trigger auto-generation for new TV shows
            if new_shows:
                try:
                    results = auto_generate.process_new_content_for_library(
                        library_id=lib_id,
                        new_movies=[],
                        new_tv_shows=new_shows,
                        auto_send=True
                    )
                    logger.info(f"[SCAN] Auto-generation complete for library {lib_id}: {results}")
                except Exception as e:
                    logger.error(f"[SCAN] Auto-generation failed for library {lib_id}: {e}")

            # Pre-populate streaming provider cache for new TV shows (best-effort)
            if new_shows:
                try:
                    from ..tmdb_client import get_watch_providers
                    from .. import database as _db
                    overlay_region = "US"
                    for cfg in _db.get_all_overlay_configs():
                        if any(e.get("type") == "streaming_platform_badge" for e in cfg.get("elements", [])):
                            overlay_region = cfg.get("streaming_region") or "US"
                            break
                    for show in new_shows:
                        tmdb_id = show.get("tmdb_id")
                        if tmdb_id:
                            get_watch_providers(int(tmdb_id), "tv", overlay_region)
                except Exception:
                    pass  # Never block scan for this

        # Process collections per library
        coll_cache_by_lib = {}
        for coll in collections_list:
            lib_id = coll.get("library_id") or "default"
            if lib_id not in coll_cache_by_lib:
                coll_cache_by_lib[lib_id] = []
            
            # Fetch poster
            poster_url = None
            try:
                poster_path = fetch_and_cache_poster(coll.get("key"), force_refresh=False)
                if poster_path:
                    poster_url = _poster_cache_url(coll.get("key"), poster_path)
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch poster for collection {coll.get('key')}: {e}")
            
            coll_cache_by_lib[lib_id].append({
                "rating_key": coll.get("key"),
                "title": coll.get("title"),
                "year": coll.get("year"),
                "added_at": coll.get("addedAt"),
                "poster_url": poster_url or coll.get("poster"),
                "library_id": lib_id,
            })
            
            processed += 1
            if processed % 50 == 0 or processed == total_items:
                logger.info("[SCAN] Overall progress %d/%d", processed, total_items)
            scan_status.update({"processed": processed, "current": coll.get("title") or ""})
        
        # Bulk refresh collection cache per library. cache.refresh_collections_from_list()
        # expects the *raw* _get_plex_collections() shape (a "key" field, etc.) and
        # translates it into the rating_key-shaped rows the DB layer wants — but
        # coll_cache_by_lib entries above are already built directly in that
        # rating_key shape, so going through that translator a second time read a
        # nonexistent "key" field as None on every item, silently overwriting every
        # scanned collection's cached rating_key with NULL. Call the DB layer
        # directly instead, since the shape here already matches what it expects.
        for lib_id, cached_colls in coll_cache_by_lib.items():
            db.bulk_refresh_collection_cache(cached_colls, library_id=lib_id)
            logger.info(f"[SCAN] Cached {len(cached_colls)} collections for library {lib_id}")

        logger.info(f"[SCAN] Completed full library sync")
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


def _get_unique_asset_roots() -> List[Path]:
    """Browsable output roots across both the movie and TV save-location templates.
    Most installs have both templates resolve to the same root (the default templates
    both start with "/config/output/{library}/..."), but a user can point them at
    different locations, so Local Assets needs to cover both rather than only the
    legacy single "saveLocation" field it used to read."""
    candidates: List[Path] = []
    for media_type in ("movie", "tv-show"):
        root = resolve_save_root(media_type)
        if root not in candidates:
            candidates.append(root)
    # Drop any root nested inside another candidate — walking the parent already covers it.
    return [r for r in candidates if not any(r != other and r.is_relative_to(other) for other in candidates)]


def _find_asset_under_roots(path: str) -> Path:
    """Resolve a relative asset path against each candidate output root, returning
    the first that both stays within its root (blocks traversal) and exists on disk.
    Raises 403 if `path` escapes every candidate root, or 404 if it's contained but
    doesn't exist anywhere."""
    roots = _get_unique_asset_roots()
    any_contained = False
    for root in roots:
        candidate = (root / path).resolve()
        if candidate.is_relative_to(root):
            any_contained = True
            if candidate.exists() and candidate.is_file():
                return candidate
    if not any_contained:
        raise HTTPException(status_code=403, detail="Access denied")
    raise HTTPException(status_code=404, detail="File not found")


@router.get("/local-assets")
def api_local_assets():
    """List all saved poster assets from the movie/TV output folders defined in UI settings."""
    try:
        output_roots = _get_unique_asset_roots()

        assets = []
        # Supported image extensions
        image_extensions = {'.jpg', '.jpeg', '.png', '.webp'}

        for output_root in output_roots:
            if not output_root.exists():
                continue
            for root, dirs, files in os.walk(output_root):
                for file in files:
                    file_path = Path(root) / file
                    if file_path.suffix.lower() in image_extensions:
                        try:
                            stat = file_path.stat()
                            rel_path = file_path.relative_to(output_root)

                            # Read library metadata from the image (cached — see
                            # _read_image_metadata — so unchanged files are instant
                            # on repeat "Refresh" clicks instead of re-opening every file)
                            metadata = _read_image_metadata(file_path, stat_result=stat)

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
                                if metadata.get("rating_key"):
                                    asset["rating_key"] = metadata.get("rating_key")
                                    asset["is_tv"] = metadata.get("is_tv", False)

                            assets.append(asset)
                        except Exception as e:
                            logger.debug(f"[LOCAL_ASSETS] Failed to stat {file_path}: {e}")

        # Sort by modified time (newest first)
        assets.sort(key=lambda x: x['modified'], reverse=True)

        logger.info(f"[LOCAL_ASSETS] Found {len(assets)} assets in {[str(r) for r in output_roots]}")
        return {
            "assets": assets,
            "count": len(assets),
            "output_path": str(output_roots[0]) if output_roots else "",
            "output_paths": [str(r) for r in output_roots],
        }
    except Exception as e:
        logger.error(f"[LOCAL_ASSETS] Failed to list assets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list local assets: {e}")


@router.get("/local-assets/{path:path}")
def api_local_asset_file(path: str):
    """Serve a local asset file."""
    try:
        file_path = _find_asset_under_roots(path)
        return FileResponse(file_path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LOCAL_ASSETS] Failed to serve file {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to serve file: {e}")


def _delete_local_asset_file(path: str) -> dict:
    """Delete a single local asset file and clean up any empty parent folders left
    behind. Shared by the single-file DELETE endpoint and the bulk-delete endpoint."""
    file_path = _find_asset_under_roots(path)
    output_root = next(r for r in _get_unique_asset_roots() if file_path.is_relative_to(r))

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


@router.delete("/local-assets/{path:path}")
def api_delete_local_asset(path: str):
    """Delete a local asset file."""
    try:
        return _delete_local_asset_file(path)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[LOCAL_ASSETS] Failed to delete file {path}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {e}")


class LocalAssetBulkDeleteRequest(BaseModel):
    paths: List[str]  # relative asset paths, as returned by GET /local-assets


@router.post("/local-assets/delete-bulk")
def api_local_assets_delete_bulk(req: LocalAssetBulkDeleteRequest):
    """Bulk-delete one or more saved local asset files."""
    results = []
    for rel_path in req.paths:
        entry: dict = {"path": rel_path}
        try:
            _delete_local_asset_file(rel_path)
            entry["status"] = "ok"
        except HTTPException as e:
            entry.update(status="error", reason=str(e.detail))
        except Exception as e:
            logger.error(f"[LOCAL_ASSETS] Failed to delete file {rel_path}: {e}")
            entry.update(status="error", reason=str(e))
        results.append(entry)

    succeeded = sum(1 for r in results if r["status"] == "ok")
    return {"status": "ok", "succeeded": succeeded, "total": len(results), "results": results}
