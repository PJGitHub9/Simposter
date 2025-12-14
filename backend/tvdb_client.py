from typing import Dict, Any, List, Optional
import time
import threading

import requests

from .config import logger, settings

TVDB_API_BASE = "https://api4.thetvdb.com/v4"


class TVDBError(Exception):
    pass


_token_lock = threading.Lock()
_token: Optional[str] = None
_token_expiry: float = 0.0
_rate_lock = threading.Lock()
_rate_requests: List[float] = []


def _apply_rate_limit():
    """Apply rate limiting based on UI settings (requests per 10 seconds)."""
    try:
        from .api.ui_settings import _read_settings
        ui_settings = _read_settings(include_env=False)
        rate_limit = ui_settings.performance.tvdbRateLimit if ui_settings.performance else 20
    except Exception:
        rate_limit = 20

    with _rate_lock:
        now = time.time()
        window_start = now - 10.0
        global _rate_requests
        _rate_requests = [ts for ts in _rate_requests if ts > window_start]
        if len(_rate_requests) >= rate_limit:
            wait_time = 10.0 - (now - _rate_requests[0]) + 0.1
            if wait_time > 0:
                logger.debug("[TVDB] Rate limit reached (%d/%d), waiting %.2fs", len(_rate_requests), rate_limit, wait_time)
                time.sleep(wait_time)
                now = time.time()
                window_start = now - 10.0
                _rate_requests = [ts for ts in _rate_requests if ts > window_start]
        _rate_requests.append(now)


def _get_token() -> str:
    global _token, _token_expiry
    with _token_lock:
        if _token and time.time() < _token_expiry:
            return _token

        if not settings.TVDB_API_KEY:
            raise TVDBError("TVDB_API_KEY not set")

        payload = {"apikey": settings.TVDB_API_KEY}
        # Optional PIN support if provided via env
        if getattr(settings, "TVDB_PIN", None):
            payload["pin"] = settings.TVDB_PIN

        try:
            r = requests.post(f"{TVDB_API_BASE}/login", json=payload, timeout=10)
            r.raise_for_status()
            data = r.json().get("data") or {}
            token = data.get("token")
            if not token:
                raise TVDBError("TVDB login failed: no token returned")
            _token = token
            # TVDB tokens are typically valid for 24h; set a conservative 6h TTL
            _token_expiry = time.time() + 6 * 3600
            logger.debug("[TVDB] Obtained token")
            return _token
        except Exception as e:
            text = ""
            if hasattr(e, "response") and e.response is not None:
                text = str(e.response.text)[:200]
            logger.warning("[TVDB] Login failed: %s body=%s", e, text)
            raise TVDBError(f"TVDB login failed: {e}")


def _tvdb_get(path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    token = _get_token()
    _apply_rate_limit()
    headers = {"Authorization": f"Bearer {token}"}
    url = f"{TVDB_API_BASE}{path}"
    try:
        r = requests.get(url, headers=headers, params=params or {}, timeout=12)
        logger.debug("[TVDB] GET %s -> status=%d", url, r.status_code)
        r.raise_for_status()
        json_data = r.json()
        logger.debug("[TVDB] Response keys: %s", list(json_data.keys()) if isinstance(json_data, dict) else type(json_data))
        return json_data
    except requests.exceptions.HTTPError as e:
        text = ""
        if hasattr(e, "response") and e.response is not None:
            text = str(e.response.text)[:500]
        logger.warning("[TVDB] HTTP error url=%s status=%s body=%s", url, e.response.status_code if e.response else "unknown", text)
        raise TVDBError(f"TVDB HTTP {e.response.status_code if e.response else 'error'}: {text}")
    except Exception as e:
        logger.warning("[TVDB] Request failed url=%s err=%s type=%s", url, e, type(e).__name__)
        raise TVDBError(f"TVDB request failed: {e}")


def get_series_images(tvdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch posters/backdrops/logos for a TV series from TVDB.
    """
    # TVDB v4 uses /series/{id}/extended with meta=translations to get all artworks
    data = _tvdb_get(f"/series/{tvdb_id}/extended", params={"meta": "translations"})

    # Artworks are nested under data.artworks in the extended response
    series_data = data.get("data") or {}
    artworks = series_data.get("artworks") or []

    logger.debug("[TVDB] Series %d: received %d artworks", tvdb_id, len(artworks))
    if artworks and len(artworks) > 0:
        logger.debug("[TVDB] Sample artwork: %s", artworks[0])

    posters: List[Dict[str, Any]] = []
    backdrops: List[Dict[str, Any]] = []
    logos: List[Dict[str, Any]] = []

    for art in artworks:
        type_id = art.get("type")  # In TVDB v4, "type" contains the numeric ID
        image_url = art.get("image")
        thumb_url = art.get("thumbnail")

        if not image_url:
            continue

        mapped = {
            "url": image_url,
            "thumb": thumb_url or image_url,
            "source": "tvdb",
            "language": art.get("language"),
            "type": f"type_{type_id}",
        }

        # Match by type ID: 2=poster, 3=background/fanart, 5=clearlogo, 14=clearlogo
        if type_id == 2:
            posters.append(mapped)
        elif type_id == 3:
            backdrops.append(mapped)
        elif type_id in [14, 5]:
            logos.append(mapped)

    logger.debug("[TVDB] Series %d images: %d posters, %d backdrops, %d logos",
                 tvdb_id, len(posters), len(backdrops), len(logos))

    return {"posters": posters, "backdrops": backdrops, "logos": logos}


def get_season_images(tvdb_id: int, season_number: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch season-specific posters from TVDB.
    Returns posters filtered to the specific season, plus series-level logos/backdrops.
    """
    # Get all artworks for the series using the extended endpoint
    data = _tvdb_get(f"/series/{tvdb_id}/extended", params={"meta": "translations"})

    # Artworks are nested under data.artworks in the extended response
    series_data = data.get("data") or {}
    artworks = series_data.get("artworks") or []

    logger.debug("[TVDB] Season %d search: received %d total artworks", season_number, len(artworks))

    posters: List[Dict[str, Any]] = []
    backdrops: List[Dict[str, Any]] = []
    logos: List[Dict[str, Any]] = []

    for art in artworks:
        type_id = art.get("type")  # In TVDB v4, "type" contains the numeric ID
        image_url = art.get("image")
        thumb_url = art.get("thumbnail")
        season_num = art.get("seasonId")

        if not image_url:
            continue

        mapped = {
            "url": image_url,
            "thumb": thumb_url or image_url,
            "source": "tvdb",
            "language": art.get("language"),
            "type": f"type_{type_id}",
        }

        # Season posters: only include if they match the season number
        if type_id == 2 and season_num is not None:
            if int(season_num) == season_number:
                posters.append(mapped)
                logger.debug("[TVDB] Found season %d poster: %s", season_number, image_url[:50])
        # Series-level backdrops and logos (no season filtering)
        elif type_id == 3 and season_num is None:
            backdrops.append(mapped)
        elif type_id in [14, 5] and season_num is None:
            logos.append(mapped)

    logger.debug("[TVDB] Season %d images: %d posters, %d backdrops, %d logos",
                 season_number, len(posters), len(backdrops), len(logos))

    return {"posters": posters, "backdrops": backdrops, "logos": logos}


def get_movie_images(tvdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch posters/backdrops/logos for a movie from TVDB.
    Uses the same structure as series images.
    """
    # TVDB v4 uses /movies/{id}/extended for movie artworks
    data = _tvdb_get(f"/movies/{tvdb_id}/extended", params={"meta": "translations"})

    # Artworks are nested under data.artworks in the extended response
    movie_data = data.get("data") or {}
    artworks = movie_data.get("artworks") or []

    logger.debug("[TVDB] Movie %d: received %d artworks", tvdb_id, len(artworks))
    if artworks and len(artworks) > 0:
        logger.debug("[TVDB] Sample artwork: %s", artworks[0])

    posters: List[Dict[str, Any]] = []
    backdrops: List[Dict[str, Any]] = []
    logos: List[Dict[str, Any]] = []

    for art in artworks:
        type_id = art.get("type")  # In TVDB v4, "type" contains the numeric ID
        image_url = art.get("image")
        thumb_url = art.get("thumbnail")

        if not image_url:
            continue

        mapped = {
            "url": image_url,
            "thumb": thumb_url or image_url,
            "source": "tvdb",
            "language": art.get("language"),
            "type": f"type_{type_id}",
        }

        # Match by type ID: 2=poster, 3=background/fanart, 5=clearlogo, 14=clearlogo
        if type_id == 2:
            posters.append(mapped)
        elif type_id == 3:
            backdrops.append(mapped)
        elif type_id in [14, 5]:
            logos.append(mapped)

    logger.debug("[TVDB] Movie %d images: %d posters, %d backdrops, %d logos",
                 tvdb_id, len(posters), len(backdrops), len(logos))

    return {"posters": posters, "backdrops": backdrops, "logos": logos}


def test_tvdb_key(api_key: str) -> Dict[str, Any]:
    """Simple key test: attempt login."""
    try:
        r = requests.post(f"{TVDB_API_BASE}/login", json={"apikey": api_key}, timeout=10)
        r.raise_for_status()
        return {"status": "ok", "message": "API key valid"}
    except Exception as e:
        text = ""
        if hasattr(e, "response") and e.response is not None:
            text = str(e.response.text)[:200]
        return {"status": "error", "error": f"{e}", "body": text}
