"""Overlay Refresh page API (Quirk #166). The logic lives in
backend/overlay_refresh.py; this is config, run/status and the log."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..config import logger, get_library_group_for
from .. import database as db
from .. import overlay_refresh as refresh

router = APIRouter(prefix="/overlay-refresh", tags=["overlay-refresh"])


def _require_group(group_id: str) -> dict:
    group = refresh.find_group(group_id)
    if not group:
        raise HTTPException(404, "Library group not found")
    return group


@router.get("/group")
def api_overlay_refresh_group(server_id: str = "plex-1", library_id: str = "", media_type: str = "movie"):
    """The library group this library belongs to, with its refresh config,
    how many posters are tracked, the next scheduled run and run status."""
    group = get_library_group_for(server_id, library_id, media_type) if library_id else None
    if not group:
        return {"group": None}
    from .. import scheduler as scheduler_module
    return {
        "group": group,
        "tracked": db.count_overlay_states(refresh.group_pairs(group)),
        "schedule": scheduler_module.get_overlay_refresh_schedule(group["id"]),
        "status": refresh.get_status(group["id"]),
    }


class RefreshConfigRequest(BaseModel):
    group_id: str
    config: Dict[str, Any]


@router.post("/config")
def api_overlay_refresh_config(req: RefreshConfigRequest):
    group = _require_group(req.group_id)
    current = dict(group.get("overlayRefresh") or {})
    cfg = {
        "enabled": bool(req.config.get("enabled")),
        "scheduleCron": (req.config.get("scheduleCron") or "").strip() or None,
        "plexLabel": str(req.config.get("plexLabel") if req.config.get("plexLabel") is not None else refresh.DEFAULT_LABEL).strip(),
        "lastRunAt": current.get("lastRunAt"),
        "lastRunStats": current.get("lastRunStats"),
    }
    from .. import scheduler as scheduler_module
    if cfg["enabled"] and cfg["scheduleCron"] and scheduler_module._build_cron_trigger(cfg["scheduleCron"]) is None:
        raise HTTPException(400, "Invalid schedule (expected a cron expression like '0 4 * * *')")
    updated = db.set_library_group_overlay_refresh(req.group_id, cfg)
    if updated is None:
        raise HTTPException(404, "Library group not found")
    try:
        if cfg["enabled"] and cfg["scheduleCron"]:
            scheduler_module.schedule_overlay_refresh(req.group_id, cfg["scheduleCron"])
        else:
            scheduler_module.cancel_overlay_refresh(req.group_id)
    except Exception as e:
        logger.warning("[OVERLAY_REFRESH] Could not update the schedule for %s: %s", req.group_id, e)
    return {"group": updated, "schedule": scheduler_module.get_overlay_refresh_schedule(req.group_id)}


class RefreshRunRequest(BaseModel):
    group_id: str
    apply: bool = False          # False = check only (nothing is uploaded)
    keys: Optional[List[str]] = None  # limit to these "server:rating_key:season" keys
    force: bool = False          # re-render even when nothing changed


@router.post("/run")
def api_overlay_refresh_run(req: RefreshRunRequest):
    _require_group(req.group_id)
    if not refresh.start_run(req.group_id, req.apply, req.keys, req.force):
        raise HTTPException(409, "A check or refresh is already running for this group")
    return {"status": "started"}


@router.get("/status")
def api_overlay_refresh_status(group_id: str):
    return refresh.get_status(group_id)


@router.get("/items")
def api_overlay_refresh_items(group_id: str):
    """Every tracked poster in the group with what its overlay last showed."""
    group = _require_group(group_id)
    states = db.get_overlay_states(refresh.group_pairs(group))
    from ..media_server import get_server_label
    names = {c["id"]: c.get("name") or c["id"] for c in db.get_all_overlay_configs()}
    out = []
    usage: dict = {}
    for s in states:
        overlays = []
        for cid in refresh.state_overlay_ids(s):
            overlays.append({"id": cid, "name": names.get(cid, cid), "missing": cid not in names})
            entry = usage.setdefault(cid, {"id": cid, "name": names.get(cid, cid), "missing": cid not in names, "count": 0})
            entry["count"] += 1
        out.append({
            "overlays": overlays,
            "key": refresh.state_key(s),
            "server_id": s["server_id"],
            "server": get_server_label(s["server_id"]),
            "rating_key": s["rating_key"],
            "season_index": s.get("season_index"),
            "title": s.get("title"),
            "year": s.get("year"),
            "preset_id": s.get("preset_id"),
            "overlay": [e.get("label") + (f" = {e['value']}" if e.get("value") else "") for e in (s.get("summary") or [])],
            "updated_at": s.get("updated_at"),
        })
    return {"items": out, "overlays": sorted(usage.values(), key=lambda o: (o["missing"], str(o["name"]).lower()))}


@router.get("/log")
def api_overlay_refresh_log(group_id: str, limit: int = 300):
    return {"entries": db.get_overlay_refresh_log(group_id, max(1, min(limit, 2000)))}
