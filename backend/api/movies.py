import xml.etree.ElementTree as ET
from typing import List
from pathlib import Path
import os
from datetime import datetime

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, FileResponse

from ..config import settings, plex_headers, logger, get_plex_movies, get_movie_tmdb_id
from ..schemas import Movie, MovieTMDbResponse, LabelsResponse, LabelsRemoveRequest
from ..tmdb_client import get_images_for_movie, TMDBError

router = APIRouter()


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
        r = requests.get(url, headers=headers, timeout=10, verify=settings.PLEX_VERIFY_TLS)
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


@router.get("/movies", response_model=List[Movie])
def api_movies():
    return get_plex_movies()


@router.get("/movie/{rating_key}/tmdb", response_model=MovieTMDbResponse)
def api_movie_tmdb(rating_key: str):
    tmdb_id = get_movie_tmdb_id(rating_key)
    return MovieTMDbResponse(tmdb_id=tmdb_id)


@router.get("/movie/{rating_key}/labels", response_model=LabelsResponse)
def api_movie_labels(rating_key: str):
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    r = requests.get(url, headers=plex_headers(), timeout=10, verify=settings.PLEX_VERIFY_TLS)
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

    return LabelsResponse(labels=sorted(labels))


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
def api_movie_poster(rating_key: str):
    """Proxy poster images through the backend to avoid CORS issues."""
    direct = f"{settings.PLEX_URL}/library/metadata/{rating_key}/thumb"

    # Try direct poster URL
    try:
        r = requests.get(direct, headers=plex_headers(), timeout=5, verify=settings.PLEX_VERIFY_TLS)
        if r.status_code == 200:
            # Return the image data directly instead of the URL
            content_type = r.headers.get('content-type', 'image/jpeg')
            return Response(content=r.content, media_type=content_type)
    except Exception as e:
        logger.debug(f"Failed to fetch poster directly for {rating_key}: {e}")

    # Fallback: parse metadata for thumb path
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
    try:
        r = requests.get(url, headers=plex_headers(), timeout=10, verify=settings.PLEX_VERIFY_TLS)
        r.raise_for_status()
        root = ET.fromstring(r.text)
        for video in root.findall(".//Video"):
            thumb = video.get("thumb")
            if thumb:
                thumb_url = f"{settings.PLEX_URL}{thumb}"
                poster_r = requests.get(thumb_url, headers=plex_headers(), timeout=5, verify=settings.PLEX_VERIFY_TLS)
                if poster_r.status_code == 200:
                    content_type = poster_r.headers.get('content-type', 'image/jpeg')
                    return Response(content=poster_r.content, media_type=content_type)
    except Exception as e:
        logger.debug(f"Failed to fetch poster via metadata for {rating_key}: {e}")

    # Return 404 if no poster found
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
