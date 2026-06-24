from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse
from typing import Optional, List
from pydantic import BaseModel
from pathlib import Path
import os

from .. import database as db
from ..config import settings, logger
from ..scheduler import schedule_poster_retry, cancel_poster_retry

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
    Priority: 1) saved thumbnail, 2) save_path file, 3) 404
    """
    record = db.get_poster_history_by_id(history_id)

    if not record:
        raise HTTPException(status_code=404, detail="History record not found")

    # First try thumbnail_path (historical snapshot)
    thumbnail_path = record.get("thumbnail_path")
    save_path = record.get("save_path")

    # Determine which file to serve (prefer thumbnail)
    file_to_serve = None
    if thumbnail_path:
        thumb = Path(thumbnail_path)
        if thumb.exists():
            file_to_serve = thumb
    if not file_to_serve and save_path:
        saved = Path(save_path)
        if saved.exists():
            file_to_serve = saved

    if not file_to_serve:
        raise HTTPException(status_code=404, detail="No saved file for this record")

    # Security: Ensure the file is within allowed directories
    allowed_roots = [
        Path(settings.CONFIG_DIR).resolve(),
        Path(settings.OUTPUT_ROOT).resolve() if hasattr(settings, 'OUTPUT_ROOT') else None,
        Path(settings.SETTINGS_DIR).resolve(),
    ]
    allowed_roots = [r for r in allowed_roots if r is not None]

    try:
        resolved_path = file_to_serve.resolve()
        is_allowed = any(
            str(resolved_path).startswith(str(root))
            for root in allowed_roots
        )
        if not is_allowed:
            logger.warning(f"[HISTORY] Attempted to access file outside allowed directories: {file_to_serve}")
            raise HTTPException(status_code=403, detail="Access denied")
    except Exception as e:
        logger.error(f"[HISTORY] Error resolving path {file_to_serve}: {e}")
        raise HTTPException(status_code=400, detail="Invalid file path")

    # Determine media type
    suffix = file_to_serve.suffix.lower()
    media_type = "image/jpeg"
    if suffix == ".png":
        media_type = "image/png"
    elif suffix == ".webp":
        media_type = "image/webp"

    return FileResponse(
        path=str(file_to_serve),
        media_type=media_type,
        filename=file_to_serve.name
    )


# ============================================================================
# Poster Retry Queue endpoints
# ============================================================================

@router.get("/retry-queue")
def api_get_retry_queue(include_resolved: bool = Query(default=False)):
    """Return the poster retry queue for UI display."""
    items = db.get_retry_queue(include_resolved=include_resolved)
    count = db.get_retry_queue_count()
    return {"items": items, "pending_count": count}


@router.get("/retry-queue/count")
def api_get_retry_queue_count():
    """Return just the pending retry count (for badge indicators)."""
    return {"pending_count": db.get_retry_queue_count()}


@router.delete("/retry-queue/{rating_key}")
def api_remove_retry_item(rating_key: str):
    """Manually remove an item from the retry queue (dismiss)."""
    db.remove_from_retry_queue(rating_key)
    return {"status": "ok"}


@router.post("/retry-queue/{rating_key}/retry-now")
def api_retry_now(rating_key: str):
    """Immediately retry a single queued item."""
    from ..api.batch import process_single_movie_poster, process_single_tv_show_poster
    from ..scheduler import _run_poster_retry

    items = db.get_retry_queue()
    item = next((i for i in items if i["rating_key"] == rating_key), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found in retry queue")

    ui = db.get_ui_settings() or {}
    send_logos = bool(ui.get("plex", {}).get("sendLogosToPlex", False))
    media_type = item.get("media_type", "movie")

    db.update_retry_attempt(rating_key)
    try:
        if media_type == "tv":
            result = process_single_tv_show_poster(
                rating_key=rating_key,
                template_id=item["template_id"],
                preset_id=item["preset_id"],
                send_to_plex=True,
                library_id=item.get("library_id", ""),
                labels=[],
                include_seasons=True,
                source="auto_generate",
                send_logos_to_plex=send_logos,
            )
            sub_results = result.get("results", []) if isinstance(result, dict) else []
            still_needs_retry = any(r.get("needs_retry") for r in sub_results)
        else:
            result = process_single_movie_poster(
                rating_key=rating_key,
                template_id=item["template_id"],
                preset_id=item["preset_id"],
                send_to_plex=True,
                library_id=item.get("library_id", ""),
                labels=[],
                source="auto_generate",
                send_logos_to_plex=send_logos,
            )
            still_needs_retry = result.get("needs_retry", True) if isinstance(result, dict) else True

        if not still_needs_retry:
            db.resolve_retry_queue_item(rating_key, "resolved")

        return {"status": "ok", "resolved": not still_needs_retry}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry-queue/apply-settings")
def api_apply_retry_settings(enabled: bool = Query(...), interval_hours: float = Query(default=24.0)):
    """Apply retry scheduler settings (called when user saves settings)."""
    if enabled:
        schedule_poster_retry(interval_hours)
    else:
        cancel_poster_retry()
    return {"status": "ok"}

