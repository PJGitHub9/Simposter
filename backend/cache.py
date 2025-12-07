"""Lightweight cache helpers for Plex library metadata."""
from typing import List, Dict, Optional
import logging

from .schemas import Movie
from . import database as db

log = logging.getLogger("simposter")


def upsert_movie(movie: Movie, tmdb_id: Optional[int] = None, poster_url: Optional[str] = None, labels: Optional[List[str]] = None):
    """Store/update a single movie in cache."""
    try:
        db.upsert_movie_cache(
            rating_key=movie.key,
            title=movie.title,
            year=movie.year,
            added_at=movie.addedAt,
            tmdb_id=tmdb_id,
            poster_url=poster_url,
            labels=labels,
            library_id=getattr(movie, "library_id", None) or "default",
        )
    except Exception as e:
        log.debug("[CACHE] failed to upsert %s: %s", movie.key, e, exc_info="database is locked" not in str(e).lower())


def update_labels(rating_key: str, labels: List[str]):
    try:
        db.update_movie_labels(rating_key, labels)
    except Exception as e:
        log.debug("[CACHE] failed to update labels for %s: %s", rating_key, e)


def update_tmdb(rating_key: str, tmdb_id: Optional[int]):
    try:
        db.update_movie_tmdb(rating_key, tmdb_id)
    except Exception as e:
        log.debug("[CACHE] failed to update tmdb for %s: %s", rating_key, e)


def update_poster(rating_key: str, poster_url: Optional[str]):
    try:
        db.update_movie_poster(rating_key, poster_url)
    except Exception as e:
        log.debug("[CACHE] failed to update poster for %s: %s", rating_key, e)


def refresh_from_list(movies: List[Movie]):
    """Replace cache with the provided list (basic metadata only)."""
    try:
        payload = []
        for m in movies:
            payload.append({
                "rating_key": m.key,
                "title": m.title,
                "year": m.year,
                "added_at": m.addedAt,
                "library_id": getattr(m, "library_id", None) or "default",
            })
        # Refresh per library to avoid deleting other libraries
        by_lib = {}
        for m in payload:
            by_lib.setdefault(m["library_id"], []).append(m)
        for lib_id, items in by_lib.items():
            db.bulk_refresh_cache(items, library_id=lib_id)
            log.info("[CACHE] refreshed %d movies for library %s", len(items), lib_id)
    except Exception as e:
        log.warning("[CACHE] refresh failed: %s", e)


def get_cached_movies(library_id: Optional[str] = None) -> List[Dict]:
    return db.get_cached_movies(library_id=library_id)
