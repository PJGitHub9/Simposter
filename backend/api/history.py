from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from typing import Optional, List
from pydantic import BaseModel
from pathlib import Path
import os

from .. import database as db
from ..config import settings, logger

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


@router.get("/poster-history/{history_id}/preview")
def api_poster_history_preview(history_id: int):
    """
    Serve the saved poster file for a history record.
    Returns the poster image if it exists on disk.
    """
    # Get the history record
    records = db.get_poster_history(limit=1)
    # We need to fetch the specific record by ID
    record = db.get_poster_history_by_id(history_id)

    if not record:
        raise HTTPException(status_code=404, detail="History record not found")

    save_path = record.get("save_path")
    if not save_path:
        raise HTTPException(status_code=404, detail="No saved file for this record")

    # Convert path to Path object and resolve
    file_path = Path(save_path)

    # Security: Ensure the file is within allowed directories
    allowed_roots = [
        Path(settings.CONFIG_DIR).resolve(),
        Path(settings.OUTPUT_ROOT).resolve() if hasattr(settings, 'OUTPUT_ROOT') else None,
        Path(settings.SETTINGS_DIR).resolve(),
    ]
    allowed_roots = [r for r in allowed_roots if r is not None]

    try:
        resolved_path = file_path.resolve()
        is_allowed = any(
            str(resolved_path).startswith(str(root))
            for root in allowed_roots
        )
        if not is_allowed:
            logger.warning(f"[HISTORY] Attempted to access file outside allowed directories: {save_path}")
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception as e:
        logger.error(f"[HISTORY] Error resolving path {save_path}: {e}")
        raise HTTPException(status_code=400, detail="Invalid file path")

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    # Determine media type
    suffix = file_path.suffix.lower()
    media_type = "image/jpeg"
    if suffix == ".png":
        media_type = "image/png"
    elif suffix == ".webp":
        media_type = "image/webp"

    return FileResponse(
        path=str(file_path),
        media_type=media_type,
        filename=file_path.name
    )

