from fastapi import APIRouter, Query
from typing import Optional, List
from pydantic import BaseModel

from .. import database as db

router = APIRouter()


class PosterStatusRequest(BaseModel):
    rating_keys: Optional[List[str]] = None
    library_id: Optional[str] = None


@router.get("/poster-history")
def api_poster_history(
    library_id: Optional[str] = Query(default=None),
    template_id: Optional[str] = Query(default=None),
    action: Optional[str] = Query(default=None),
    limit: int = Query(default=500, ge=1, le=2000),
):
    """
    Return poster history records (local saves / Plex sends).
    Supports filtering by library, template, action, and limit.
    """
    records = db.get_poster_history(
        library_id=library_id,
        template_id=template_id,
        action=action,
        limit=limit,
    )
    return {"records": records}


@router.post("/poster-status")
def api_poster_status(payload: PosterStatusRequest):
    """Return latest sent/saved status per rating key (optionally filtered by library)."""
    status = db.get_poster_status(
        library_id=payload.library_id,
        rating_keys=payload.rating_keys,
    )
    return {"status": status}

