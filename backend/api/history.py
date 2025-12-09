from fastapi import APIRouter, Query
from typing import Optional

from .. import database as db

router = APIRouter()


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

