"""Manual editor support for Overlay only titles: preview and send the preset's
overlays drawn on the server's current poster (no TMDb art, logo or text)."""
import base64
import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from .. import overlay_only

logger = logging.getLogger("simposter")
router = APIRouter()


class OverlayOnlyTarget(BaseModel):
    server_id: str = "plex-1"
    rating_key: str


class OverlayOnlyRequest(BaseModel):
    server_id: str = "plex-1"
    rating_key: str
    is_tv: bool = False
    library_id: Optional[str] = None
    template_id: str = "uniformlogo"
    preset_id: Optional[str] = None
    # None = use the preset's own lists (series or season)
    overlay_config_ids: Optional[List[str]] = None
    overlay_config_ids_below: List[str] = Field(default_factory=list)
    # TV: the season's number when rating_key is a season (0 = Specials)
    season_index: Optional[int] = None
    # preview only: download the server's poster again instead of the copy
    # kept from the last few minutes
    refresh_base: bool = False
    # send only: every server copy to upload to (defaults to the one above)
    targets: Optional[List[OverlayOnlyTarget]] = None


def _lists(req: OverlayOnlyRequest) -> Optional[dict]:
    if req.overlay_config_ids is None:
        return None
    return {"ids": req.overlay_config_ids, "below": req.overlay_config_ids_below}


@router.post("/overlay-only/preview")
async def api_overlay_only_preview(req: OverlayOnlyRequest):
    """The overlays drawn on the item's current poster, as a JPEG. Nothing is sent."""
    if req.overlay_config_ids is not None and not req.overlay_config_ids:
        return {"status": "skipped", "reason": "No overlays are ticked."}
    result = await run_in_threadpool(
        overlay_only.apply_for_item, req.server_id, req.rating_key, req.library_id, req.is_tv,
        req.template_id, req.preset_id, "manual", req.season_index, _lists(req), False,
        preview=True, refresh_base=req.refresh_base,
    )
    if result.get("status") != "ok":
        return {"status": result.get("status", "error"), "reason": result.get("reason") or ""}
    data = result["image_bytes"]
    mime = result.get("content_type") or "image/jpeg"
    return {"status": "ok", "base": result.get("base"),
            "image_data": f"data:{mime};base64,{base64.b64encode(data).decode()}"}


@router.post("/overlay-only/send")
async def api_overlay_only_send(req: OverlayOnlyRequest):
    """Draw the overlays on each target's current poster and upload it."""
    if req.overlay_config_ids is not None and not req.overlay_config_ids:
        raise HTTPException(status_code=400, detail="No overlays are ticked.")
    targets = req.targets or [OverlayOnlyTarget(server_id=req.server_id, rating_key=req.rating_key)]
    results = []
    for t in targets:
        r = await run_in_threadpool(
            overlay_only.apply_for_item, t.server_id, t.rating_key,
            req.library_id if t.rating_key == req.rating_key else None, req.is_tv,
            req.template_id, req.preset_id, "manual", req.season_index, _lists(req), True,
        )
        results.append({"server_id": t.server_id, "rating_key": t.rating_key,
                        "status": r.get("status"), "reason": r.get("reason") or ""})
    ok = sum(1 for r in results if r["status"] == "ok")
    return {"sent": ok, "total": len(results), "results": results}
