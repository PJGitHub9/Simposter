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
        r.raise_for_status()
        logger.debug("[TVDB] GET %s params=%s", url, params)
        return r.json()
    except Exception as e:
        text = ""
        if hasattr(e, "response") and e.response is not None:
            text = str(e.response.text)[:200]
        logger.warning("[TVDB] Request failed url=%s err=%s body=%s", url, e, text)
        raise TVDBError(f"TVDB request failed: {e}")


def get_series_images(tvdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch posters/backdrops/logos for a TV series from TVDB.
    """
    data = _tvdb_get(f"/series/{tvdb_id}/artworks")
    artworks = data.get("data") or []

    posters: List[Dict[str, Any]] = []
    backdrops: List[Dict[str, Any]] = []
    logos: List[Dict[str, Any]] = []

    for art in artworks:
        atype = (art.get("type") or "").lower()
        image_url = art.get("image")
        thumb_url = art.get("thumbnail")
        if not image_url:
            continue
        mapped = {
            "url": image_url,
            "thumb": thumb_url or image_url,
            "source": "tvdb",
            "language": art.get("language"),
            "type": atype,
        }
        if "poster" in atype:
            posters.append(mapped)
        elif any(x in atype for x in ["fanart", "background", "backdrop"]):
            backdrops.append(mapped)
        elif "logo" in atype or "clearlogo" in atype:
            logos.append(mapped)

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
