"""Poster mode endpoints: list, set by hand, and re-apply a group's rules."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import poster_mode
from ..config import logger

router = APIRouter()

MAX_SET_ITEMS = 2000


class PosterModeSetRequest(BaseModel):
    group_id: str
    media_type: str = "movie"
    items: List[Dict[str, Any]] = Field(default_factory=list)  # [{tmdb_id?, tvdb_id?}]
    mode: Optional[str] = None  # None clears the manual mode


class PosterModeReevaluateRequest(BaseModel):
    group_id: str


class PosterModeDismissRequest(BaseModel):
    group_id: str
    media_type: str = "movie"
    items: List[Dict[str, Any]] = Field(default_factory=list)  # [{tmdb_id?, tvdb_id?}]


def _media_type(value: str) -> str:
    if value not in ("movie", "tv"):
        raise HTTPException(status_code=400, detail="media_type must be 'movie' or 'tv'")
    return value


@router.get("/poster-modes")
def api_get_poster_modes(group_id: str, media_type: str = "movie"):
    media_type = _media_type(media_type)
    modes = poster_mode.modes_for_group(group_id, media_type)
    items = [{"id_type": k[0], "item_id": k[1], "mode": v["mode"], "reason": v["reason"], "manual": v["manual"],
              "warning": v["warning"]}
             for k, v in modes.items()]
    return {"items": items, "rules": poster_mode.rules_for(group_id)}


@router.post("/poster-modes/set")
def api_set_poster_modes(req: PosterModeSetRequest):
    media_type = _media_type(req.media_type)
    if req.mode is not None and req.mode not in poster_mode.MODES:
        raise HTTPException(status_code=400, detail=f"Invalid poster mode: {req.mode}")
    if len(req.items) > MAX_SET_ITEMS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_SET_ITEMS} items per request")
    try:
        updated = poster_mode.set_manual(req.group_id, media_type, req.items, req.mode)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    logger.info("[MODE] %s: %d title(s) set to %s by hand", req.group_id, updated, req.mode or "rule/default")
    return {"updated": updated}


@router.post("/poster-modes/dismiss-warning")
def api_dismiss_mode_warning(req: PosterModeDismissRequest):
    """Dismiss the "lost its rule" heads-up on these titles."""
    media_type = _media_type(req.media_type)
    if len(req.items) > MAX_SET_ITEMS:
        raise HTTPException(status_code=400, detail=f"At most {MAX_SET_ITEMS} items per request")
    keys = [k for k in (poster_mode.item_key(media_type, it.get("tmdb_id"), it.get("tvdb_id")) for it in req.items) if k]
    return {"cleared": poster_mode.clear_lost(req.group_id, media_type, keys)}


@router.post("/poster-modes/reevaluate")
def api_reevaluate_poster_modes(req: PosterModeReevaluateRequest):
    # An explicit re-check (Settings Save) always reads the linked Radarr/Sonarr again.
    return poster_mode.evaluate_group(req.group_id, tags_max_age=0)
