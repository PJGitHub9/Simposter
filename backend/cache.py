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


def refresh_from_list(movies):
    """Replace cache with the provided list (basic metadata only). Accepts Movie objects or dicts."""
    try:
        payload = []
        for m in movies:
            # Handle both Movie objects and dicts
            if isinstance(m, dict):
                payload.append({
                    "rating_key": m.get("rating_key") or m.get("key"),
                    "title": m.get("title"),
                    "year": m.get("year"),
                    "added_at": m.get("added_at") or m.get("addedAt"),
                    "poster_url": m.get("poster_url"),
                    "labels": m.get("labels") or [],
                    "library_id": m.get("library_id") or "default",
                })
            else:
                # Movie object
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


# TV cache helpers
def upsert_tv_show(show: Dict, tmdb_id: Optional[int] = None, tvdb_id: Optional[int] = None, poster_url: Optional[str] = None, labels: Optional[List[str]] = None, seasons: Optional[List[Dict]] = None):
    try:
        db.upsert_tv_cache(
            rating_key=show.get("key"),
            title=show.get("title") or "",
            year=show.get("year"),
            added_at=show.get("addedAt"),
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            poster_url=poster_url,
            labels=labels,
            seasons=seasons,
            library_id=show.get("library_id") or "default",
        )
    except Exception as e:
        log.debug("[CACHE] failed to upsert tv show %s: %s", show.get("key"), e, exc_info="database is locked" not in str(e).lower())


def update_tv_labels(rating_key: str, labels: List[str], library_id: str = "default"):
    try:
        db.update_tv_labels(rating_key, labels, library_id=library_id)
    except Exception as e:
        log.debug("[CACHE] failed to update tv labels for %s: %s", rating_key, e)


def update_tv_tmdb(rating_key: str, tmdb_id: Optional[int], library_id: str = "default"):
    try:
        db.update_tv_tmdb(rating_key, tmdb_id, library_id=library_id)
    except Exception as e:
        log.debug("[CACHE] failed to update tv tmdb for %s: %s", rating_key, e)


def update_tv_tvdb(rating_key: str, tvdb_id: Optional[int], library_id: str = "default"):
    try:
        db.update_tv_tvdb(rating_key, tvdb_id, library_id=library_id)
    except Exception as e:
        log.debug("[CACHE] failed to update tv tvdb for %s: %s", rating_key, e)


def update_tv_poster(rating_key: str, poster_url: Optional[str], library_id: str = "default"):
    try:
        db.update_tv_poster(rating_key, poster_url, library_id=library_id)
    except Exception as e:
        log.debug("[CACHE] failed to update tv poster for %s: %s", rating_key, e)


def update_tv_seasons(rating_key: str, seasons: List[Dict], library_id: str = "default"):
    try:
        db.update_tv_seasons(rating_key, seasons, library_id=library_id)
    except Exception as e:
        log.debug("[CACHE] failed to update tv seasons for %s: %s", rating_key, e)


def refresh_tv_from_list(shows: List[Dict]):
    try:
        payload = []
        for s in shows:
            # Handle both dict formats: from scan (has "rating_key") and from API (has "key")
            rating_key = s.get("rating_key") or s.get("key")
            added_at = s.get("added_at") or s.get("addedAt")
            poster_url = s.get("poster_url") or s.get("poster")
            
            payload.append({
                "rating_key": rating_key,
                "title": s.get("title"),
                "year": s.get("year"),
                "added_at": added_at,
                "tmdb_id": s.get("tmdb_id"),
                "tvdb_id": s.get("tvdb_id"),
                "poster_url": poster_url,
                "labels": s.get("labels"),
                "seasons": s.get("seasons"),
                "library_id": s.get("library_id") or "default",
            })
        by_lib: Dict[str, List[Dict]] = {}
        for item in payload:
            by_lib.setdefault(item["library_id"], []).append(item)
        for lib_id, items in by_lib.items():
            db.bulk_refresh_tv_cache(items, library_id=lib_id)
            log.info("[CACHE] refreshed %d tv shows for library %s", len(items), lib_id)
    except Exception as e:
        log.warning("[CACHE] tv refresh failed: %s", e)


def get_cached_tv_shows(library_id: Optional[str] = None) -> List[Dict]:
    return db.get_cached_tv_shows(library_id=library_id)


def get_tv_cache_stats(library_id: Optional[str] = None) -> Dict[str, any]:
    return db.get_tv_cache_stats(library_id=library_id)


# Collection cache helpers
def upsert_collection(collection: Dict, library_id: str = "default"):
    try:
        db.upsert_collection_cache(
            rating_key=collection.get("key"),
            title=collection.get("title") or "",
            year=collection.get("year"),
            added_at=collection.get("addedAt"),
            poster_url=collection.get("poster"),
            library_id=collection.get("library_id") or library_id or "default",
        )
    except Exception as e:
        log.debug("[CACHE] failed to upsert collection %s: %s", collection.get("key"), e, exc_info="database is locked" not in str(e).lower())


def refresh_collections_from_list(collections: List[Dict]):
    try:
        payload = []
        for c in collections:
            payload.append({
                "rating_key": c.get("key"),
                "title": c.get("title") or "",
                "year": c.get("year"),
                "added_at": c.get("addedAt"),
                "poster_url": c.get("poster"),
                "library_id": c.get("library_id") or "default",
            })
        by_lib: Dict[str, List[Dict]] = {}
        for item in payload:
            by_lib.setdefault(item["library_id"], []).append(item)
        for lib_id, items in by_lib.items():
            db.bulk_refresh_collection_cache(items, library_id=lib_id)
            log.info("[CACHE] refreshed %d collections for library %s", len(items), lib_id)
    except Exception as e:
        log.warning("[CACHE] collections refresh failed: %s", e)


def get_cached_collections(library_id: Optional[str] = None) -> List[Dict]:
    return db.get_cached_collections(library_id=library_id)


def get_collection_cache_stats(library_id: Optional[str] = None) -> Dict[str, any]:
    return db.get_collection_cache_stats(library_id=library_id)
