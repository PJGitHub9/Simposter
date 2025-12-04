# backend/tmdb_client.py
from typing import Dict, Any, List

import requests

from .config import logger, settings

TMDB_API_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"


class TMDBError(Exception):
    pass


def _tmdb_get(path: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.TMDB_API_KEY:
        logger.error("[TMDB] TMDB_API_KEY not set")
        raise TMDBError("TMDB_API_KEY not set")

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


def _make_img_url(file_path: str, size: str = "original") -> str:
    return f"{TMDB_IMG_BASE}/{size}{file_path}"


def _build_image_entry(p: Dict[str, Any], kind: str) -> Dict[str, Any]:
    path = p.get("file_path")
    if not path:
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

    return {
        "url": _make_img_url(path, "original"),
        "thumb": _make_img_url(path, thumb_size),
        "width": width,
        "height": height,
        "language": lang,
        "has_text": bool(lang),
    }


def get_images_for_movie(tmdb_id: int) -> Dict[str, List[Dict[str, Any]]]:
    logger.info("[TMDB] Fetching images tmdb_id=%s", tmdb_id)
    data = _tmdb_get(
        f"/movie/{tmdb_id}/images",
        {
            "include_image_language": "en,null",
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
    release_date = data.get("release_date", "")  # Format: YYYY-MM-DD
    year = release_date.split("-")[0] if release_date else ""

    logger.debug("[TMDB] tmdb_id=%s title='%s' year=%s", tmdb_id, title, year)

    return {
        "title": title,
        "original_title": original_title,
        "year": year,
        "release_date": release_date,
    }
