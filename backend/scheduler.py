"""
Background task scheduler for periodic operations like library scans.
Uses APScheduler for cron-style scheduling.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from datetime import datetime, timezone
import requests
from typing import Optional

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None
_scan_job_id = "library_scan_job"


def init_scheduler(restore_from_settings: bool = True):
    """Initialize the background scheduler."""
    global _scheduler
    if _scheduler is not None:
        logger.warning("[SCHEDULER] Scheduler already initialized")
        return _scheduler

    _scheduler = BackgroundScheduler(daemon=True)
    _scheduler.start()
    logger.info("[SCHEDULER] Background scheduler started")

    # Restore schedule from settings if requested
    if restore_from_settings:
        try:
            from .api.ui_settings import _read_settings
            settings = _read_settings()
            settings_dict = settings.model_dump(exclude_none=False)
            scheduler_settings = settings_dict.get("scheduler", {})
            if scheduler_settings.get("enabled", False):
                schedule_library_scan(
                    scheduler_settings.get("cronExpression", "0 1 * * *"),
                    scheduler_settings.get("libraryId", None)
                )
                logger.info("[SCHEDULER] Restored schedule from settings: %s", scheduler_settings.get("cronExpression"))
        except Exception as e:
            logger.error("[SCHEDULER] Failed to restore schedule from settings: %s", e)

    return _scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Get the scheduler instance."""
    return _scheduler


def schedule_library_scan(cron_expression: str, library_id: Optional[str] = None):
    """
    Schedule a library scan using a cron expression.

    Args:
        cron_expression: Cron expression (e.g., "0 2 * * *" for 2 AM daily)
        library_id: Optional library ID to scan (None = all libraries)

    Cron format: minute hour day month day_of_week
    Examples:
        "0 2 * * *"     - Every day at 2:00 AM
        "0 */6 * * *"   - Every 6 hours
        "0 0 * * 0"     - Every Sunday at midnight
        "30 3 * * 1-5"  - Weekdays at 3:30 AM
    """
    if _scheduler is None:
        logger.error("[SCHEDULER] Scheduler not initialized, call init_scheduler() first")
        return False

    try:
        # Parse cron expression
        parts = cron_expression.strip().split()
        if len(parts) != 5:
            logger.error("[SCHEDULER] Invalid cron expression: %s (must be 5 fields)", cron_expression)
            return False

        minute, hour, day, month, day_of_week = parts

        # Create trigger using local timezone
        import tzlocal
        local_tz = tzlocal.get_localzone()

        trigger = CronTrigger(
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            timezone=local_tz
        )

        # Remove existing job if present
        if _scheduler.get_job(_scan_job_id):
            _scheduler.remove_job(_scan_job_id)
            logger.info("[SCHEDULER] Removed existing library scan job")

        # Add new job
        _scheduler.add_job(
            func=_run_library_scan,
            trigger=trigger,
            id=_scan_job_id,
            name="Library Scan",
            args=[library_id],
            replace_existing=True
        )

        logger.info("[SCHEDULER] Scheduled library scan with cron: %s (library_id=%s)",
                   cron_expression, library_id or "all")

        # Log next run time
        next_run = _scheduler.get_job(_scan_job_id).next_run_time
        logger.info("[SCHEDULER] Next scan scheduled for: %s", next_run)

        return True

    except Exception as e:
        logger.error("[SCHEDULER] Failed to schedule library scan: %s", e)
        return False


def cancel_library_scan():
    """Cancel the scheduled library scan job."""
    if _scheduler is None:
        return False

    try:
        if _scheduler.get_job(_scan_job_id):
            _scheduler.remove_job(_scan_job_id)
            logger.info("[SCHEDULER] Cancelled library scan job")
            return True
        return False
    except Exception as e:
        logger.error("[SCHEDULER] Failed to cancel library scan: %s", e)
        return False


def get_scan_schedule() -> Optional[dict]:
    """Get information about the current scan schedule."""
    if _scheduler is None:
        return None

    job = _scheduler.get_job(_scan_job_id)
    if job is None:
        return None

    return {
        "job_id": job.id,
        "name": job.name,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger)
    }


def _run_library_scan(library_id: Optional[str] = None):
    """
    Internal function to execute a library scan.
    This is called by the scheduler.
    """
    try:
        from .config import settings

        logger.info("[SCHEDULER] Starting scheduled library scan (library_id=%s)", library_id or "all")

        # Make internal API call to trigger scan
        url = f"http://localhost:{settings.PORT}/api/scan-library"
        if library_id:
            url += f"?library_id={library_id}"

        response = requests.post(url, timeout=300)  # 5 minute timeout

        if response.status_code == 200:
            logger.info("[SCHEDULER] Library scan completed successfully")
        elif response.status_code == 409:
            logger.warning("[SCHEDULER] Library scan already in progress")
        else:
            logger.error("[SCHEDULER] Library scan failed with status %s: %s",
                        response.status_code, response.text)

    except requests.Timeout:
        logger.error("[SCHEDULER] Library scan timed out after 5 minutes")
    except Exception as e:
        logger.error("[SCHEDULER] Failed to run scheduled library scan: %s", e)


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[SCHEDULER] Scheduler shut down")
