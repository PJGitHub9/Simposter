# backend/api/mdblist.py
"""MDBList endpoints: key test, rating lookup (for the overlay preview), and the
cached lists overlays use. The client lives in backend/mdblist_client.py."""
from typing import Optional

from fastapi import APIRouter, HTTPException

from .. import database as db
from .. import mdblist_client as mdb

router = APIRouter()


@router.post("/test-mdblist")
def api_test_mdblist(payload: dict):
    """Test an MDBList API key (body, so the key stays out of access logs)."""
    return mdb.test_key(str(payload.get("api_key") or ""))


@router.get("/mdblist/ratings")
def api_mdblist_ratings(media_type: str = "movie", tmdb_id: Optional[str] = None,
                        tvdb_id: Optional[str] = None, rating_key: Optional[str] = None):
    """Rating fields for one item, as overlays see them (cached; fetches when stale)."""
    kind = "show" if media_type in ("tv", "show", "tv-show") else "movie"
    if not tmdb_id and rating_key:
        tmdb_id, cached_tvdb = db.get_ids_for_rating_key(rating_key)
        tvdb_id = tvdb_id or cached_tvdb
    if not tmdb_id and not tvdb_id:
        return {"configured": mdb.has_key(), "fields": {}, "raw": {}}
    data = mdb.get_ratings(kind, tmdb_id=tmdb_id, tvdb_id=tvdb_id) or {}
    return {"configured": mdb.has_key(), "fields": mdb.rating_fields(data), "raw": data.get("raw") or {}}


@router.get("/mdblist/lists")
def api_mdblist_lists():
    """Lists cached so far (every list an overlay rule refers to lands here)."""
    return {"configured": mdb.has_key(), "lists": db.get_all_list_cache()}


@router.post("/mdblist/lists/refresh")
def api_mdblist_list_refresh(payload: dict):
    """Fetch (or re-fetch) one list now. Body: {"url": "https://mdblist.com/lists/user/slug"}."""
    url = mdb.normalize_list_url(str(payload.get("url") or ""))
    if not url:
        raise HTTPException(400, "Not an MDBList list URL (https://mdblist.com/lists/<user>/<list>)")
    if not mdb.has_key():
        raise HTTPException(400, "Add an MDBList API key in Settings → General first")
    data = mdb.get_list(url, force=True)
    if not data:
        raise HTTPException(502, "Couldn't fetch that list from MDBList")
    return {"url": url, "title": data.get("title"), "movies": len(data["movie_ids"]), "shows": len(data["show_ids"])}


@router.delete("/mdblist/cache")
def api_mdblist_clear_cache():
    return {"deleted": db.clear_mdblist_cache()}
