# backend/api/poster_import.py
"""Tools -> Poster Import: apply Kometa-style `url_poster` YAML to a library
group once, or from a live file on disk (backend/custom_posters.py)."""
import threading
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import custom_posters as cp
from ..config import logger

router = APIRouter()

MAX_TEXT = 2_000_000


class _Library(BaseModel):
    server_id: str = "plex-1"
    library_id: str
    media_type: str = "movie"


class PreviewRequest(_Library):
    text: str = Field(..., max_length=MAX_TEXT)


class ApplyRequest(PreviewRequest):
    mode: str = "template"
    template_id: Optional[str] = "uniformlogo"
    preset_id: Optional[str] = None
    overrides: Dict[str, str] = Field(default_factory=dict)  # entry key -> mode | "skip"


class FileRequest(_Library):
    id: Optional[str] = None
    path: str
    name: Optional[str] = ""
    mode: str = "template"
    template_id: Optional[str] = "uniformlogo"
    preset_id: Optional[str] = None
    interval_hours: float = 6
    enabled: bool = True
    require_approval: bool = False


class RemoveRequest(BaseModel):
    media_type: str = "movie"
    item_key: str
    season_index: Optional[int] = None


def _check(media_type: str, mode: Optional[str] = None, preset_id: Optional[str] = None) -> None:
    if media_type not in ("movie", "tv"):
        raise HTTPException(400, "media_type must be movie or tv")
    if mode is not None:
        if mode not in cp.MODES:
            raise HTTPException(400, f"mode must be one of {', '.join(cp.MODES)}")
        if mode in ("template", "overlay") and not preset_id:
            raise HTTPException(400, "Pick a preset")


@router.post("/poster-import/preview")
def api_poster_import_preview(req: PreviewRequest):
    _check(req.media_type)
    try:
        return cp.preview(req.text, req.server_id, str(req.library_id), req.media_type)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/poster-import/apply")
def api_poster_import_apply(req: ApplyRequest):
    _check(req.media_type, req.mode, req.preset_id)
    for k, v in req.overrides.items():
        if v not in cp.MODES and v != "skip":
            raise HTTPException(400, f"Unknown choice for {k}: {v}")
    try:
        entries, _msgs = cp.parse(req.text)
    except ValueError as e:
        raise HTTPException(400, str(e))
    matched = cp.match(entries, req.server_id, str(req.library_id), req.media_type)
    started = cp.start_import(entries=matched, server_id=req.server_id, library_id=str(req.library_id),
                              media_type=req.media_type, mode=req.mode, template_id=req.template_id,
                              preset_id=req.preset_id, overrides=req.overrides, label="Import")
    if not started:
        raise HTTPException(409, "An import is already running")
    return {"started": True}


@router.get("/poster-import/status")
def api_poster_import_status():
    return cp.get_status()


@router.get("/poster-import/posters")
def api_poster_import_posters(server_id: str = "plex-1", library_id: str = "", media_type: str = "movie"):
    _check(media_type)
    return {"posters": cp.list_for_group(server_id, str(library_id), media_type)}


@router.get("/poster-import/image")
def api_poster_import_image(url: str):
    """The downloaded copy of an imported image (never fetched here)."""
    from fastapi.responses import FileResponse
    path = cp.cached_path(url)
    if path is None:
        raise HTTPException(404, "Not downloaded")
    media = {".png": "image/png", ".webp": "image/webp"}.get(path.suffix, "image/jpeg")
    return FileResponse(str(path), media_type=media, headers={"Cache-Control": "public, max-age=86400"})


@router.post("/poster-import/posters/remove")
def api_poster_import_remove(req: RemoveRequest):
    _check(req.media_type)
    return {"removed": cp.remove(req.media_type, req.item_key, req.season_index)}


# ---- live files ----

def _with_next_run(f: dict) -> dict:
    from ..scheduler import get_poster_import_next_run
    return {**f, "next_run": get_poster_import_next_run(f["id"]) if f.get("enabled") else None}


@router.get("/poster-import/files")
def api_poster_import_files(server_id: str = "plex-1", library_id: str = "", media_type: str = "movie"):
    _check(media_type)
    return {"files": [_with_next_run(f) for f in cp.get_files(server_id, str(library_id), media_type)]}


@router.post("/poster-import/files")
def api_poster_import_save_file(req: FileRequest):
    _check(req.media_type, req.mode, req.preset_id)
    from ..live_kometa import validate_source
    from ..scheduler import cancel_poster_import, schedule_poster_import
    try:
        path = validate_source(req.path)
    except ValueError as e:
        raise HTTPException(400, str(e))
    hours = max(0.25, min(float(req.interval_hours or 6), 168))
    saved = cp.save_file({**req.model_dump(), "path": str(path), "interval_hours": hours})
    if saved["enabled"]:
        schedule_poster_import(saved["id"], hours)
    else:
        cancel_poster_import(saved["id"])
    if saved["enabled"] and not req.id:
        # Apply it right away (in the background; it may take a while).
        threading.Thread(target=cp.sync_file, args=(saved["id"],), daemon=True, name="poster-import-file").start()
    return _with_next_run(saved)


@router.post("/poster-import/files/{file_id}/sync")
def api_poster_import_sync_file(file_id: str, force: bool = False, approve: bool = False):
    if not cp.get_file(file_id):
        raise HTTPException(404, "Not found")
    if cp.is_running():
        raise HTTPException(409, "An import is already running")
    from ..live_kometa import source_name
    f = cp.get_file(file_id)
    cp.mark_starting(f"Live file {f.get('name') or source_name(f['path'])}")
    threading.Thread(target=cp.sync_file, args=(file_id, force, approve), daemon=True, name="poster-import-file").start()
    return {"started": True}


@router.delete("/poster-import/files/{file_id}")
def api_poster_import_delete_file(file_id: str):
    from ..scheduler import cancel_poster_import
    cancel_poster_import(file_id)
    if not cp.delete_file(file_id):
        raise HTTPException(404, "Not found")
    logger.info("[POSTER_IMPORT] Removed live file %s (imported posters are kept)", file_id)
    return {"deleted": True}
