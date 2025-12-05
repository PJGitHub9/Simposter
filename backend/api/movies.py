import xml.etree.ElementTree as ET
from typing import List, Optional
from pathlib import Path
import os
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, FileResponse, JSONResponse

import requests
from ..config import settings, plex_headers, logger, get_plex_movies, get_movie_tmdb_id, plex_session, POSTER_CACHE_DIR
from .. import cache, database as db
from ..schemas import Movie, MovieTMDbResponse, LabelsResponse, LabelsRemoveRequest
from ..tmdb_client import get_images_for_movie, TMDBError

router = APIRouter()


def _poster_cache_path(rating_key: str) -> Optional[Path]:
    cache_dir = Path(POSTER_CACHE_DIR)
    for ext in ("jpg", "jpeg", "png", "webp"):
        candidate = cache_dir / f"{rating_key}.{ext}"
        if candidate.exists():
            return candidate
    return None


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


def _cache_fresh(max_age_seconds: int) -> bool:
    stats = db.get_movie_cache_stats()
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


@router.get("/movies", response_model=List[Movie])
def api_movies(force_refresh: bool = False, max_age: int = 900):
    """
    Return movies. Uses cached DB if it is fresh (default 15 minutes) unless force_refresh=true.
    """
    if not force_refresh and _cache_fresh(max_age):
        cached = cache.get_cached_movies()
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
                }
                for m in cached
            ]

    # Otherwise hit Plex and refresh the cache
    movies = get_plex_movies()
    return [{**m.model_dump(), "poster": None} for m in movies]


@router.get("/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


@router.get("/movie/{rating_key}/labels", response_model=LabelsResponse)
def api_movie_labels(rating_key: str):
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    r = plex_session.get(url, headers=plex_headers(), timeout=10)
    r.raise_for_status()

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
        return get_images_for_movie(tmdb_id)
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


@router.post("/scan-library")
def api_scan_library():
    """Scan entire Plex library and return full data for caching."""
    try:
        movies = get_plex_movies()
        logger.info(f"[SCAN] Starting library scan for {len(movies)} movies")

        # Build complete response with posters and labels
        result = {
            "status": "ok",
            "count": len(movies),
            "movies": [],
            "posters": {},
            "labels": {}
        }

        for movie in movies:
            # Add movie data
            result["movies"].append({
                "key": movie.key,
                "title": movie.title,
                "year": movie.year,
                "addedAt": movie.addedAt
            })

            # Fetch poster URL
            try:
                poster_data = api_movie_poster(movie.key)
                result["posters"][movie.key] = poster_data.get("url")
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch poster for {movie.key}: {e}")
                result["posters"][movie.key] = None

            # Fetch labels
            try:
                labels_data = api_movie_labels(movie.key)
                result["labels"][movie.key] = labels_data.labels
            except Exception as e:
                logger.debug(f"[SCAN] Failed to fetch labels for {movie.key}: {e}")
                result["labels"][movie.key] = []

        logger.info(f"[SCAN] Completed library scan - {len(movies)} movies, {len(result['posters'])} posters, {len(result['labels'])} label sets")
        return result
    except Exception as e:
        logger.error(f"[SCAN] Failed to scan library: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to scan library: {e}")


@router.get("/local-assets")
def api_local_assets():
    """List all saved poster assets from the output folder."""
    try:
        output_root = Path(settings.OUTPUT_ROOT)
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

                        assets.append({
                            "filename": file,
                            "path": str(rel_path),
                            "full_path": str(file_path),
                            "size": stat.st_size,
                            "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                            "folder": str(rel_path.parent) if rel_path.parent != Path('.') else ""
                        })
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
        output_root = Path(settings.OUTPUT_ROOT)
        file_path = output_root / path

        # Security check: ensure the resolved path is still within OUTPUT_ROOT
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
