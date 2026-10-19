# backend/api/live_kometa.py
"""Live Kometa files (Overlay Manager → Advanced). See backend/live_kometa.py."""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import database as db
from .. import live_kometa

router = APIRouter()


class LiveKometaSaveRequest(BaseModel):
    id: Optional[str] = None
    path: str
    name: Optional[str] = ""
    library_type: str = "movie"
    interval_hours: float = 6
    enabled: bool = True
    refresh_posters: bool = True


def _with_next_run(item: dict) -> dict:
    from ..scheduler import get_live_kometa_next_run
    item = dict(item)
    item.pop("last_hash", None)
    item["next_run"] = get_live_kometa_next_run(item["id"]) if item.get("enabled") else None
    return item


@router.get("/live-kometa-files")
def api_list_live_files():
    return {"files": [_with_next_run(f) for f in db.get_live_kometa_files()]}


@router.post("/live-kometa-files")
def api_save_live_file(req: LiveKometaSaveRequest):
    try:
        path = live_kometa.validate_path(req.path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    hours = float(req.interval_hours or 0)
    if hours < 0.25 or hours > 24 * 7:
        raise HTTPException(400, "Check every 15 minutes to 7 days")
    file_id = req.id or uuid.uuid4().hex[:12]
    is_new = db.get_live_kometa_file(file_id) is None
    library_type = "show" if str(req.library_type).lower() in ("show", "tv") else "movie"
    db.save_live_kometa_file(file_id, str(path), (req.name or "").strip(), library_type, hours,
                             req.enabled, req.refresh_posters)
    from ..scheduler import schedule_live_kometa, cancel_live_kometa
    if req.enabled:
        schedule_live_kometa(file_id, hours)
    else:
        cancel_live_kometa(file_id)
    result = None
    if is_new:
        # Import it right away so the overlay exists to use.
        result = live_kometa.sync_file(file_id, force=True)
    return {"file": _with_next_run(db.get_live_kometa_file(file_id)), "sync": result}


@router.post("/live-kometa-files/{file_id}/sync")
def api_sync_live_file(file_id: str, force: bool = True):
    if not db.get_live_kometa_file(file_id):
        raise HTTPException(404, "Not found")
    result = live_kometa.sync_file(file_id, force=force)
    return {"file": _with_next_run(db.get_live_kometa_file(file_id)), "sync": result}


@router.delete("/live-kometa-files/{file_id}")
def api_delete_live_file(file_id: str):
    from ..scheduler import cancel_live_kometa
    cancel_live_kometa(file_id)
    if not db.delete_live_kometa_file(file_id):
        raise HTTPException(404, "Not found")
    return {"status": "ok"}
