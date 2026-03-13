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
        # Mask API key in debug logging
        debug_params = {k: ("***" + v[-4:] if k == "api_key" and v else v) for k, v in params.items()}
        logger.debug("[TMDB] GET %s params=%s", url, debug_params)
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


# ---------------------------------------------------------------------------
# Watch Providers (streaming platform detection)
# ---------------------------------------------------------------------------

import re as _re

_PROVIDER_SLUG_MAP = {
    "Netflix": "netflix",
    "Amazon Prime Video": "prime-video",
    "Apple TV+": "apple-tv-plus",
    "Apple TV": "apple-tv-plus",
    "Disney Plus": "disney-plus",
    "Disney+": "disney-plus",
    "Max": "max",
    "HBO Max": "max",
    "Hulu": "hulu",
    "Paramount Plus": "paramount-plus",
    "Paramount+": "paramount-plus",
    "Peacock": "peacock",
    "Peacock Premium": "peacock",
    "Tubi TV": "tubi",
    "Crunchyroll": "crunchyroll",
    "Shudder": "shudder",
    "MUBI": "mubi",
    "BritBox": "britbox",
    "Acorn TV": "acorn-tv",
    "AMC+": "amc-plus",
    "AMC Plus": "amc-plus",
    "Starz": "starz",
    "Showtime": "showtime",
    "Epix": "epix",
}


def normalize_provider_name(name: str) -> str:
    """Normalize a TMDb provider name to a lowercase slug."""
    if name in _PROVIDER_SLUG_MAP:
        return _PROVIDER_SLUG_MAP[name]
    return _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


_STUDIO_SLUG_MAP = {
    # Major film studios
    "A24": "a24",
    "Netflix": "netflix",
    "Netflix Studios": "netflix",
    "Netflix Animation": "netflix",
    "Netflix Productions": "netflix",
    "Amazon MGM Studios": "amazon-mgm",
    "Amazon Studios": "amazon-mgm",
    "MGM": "amazon-mgm",
    "Apple Original Films": "apple-original",
    "Walt Disney Pictures": "disney",
    "Walt Disney Animation Studios": "disney",
    "Disney": "disney",
    "Marvel Studios": "marvel-studios",
    "Pixar": "pixar",
    "Pixar Animation Studios": "pixar",
    "Warner Bros.": "warner-bros",
    "Warner Bros. Pictures": "warner-bros",
    "Warner Bros. Television": "warner-bros",
    "Universal Pictures": "universal",
    "Universal Television": "universal",
    "Paramount Pictures": "paramount",
    "Paramount Network Television": "paramount",
    "Sony Pictures": "sony-pictures",
    "Columbia Pictures": "sony-pictures",
    "TriStar Pictures": "sony-pictures",
    "20th Century Studios": "20th-century",
    "20th Century Fox": "20th-century",
    "20th Century Fox Television": "20th-century",
    "Lionsgate": "lionsgate",
    "Lionsgate Films": "lionsgate",
    "Lionsgate Television": "lionsgate",
    "Blumhouse Productions": "blumhouse",
    "Blumhouse Television": "blumhouse",
    "Focus Features": "focus-features",
    "DreamWorks Animation": "dreamworks",
    "DreamWorks Pictures": "dreamworks",
    "Amblin Entertainment": "amblin",
    "Legendary Entertainment": "legendary",
    "Bad Robot": "bad-robot",
    # TV Networks
    "HBO": "hbo",
    "HBO Max": "hbo",
    "FX": "fx",
    "FX Networks": "fx",
    "FX Productions": "fx",
    "AMC": "amc",
    "AMC Networks": "amc",
    "Showtime": "showtime",
    "Starz": "starz",
    "CBS": "cbs",
    "NBC": "nbc",
    "ABC": "abc",
    "FOX": "fox",
    "Fox Broadcasting Company": "fox",
    "Hulu": "hulu",
    "Peacock": "peacock",
    "Apple TV+": "apple-tv-plus",
    "Disney+": "disney-plus",
}

_STUDIO_CACHE_KEY = "__studio__"


def normalize_studio_name(name: str) -> str:
    """Normalize a TMDb studio/network name to a lowercase slug."""
    if name in _STUDIO_SLUG_MAP:
        return _STUDIO_SLUG_MAP[name]
    return _re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def get_studio_name(tmdb_id: int, media_type: str = "movie") -> str:
    """
    Return the primary studio slug for a movie (production_companies[0]) or
    TV show (networks[0]). Uses the streaming_provider_cache table with a
    pseudo-region '__studio__' so no extra DB table is needed.

    Returns "" on any error so badge rendering is never blocked.
    """
    # 1. Check DB cache (reuses streaming_provider_cache, region='__studio__')
    try:
        cached = db.get_cached_providers(tmdb_id, media_type, _STUDIO_CACHE_KEY)
        if cached is not None:
            if cached:
                # If provider_id is missing the cache pre-dates company ID tracking — re-fetch
                if cached[0].get("provider_id") is not None:
                    return normalize_studio_name(cached[0].get("provider_name", ""))
            elif cached == []:
                return ""  # Previously cached "no studio" result
    except Exception:
        pass

    # 2. Fetch from TMDb
    studio_name = ""
    company_id: Optional[int] = None
    try:
        data = _tmdb_get(f"/{media_type}/{tmdb_id}", {})
        if media_type == "tv":
            companies = data.get("networks") or data.get("production_companies") or []
        else:
            companies = data.get("production_companies") or []
        if companies:
            studio_name = companies[0].get("name", "")
            company_id = companies[0].get("id")
        logger.debug("[TMDB] Studio for %s/%s: '%s' (company_id=%s)", media_type, tmdb_id, studio_name, company_id)
    except Exception as e:
        logger.debug("[TMDB] Studio fetch failed for %s/%s: %s", media_type, tmdb_id, e)

    # 3. Cache result — store company_id alongside name so callers can use it for asset lookup
    entry = [{"provider_name": studio_name, "provider_id": company_id}] if studio_name else []
    try:
        db.upsert_cached_providers(tmdb_id, media_type, _STUDIO_CACHE_KEY, entry)
    except Exception:
        pass

    return normalize_studio_name(studio_name) if studio_name else ""


def get_studio_company_id(tmdb_id: int, media_type: str = "movie") -> Optional[int]:
    """Return the TMDb company ID for the primary studio/network of an item.

    Reads from the same DB cache as get_studio_name() — no extra network call.
    Returns None if not cached or not available.
    """
    try:
        cached = db.get_cached_providers(tmdb_id, media_type, _STUDIO_CACHE_KEY)
        if cached:
            val = cached[0].get("provider_id")
            return int(val) if val is not None else None
    except Exception:
        pass
    return None


def get_watch_providers(tmdb_id: int, media_type: str = "movie", region: str = "US") -> list:
    """
    Return the flatrate (subscription) streaming providers for an item, sorted by display_priority.

    Checks the database cache first (7-day TTL). Falls back to the TMDb API and
    stores the result. Returns [] on any error so badge rendering is never blocked.
    """
    # 1. Check DB cache
    try:
        cached = db.get_cached_providers(tmdb_id, media_type, region)
        if cached is not None:
            return cached
    except Exception:
        pass

    # 2. Fetch from TMDb
    try:
        data = _tmdb_get(f"/{media_type}/{tmdb_id}/watch/providers", {})
        region_data = data.get("results", {}).get(region, {})
        flatrate = region_data.get("flatrate", [])
        providers = sorted(flatrate, key=lambda p: p.get("display_priority", 999))
        logger.debug("[TMDB] Watch providers for %s/%s (%s): %d provider(s)",
                     media_type, tmdb_id, region, len(providers))
    except Exception as e:
        logger.debug("[TMDB] Watch provider fetch failed for %s/%s: %s", media_type, tmdb_id, e)
        providers = []

    # 3. Store in DB cache regardless (even empty list)
    try:
        db.upsert_cached_providers(tmdb_id, media_type, region, providers)
    except Exception:
        pass

    return providers
