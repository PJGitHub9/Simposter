# backend/api/live_kometa.py
"""Live Kometa files (Overlay Manager → Advanced). See backend/live_kometa.py."""
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import database as db
from .. import live_kometa
from ..config import logger

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


_BROWSE_EXT = (".yml", ".yaml")
_BROWSE_LIMIT = 2000


def _browse_roots() -> list:
    """Starting points: drive letters on Windows, "/" elsewhere, plus common
    Kometa/UMTK and container folders that exist on this server."""
    import os
    import string
    from pathlib import Path
    from ..config import settings
    roots = []
    if os.name == "nt":
        roots += [f"{d}:\\" for d in string.ascii_uppercase if Path(f"{d}:\\").exists()]
    else:
        roots.append("/")
    for c in ("/config", "/kometa", "/umtk", "/tssk", "/data", "/mnt", str(Path.home())):
        try:
            if Path(c).is_dir() and c not in roots:
                roots.append(c)
        except OSError:
            continue
    try:
        cfg = str(Path(settings.CONFIG_DIR).resolve())
        if cfg not in roots:
            roots.append(cfg)
    except Exception:
        pass
    return roots


@router.get("/live-kometa-files/browse")
def api_browse_live_files(path: Optional[str] = None):
    """List the folders and .yml/.yaml files in a folder on the Simposter server,
    for the live-file picker. Without a path (or with one that's not a folder),
    starts at the given file's folder or returns only the starting points."""
    from pathlib import Path
    roots = _browse_roots()
    raw = (path or "").strip()
    if not raw:
        return {"path": None, "parent": None, "dirs": [], "files": [], "roots": roots}
    if live_kometa.is_network_path(raw):
        raise HTTPException(400, "Network paths aren't allowed; mount the share on the server and use its local path")
    p = Path(raw).expanduser()
    if p.suffix.lower() in _BROWSE_EXT and not p.is_dir():
        p = p.parent
    try:
        p = p.resolve()
        if not p.is_dir():
            raise HTTPException(404, f"Folder not found on the Simposter server: {raw}")
        dirs, files = [], []
        for i, entry in enumerate(sorted(p.iterdir(), key=lambda e: e.name.lower())):
            if i >= _BROWSE_LIMIT:
                break
            try:
                if entry.name.startswith("."):
                    continue
                if entry.is_dir():
                    dirs.append(entry.name)
                elif entry.suffix.lower() in _BROWSE_EXT and entry.is_file():
                    files.append({"name": entry.name, "size": entry.stat().st_size,
                                  "modified": entry.stat().st_mtime})
            except OSError:
                continue
    except PermissionError:
        raise HTTPException(403, f"Simposter can't read this folder: {raw}")
    except OSError as e:
        logger.debug("[LIVE KOMETA] Couldn't open %s: %s", raw, e)
        raise HTTPException(400, f"Couldn't open this folder: {raw}")
    parent = str(p.parent) if p.parent != p else None
    return {"path": str(p), "parent": parent, "dirs": dirs, "files": files, "roots": roots}
