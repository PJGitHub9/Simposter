"""
API endpoints for managing scheduled tasks like automatic library scans.
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional
from ..scheduler import (
    schedule_library_scan,
    cancel_library_scan,
    get_scan_schedule,
    get_scheduler
)
from ..config import logger
from .. import database as db
from .ui_settings import _read_settings

router = APIRouter()


class ScheduleRequest(BaseModel):
    cron_expression: str
    library_id: Optional[str] = None


@router.post("/scheduler/library-scan")
def api_schedule_library_scan(req: ScheduleRequest):
    """
    Schedule automatic library scans using a cron expression.

    Examples of cron expressions:
    - "0 2 * * *"     - Every day at 2:00 AM
    - "0 */6 * * *"   - Every 6 hours
    - "0 0 * * 0"     - Every Sunday at midnight
    - "30 3 * * 1-5"  - Weekdays at 3:30 AM
    """
    try:
        success = schedule_library_scan(req.cron_expression, req.library_id)
        if not success:
            raise HTTPException(status_code=400, detail="Failed to schedule library scan. Check cron expression format.")

        # Save to settings database
        settings = _read_settings()
        settings_dict = settings.model_dump(exclude_none=False)
        # Ensure empty string is converted to None/null, and convert to string if needed
        library_id = None
        if req.library_id:
            if isinstance(req.library_id, str) and req.library_id.strip():
                library_id = req.library_id.strip()
            elif isinstance(req.library_id, int):
                library_id = str(req.library_id)

        settings_dict["scheduler"] = {
            "enabled": True,
            "cronExpression": req.cron_expression,
            "libraryId": library_id
        }
        db.save_ui_settings(settings_dict)

        schedule_info = get_scan_schedule()
        return {
            "status": "scheduled",
            "cron_expression": req.cron_expression,
            "library_id": req.library_id,
            "schedule": schedule_info
        }
    except Exception as e:
        logger.error(f"[SCHEDULER API] Failed to schedule library scan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to schedule library scan: {e}")


@router.delete("/scheduler/library-scan")
def api_cancel_library_scan():
    """Cancel the scheduled library scan."""
    try:
        success = cancel_library_scan()

        # Save to settings database
        settings = _read_settings()
        settings_dict = settings.model_dump(exclude_none=False)
        settings_dict["scheduler"] = {
            "enabled": False,
            "cronExpression": settings_dict.get("scheduler", {}).get("cronExpression", "0 1 * * *"),
            "libraryId": settings_dict.get("scheduler", {}).get("libraryId", None)
        }
        db.save_ui_settings(settings_dict)

        if success:
            return {"status": "cancelled"}
        else:
            return {"status": "not_scheduled", "message": "No library scan was scheduled"}
    except Exception as e:
        logger.error(f"[SCHEDULER API] Failed to cancel library scan: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to cancel library scan: {e}")


@router.get("/scheduler/library-scan")
def api_get_library_scan_schedule():
    """Get information about the current library scan schedule."""
    try:
        schedule_info = get_scan_schedule()
        settings = _read_settings()
        settings_dict = settings.model_dump(exclude_none=False)
        scheduler_settings = settings_dict.get("scheduler", {
            "enabled": False,
            "cronExpression": "0 1 * * *",
            "libraryId": None
        })

        # Normalize libraryId - convert "None" string or empty string to null, convert int to string
        library_id = scheduler_settings.get("libraryId")
        if library_id in (None, "", "None", "null"):
            scheduler_settings["libraryId"] = None
        elif isinstance(library_id, int):
            scheduler_settings["libraryId"] = str(library_id)

        if schedule_info is None:
            return {
                "status": "not_scheduled",
                "settings": scheduler_settings
            }

        return {
            "status": "scheduled",
            "schedule": schedule_info,
            "settings": scheduler_settings
        }
    except Exception as e:
        logger.error(f"[SCHEDULER API] Failed to get library scan schedule: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get schedule: {e}")


@router.get("/scheduler/status")
def api_scheduler_status():
    """Check if the scheduler is running."""
    try:
        scheduler = get_scheduler()
        if scheduler is None:
            return {"status": "not_initialized"}

        return {
            "status": "running" if scheduler.running else "stopped",
            "jobs": len(scheduler.get_jobs())
        }
    except Exception as e:
        logger.error(f"[SCHEDULER API] Failed to get scheduler status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get scheduler status: {e}")
