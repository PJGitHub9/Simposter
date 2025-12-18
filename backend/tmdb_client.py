# backend/tmdb_client.py
from typing import Dict, Any, List, Optional
import time
import threading

import requests

from .config import logger, settings
from . import database as db

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


class TMDBError(Exception):
    pass


# Rate limiting: Track requests in a sliding window
_rate_limit_lock = threading.Lock()
_rate_limit_requests = []  # List of (timestamp,) tuples


def _apply_rate_limit():
    """Apply rate limiting based on UI settings (requests per 10 seconds)."""
    # Get rate limit from UI settings
    try:
        from .api.ui_settings import _read_settings
        ui_settings = _read_settings(include_env=False)
        rate_limit = ui_settings.performance.tmdbRateLimit if ui_settings.performance else 40
    except Exception:
        rate_limit = 40  # Default to 40 requests per 10 seconds

    with _rate_limit_lock:
        now = time.time()
        window_start = now - 10.0  # 10 second window

        # Remove requests outside the window
        global _rate_limit_requests
        _rate_limit_requests = [ts for ts in _rate_limit_requests if ts > window_start]

        # Check if we're at the limit
        if len(_rate_limit_requests) >= rate_limit:
            # Calculate how long to wait
            oldest_request = _rate_limit_requests[0]
            wait_time = 10.0 - (now - oldest_request) + 0.1  # Add small buffer
            if wait_time > 0:
                logger.debug("[TMDB] Rate limit reached (%d/%d), waiting %.2fs", len(_rate_limit_requests), rate_limit, wait_time)
                time.sleep(wait_time)
                # Recalculate after sleep
                now = time.time()
                window_start = now - 10.0
                _rate_limit_requests = [ts for ts in _rate_limit_requests if ts > window_start]

        # Record this request
        _rate_limit_requests.append(now)


def _tmdb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.TMDB_API_KEY:
        logger.error("[TMDB] TMDB_API_KEY not set")
        raise TMDBError("TMDB_API_KEY not set")

    # Apply rate limiting
    _apply_rate_limit()

    url = f"{TMDB_API_BASE}{path}"
    params = dict(params)
    params["api_key"] = settings.TMDB_API_KEY

    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        logger.debug("[TMDB] GET %s params=%s", url, params)
        return r.json()
    except Exception as e:
        text = ""
        if hasattr(e, "response") and e.response is not None:
            text = str(e.response.text)[:200]
        logger.warning("[TMDB] Request failed url=%s status=%s err=%s body=%s", url, getattr(e, "response", None), e, text)
        raise TMDBError(f"TMDb request failed: {e}") from e


def get_tv_external_ids(tmdb_id: int) -> Dict[str, Any]:
    """Get external IDs (including TVDB) for a TV show."""
    return _tmdb_get(f"/tv/{tmdb_id}/external_ids", {})


def get_movie_external_ids(tmdb_id: int) -> Dict[str, Any]:
    """Get external IDs (including IMDB) for a movie."""
    return _tmdb_get(f"/movie/{tmdb_id}/external_ids", {})


def _make_img_url(file_path: str, size: str = "original") -> str:
    return f"{TMDB_IMG_BASE}/{size}{file_path}"


def _build_image_entry(p: Dict[str, Any], kind: str) -> Dict[str, Any]:
    path = p.get("file_path")
    if not path:
        return {}
    
    # Skip SVG files for posters and backdrops (PIL can't handle them)
    # But allow SVG logos - they'll be handled by cairosvg if available, or skipped during render
    if path.lower().endswith('.svg') and kind != "logo":
        return {}

    lang = p.get("iso_639_1")
    width = p.get("width")
    height = p.get("height")

    if kind == "logo":
        thumb_size = "w300"
    elif kind == "backdrop":
        thumb_size = "w780"
    else:
        thumb_size = "w342"

    entry = {
        "url": _make_img_url(path, "original"),
        "thumb": _make_img_url(path, thumb_size),
        "width": width,
        "height": height,
        "language": lang,
        "has_text": bool(lang),
    }
    if kind == "logo":
        entry["source"] = "tmdb"
        entry["type"] = "logo"
    return entry


def _build_lang_param(language_preference: Optional[str], original_language: Optional[str]) -> str:
    """Build TMDB include_image_language parameter honoring prefs + null."""
    langs = []
    if language_preference:
        langs.append(language_preference)
    if original_language and original_language not in langs:
        langs.append(original_language)
    if "en" not in langs:
        langs.append("en")
    if "null" not in langs:
        langs.append("null")
    # Deduplicate preserving order
    seen = set()
    ordered = []
    for lang in langs:
        if lang in seen:
            continue
        seen.add(lang)
        ordered.append(lang)
    return ",".join(ordered)


def get_images_for_movie(tmdb_id: int, original_language: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    logger.info("[TMDB] Fetching images tmdb_id=%s", tmdb_id)
    language_pref = db.get_setting("pref.language") or "en"
    include_lang = _build_lang_param(language_pref, original_language)
    data = _tmdb_get(
        f"/movie/{tmdb_id}/images",
        {
            "include_image_language": include_lang,
        },
    )

    posters: List[Dict[str, Any]] = []
    for p in data.get("posters", []):
        entry = _build_image_entry(p, "poster")
        if entry:
            posters.append(entry)

    backdrops: List[Dict[str, Any]] = []
    for b in data.get("backdrops", []):
        entry = _build_image_entry(b, "backdrop")
        if entry:
            backdrops.append(entry)

    logos: List[Dict[str, Any]] = []
    for l in data.get("logos", []):
        entry = _build_image_entry(l, "logo")
        if entry:
            logos.append(entry)

    logger.debug(
        "[TMDB] tmdb_id=%s posters=%d backdrops=%d logos=%d",
        tmdb_id,
        len(posters),
        len(backdrops),
        len(logos),
    )

    return {
        "posters": posters,
        "backdrops": backdrops,
        "logos": logos,
    }


def get_movie_details(tmdb_id: int) -> Dict[str, Any]:
    """
    Fetch movie details from TMDb (title, year, etc.)
    """
    logger.info("[TMDB] Fetching movie details tmdb_id=%s", tmdb_id)
    data = _tmdb_get(f"/movie/{tmdb_id}", {})

    title = data.get("title", "")
    original_title = data.get("original_title", "")
    original_language = data.get("original_language", "")
    release_date = data.get("release_date", "")  # Format: YYYY-MM-DD
    year = release_date.split("-")[0] if release_date else ""

    logger.debug("[TMDB] tmdb_id=%s title='%s' year=%s", tmdb_id, title, year)

    return {
        "title": title,
        "original_title": original_title,
        "original_language": original_language,
        "year": year,
        "release_date": release_date,
    }


def get_images_for_tv_show(tmdb_id: int, original_language: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch images for a TV show from TMDb."""
    logger.info("[TMDB] Fetching TV show images tmdb_id=%s", tmdb_id)
    language_pref = db.get_setting("pref.language") or "en"
    include_lang = _build_lang_param(language_pref, original_language)
    data = _tmdb_get(
        f"/tv/{tmdb_id}/images",
        {
            "include_image_language": include_lang,
        },
    )

    posters: List[Dict[str, Any]] = []
    for p in data.get("posters", []):
        entry = _build_image_entry(p, "poster")
        if entry:
            posters.append(entry)

    backdrops: List[Dict[str, Any]] = []
    for b in data.get("backdrops", []):
        entry = _build_image_entry(b, "backdrop")
        if entry:
            backdrops.append(entry)

    logos: List[Dict[str, Any]] = []
    for l in data.get("logos", []):
        entry = _build_image_entry(l, "logo")
        if entry:
            logos.append(entry)

    logger.debug(
        "[TMDB] TV show tmdb_id=%s posters=%d backdrops=%d logos=%d",
        tmdb_id,
        len(posters),
        len(backdrops),
        len(logos),
    )

    return {
        "posters": posters,
        "backdrops": backdrops,
        "logos": logos,
    }


def get_tv_show_details(tmdb_id: int) -> Dict[str, Any]:
    """Fetch TV show details from TMDb."""
    logger.info("[TMDB] Fetching TV show details tmdb_id=%s", tmdb_id)
    data = _tmdb_get(f"/tv/{tmdb_id}", {})

    name = data.get("name", "")
    original_name = data.get("original_name", "")
    original_language = data.get("original_language", "")
    first_air_date = data.get("first_air_date", "")
    year = first_air_date.split("-")[0] if first_air_date else ""
    number_of_seasons = data.get("number_of_seasons", 0)

    logger.debug("[TMDB] TV show tmdb_id=%s name='%s' year=%s seasons=%d", tmdb_id, name, year, number_of_seasons)

    return {
        "name": name,
        "original_name": original_name,
        "original_language": original_language,
        "year": year,
        "first_air_date": first_air_date,
        "number_of_seasons": number_of_seasons,
    }


def get_tv_season_images(tmdb_id: int, season_number: int, original_language: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch images for a specific TV show season from TMDb."""
    logger.info("[TMDB] Fetching TV season images tmdb_id=%s season=%d", tmdb_id, season_number)
    language_pref = db.get_setting("pref.language") or "en"
    include_lang = _build_lang_param(language_pref, original_language)
    data = _tmdb_get(
        f"/tv/{tmdb_id}/season/{season_number}/images",
        {
            "include_image_language": include_lang,
        },
    )

    posters: List[Dict[str, Any]] = []
    for p in data.get("posters", []):
        entry = _build_image_entry(p, "poster")
        if entry:
            posters.append(entry)

    logger.debug(
        "[TMDB] TV season tmdb_id=%s season=%d posters=%d",
        tmdb_id,
        season_number,
        len(posters),
    )

    return {
        "posters": posters,
        "backdrops": [],
        "logos": [],
    }
