from typing import Optional

from fastapi import APIRouter

from .. import cache

router = APIRouter()


@router.get("/cache/movies")
def api_cache_movies(library_id: Optional[str] = None):
    """Return cached Plex movies with any stored labels/poster/tmdb info."""
    return {"movies": cache.get_cached_movies(library_id=library_id)}

