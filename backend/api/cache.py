from typing import Optional

from fastapi import APIRouter, Body

from ..config import logger, get_plex_movies, get_movie_tmdb_id
from .. import cache
from .movies import api_movie_labels

router = APIRouter()


@router.get("/cache/movies")
def api_cache_movies():
    """Return cached Plex movies with any stored labels/poster/tmdb info."""
    return {"movies": cache.get_cached_movies()}


@router.post("/cache/refresh")
def api_cache_refresh(
    include_labels: bool = Body(default=False),
    include_tmdb: bool = Body(default=False),
):
    """
    Refresh the cache from Plex. Optionally fetch labels and TMDB IDs for each movie.
    This can be scheduled (e.g., cron hitting the endpoint) or run on-demand.
    """
    movies = get_plex_movies()
    for m in movies:
        labels = None
        tmdb_id: Optional[int] = None

        if include_labels:
            try:
                labels_resp = api_movie_labels(m.key)
                labels = getattr(labels_resp, "labels", None) or []
            except Exception as e:
                logger.debug("[CACHE] label fetch failed for %s: %s", m.key, e)

        if include_tmdb:
            try:
                tmdb_id = get_movie_tmdb_id(m.key)
            except Exception as e:
                logger.debug("[CACHE] tmdb fetch failed for %s: %s", m.key, e)

        cache.upsert_movie(m, tmdb_id=tmdb_id, labels=labels)

    return {"status": "ok", "count": len(movies), "labels_included": include_labels, "tmdb_included": include_tmdb}
