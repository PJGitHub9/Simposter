# backend/fanart_client.py
from typing import Dict, Any, List, Optional

import requests

from .config import logger, settings

FANART_MOVIE_API_BASE = "https://webservice.fanart.tv/v3/movies"
FANART_TV_API_BASE = "https://webservice.fanart.tv/v3/tv"


class FanartError(Exception):
    pass


def _fanart_get(base_url: str, lookup_id: int) -> Dict[str, Any]:
    """
    Fetch media data from Fanart.tv API.
    Returns raw API response with all artwork types.
    """
    if not settings.FANART_API_KEY:
        logger.warning("[FANART] FANART_API_KEY not set - please save your API key in Settings")
        return {}

    url = f"{base_url}/{lookup_id}"
    # Redact API key in logs
    api_key_redacted = settings.FANART_API_KEY[:8] + "..." if len(settings.FANART_API_KEY) > 8 else "***"
    params = {"api_key": settings.FANART_API_KEY}

    try:
        logger.info("[FANART] Fetching artwork for id=%s (key: %s)", lookup_id, api_key_redacted)
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()

        # Log what we got back
        hdmovielogo_count = len(data.get("hdmovielogo", []))
        movielogo_count = len(data.get("movielogo", []))
        clearlogo_count = len(data.get("clearlogo", []))
        total_logos = hdmovielogo_count + movielogo_count + clearlogo_count

        logger.info("[FANART] id=%s: Found %d logos (HD: %d, Standard: %d, Clear: %d)",
                   lookup_id, total_logos, hdmovielogo_count, movielogo_count, clearlogo_count)

        if total_logos > 0:
            # Log first logo URL for debugging
            first_logo = None
            if hdmovielogo_count > 0:
                first_logo = data["hdmovielogo"][0].get("url")
                logger.debug("[FANART] First HD logo: %s", first_logo)
            elif movielogo_count > 0:
                first_logo = data["movielogo"][0].get("url")
                logger.debug("[FANART] First standard logo: %s", first_logo)
            elif clearlogo_count > 0:
                first_logo = data["clearlogo"][0].get("url")
                logger.debug("[FANART] First clear logo: %s", first_logo)

        return data
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            logger.info("[FANART] No artwork found for id=%s (404)", lookup_id)
            return {}
        logger.warning("[FANART] HTTP %s error for id=%s: %s", e.response.status_code, lookup_id, e)
        return {}
    except Exception as e:
        logger.warning("[FANART] Request failed for id=%s: %s", lookup_id, e)
        return {}


def _build_entry(item: Dict[str, Any], kind: str) -> Dict[str, Any]:
    """
    Build standardized entry from Fanart.tv data.
    kind: "logo" | "clearart" | "poster" | "backdrop"
    """
    url = item.get("url")
    if not url:
        return {}

    lang = item.get("lang", "")
    # Fanart.tv uses "00" to indicate textless/unknown language
    if lang == "00":
        normalized_lang = "00"
    elif lang:
        normalized_lang = lang
    else:
        normalized_lang = None

    has_text_val = None
    if kind in ("logo", "clearart"):
        # Logos/clearart are typically textless; mark true textless for empty/00 language
        if lang in ("", None, "00"):
            has_text_val = False
    elif kind == "poster":
        # Treat language-neutral ("" or "00") as textless; others as having text
        has_text_val = False if lang in ("", None, "00") else True

    return {
        "url": url,
        "thumb": url,  # Fanart.tv doesn't provide thumbnails, use full URL
        "width": item.get("width"),
        "height": item.get("height"),
        "language": normalized_lang,
        "has_text": has_text_val,
        "source": "fanart",
        "type": kind,
    }


def get_logos_for_movie(tmdb_id: int) -> List[Dict[str, Any]]:
    """
    Fetch logos (and clearart) from Fanart.tv for a movie.

    Returns list of logo dictionaries matching TMDB format:
    {
        "url": str,
        "thumb": str,
        "width": int | None,
        "height": int | None,
        "language": str | None,
        "has_text": bool,
        "source": "fanart"
    }
    """
    logger.info("[FANART] Fetching logos for tmdb_id=%s", tmdb_id)
    data = _fanart_get(FANART_MOVIE_API_BASE, tmdb_id)

    if not data:
        return []

    logos: List[Dict[str, Any]] = []

    # Priority order: HD logos first, then regular logos
    # hdmovielogo: High-definition movie logos (PNG with transparency)
    for logo in data.get("hdmovielogo", []):
        entry = _build_entry(logo, "logo")
        if entry:
            logos.append(entry)

    # movielogo: Standard movie logos
    for logo in data.get("movielogo", []):
        entry = _build_entry(logo, "logo")
        if entry:
            logos.append(entry)

    # clearlogo: Additional clearlogos
    for logo in data.get("clearlogo", []):
        entry = _build_entry(logo, "logo")
        if entry:
            logos.append(entry)

    # hdmovieclearart / movieart: treat as clearart but surface with type for UI
    for art in data.get("hdmovieclearart", []):
        entry = _build_entry(art, "clearart")
        if entry:
            logos.append(entry)
    for art in data.get("movieart", []):
        entry = _build_entry(art, "clearart")
        if entry:
            logos.append(entry)

    if logos:
        logger.info("[FANART] Final logo list for tmdb_id=%s: %d items", tmdb_id, len(logos))
    else:
        logger.info("[FANART] No logos returned for tmdb_id=%s", tmdb_id)
    logger.debug("[FANART] tmdb_id=%s logos=%d", tmdb_id, len(logos))

    return logos


def get_images_for_movie(tmdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch all images from Fanart.tv for a movie.
    Currently returns logos + clearart (merged into logos) and movie posters to match editor expectations.

    Returns:
    {
        "posters": [],
        "backdrops": [],
        "logos": [...]
    }
    """
    data = _fanart_get(FANART_MOVIE_API_BASE, tmdb_id)
    logos = get_logos_for_movie(tmdb_id)

    posters: List[Dict[str, Any]] = []
    if data:
        for poster in (data.get("movieposter") or []):
            entry = _build_entry(poster, "poster")
            if entry:
                posters.append(entry)

    # Backdrops if needed later: moviebackground
    backdrops: List[Dict[str, Any]] = []
    if data:
        for bg in (data.get("moviebackground") or []):
            entry = _build_entry(bg, "backdrop")
            if entry:
                backdrops.append(entry)

    return {
        "posters": posters,
        "backdrops": backdrops,
        "logos": logos,
    }


def get_images_for_tv_show(tvdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch all images from Fanart.tv for a TV show (requires TVDB ID).
    Returns logos + clearart (merged into logos), posters, and backdrops.
    """
    data = _fanart_get(FANART_TV_API_BASE, tvdb_id)

    logos: List[Dict[str, Any]] = []
    if data:
        for logo in (data.get("hdtvlogo") or []):
            entry = _build_entry(logo, "logo")
            if entry:
                logos.append(entry)
        for logo in (data.get("clearlogo") or []):
            entry = _build_entry(logo, "logo")
            if entry:
                logos.append(entry)
        for art in (data.get("tvclearart") or []):
            entry = _build_entry(art, "clearart")
            if entry:
                logos.append(entry)

    posters: List[Dict[str, Any]] = []
    if data:
        for poster in (data.get("tvposter") or []):
            entry = _build_entry(poster, "poster")
            if entry:
                posters.append(entry)

    backdrops: List[Dict[str, Any]] = []
    if data:
        for bg in (data.get("showbackground") or []):
            entry = _build_entry(bg, "backdrop")
            if entry:
                backdrops.append(entry)

    return {
        "posters": posters,
        "backdrops": backdrops,
        "logos": logos,
    }
