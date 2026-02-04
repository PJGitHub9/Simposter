"""
Background task scheduler for periodic operations like library scans.
Uses APScheduler for cron-style scheduling.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
from typing import Optional, List

# Use the shared logger from config so scheduler logs appear in the main log
logger = logging.getLogger("simposter")

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

            # Restore library scan schedule
            scheduler_settings = settings_dict.get("scheduler", {})
            logger.info("[SCHEDULER] Scheduler settings: enabled=%s, cronExpression=%s",
                       scheduler_settings.get("enabled", False),
                       scheduler_settings.get("cronExpression", "not set"))

            if scheduler_settings.get("enabled", False):
                # Support both legacy libraryId and new libraryIds
                library_ids = scheduler_settings.get("libraryIds", [])
                if not library_ids:
                    library_id = scheduler_settings.get("libraryId")
                    library_ids = [library_id] if library_id else []

                cron_expr = scheduler_settings.get("cronExpression", "0 1 * * *")
                success = schedule_library_scan(cron_expr, library_ids)
                if success:
                    logger.info("[SCHEDULER] Restored library scan schedule: cron=%s, libraries=%s",
                               cron_expr, library_ids or "all")
                else:
                    logger.error("[SCHEDULER] Failed to restore library scan schedule")
            else:
                logger.info("[SCHEDULER] Scheduled scans are disabled in settings")

        except Exception as e:
            logger.error("[SCHEDULER] Failed to restore schedule from settings: %s", e, exc_info=True)

    return _scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Get the scheduler instance."""
    return _scheduler


def schedule_library_scan(cron_expression: str, library_ids: Optional[List[str]] = None):
    """
    Schedule a library scan using a cron expression.

    Args:
        cron_expression: Cron expression (e.g., "0 2 * * *" for 2 AM daily)
        library_ids: Optional list of library IDs to scan (None or empty = all libraries)

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

        # Validate cron field ranges
        def validate_cron_field(value: str, min_val: int, max_val: int, field_name: str) -> bool:
            """Validate a single cron field (handles *, ranges, steps, lists)"""
            if value == '*':
                return True

            # Handle ranges (e.g., 1-5)
            if '-' in value:
                try:
                    start, end = value.split('-')
                    return (min_val <= int(start) <= max_val and
                           min_val <= int(end) <= max_val)
                except (ValueError, AttributeError):
                    return False

            # Handle steps (e.g., */5)
            if '/' in value:
                base, step = value.split('/')
                if base != '*':
                    try:
                        if not (min_val <= int(base) <= max_val):
                            return False
                    except ValueError:
                        return False
                try:
                    return int(step) > 0
                except ValueError:
                    return False

            # Handle lists (e.g., 1,3,5)
            if ',' in value:
                try:
                    values = [int(v) for v in value.split(',')]
                    return all(min_val <= v <= max_val for v in values)
                except ValueError:
                    return False

            # Handle single value
            try:
                return min_val <= int(value) <= max_val
            except ValueError:
                return False

        # Validate each field
        if not validate_cron_field(minute, 0, 59, 'minute'):
            logger.error("[SCHEDULER] Invalid minute value: %s (must be 0-59)", minute)
            return False

        if not validate_cron_field(hour, 0, 23, 'hour'):
            logger.error("[SCHEDULER] Invalid hour value: %s (must be 0-23)", hour)
            return False

        if not validate_cron_field(day, 1, 31, 'day'):
            logger.error("[SCHEDULER] Invalid day value: %s (must be 1-31)", day)
            return False

        if not validate_cron_field(month, 1, 12, 'month'):
            logger.error("[SCHEDULER] Invalid month value: %s (must be 1-12)", month)
            return False

        if not validate_cron_field(day_of_week, 0, 6, 'day_of_week'):
            logger.error("[SCHEDULER] Invalid day_of_week value: %s (must be 0-6)", day_of_week)
            return False

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
            args=[library_ids],
            replace_existing=True
        )

        logger.info("[SCHEDULER] Scheduled library scan with cron: %s (library_ids=%s)",
                   cron_expression, library_ids or "all")

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


def _run_library_scan(library_ids: Optional[List[str]] = None):
    """
    Internal function to execute a library scan.
    This is called by the scheduler.
    """
    import time
    from fastapi import HTTPException
    scan_start = time.time()

    try:
        # Import the scan function directly - no HTTP request needed
        from .api.movies import api_scan_library

        logger.info("[SCHEDULER] ========== SCHEDULED SCAN TRIGGERED ==========")
        logger.info("[SCHEDULER] Starting scheduled library scan at %s (library_ids=%s)",
                   datetime.now().strftime("%Y-%m-%d %H:%M:%S"), library_ids or "all")

        # Call the scan function directly
        if library_ids:
            # Scan each library individually
            for library_id in library_ids:
                try:
                    result = api_scan_library(library_id=library_id)
                    logger.info("[SCHEDULER] Library scan completed for library_id=%s: %s movies, %s TV shows, %s collections",
                               library_id, result.get("movies_count", 0), result.get("tv_shows_count", 0), result.get("collections_count", 0))
                except HTTPException as e:
                    if e.status_code == 409:
                        logger.warning("[SCHEDULER] Library scan already in progress for library_id=%s", library_id)
                    else:
                        logger.error("[SCHEDULER] Library scan failed for library_id=%s: %s", library_id, e.detail)
                except Exception as e:
                    logger.error("[SCHEDULER] Failed to scan library_id=%s: %s", library_id, e)
        else:
            # Scan all libraries
            try:
                result = api_scan_library(library_id=None)
                elapsed = time.time() - scan_start
                logger.info("[SCHEDULER] Library scan completed in %.1f seconds: %s movies, %s TV shows, %s collections",
                           elapsed, result.get("movies_count", 0), result.get("tv_shows_count", 0), result.get("collections_count", 0))
            except HTTPException as e:
                if e.status_code == 409:
                    logger.warning("[SCHEDULER] Library scan already in progress")
                else:
                    logger.error("[SCHEDULER] Library scan failed: %s", e.detail)

        logger.info("[SCHEDULER] ========== SCHEDULED SCAN FINISHED ==========")

    except Exception as e:
        logger.error("[SCHEDULER] Unexpected error during scheduled library scan: %s", e, exc_info=True)


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[SCHEDULER] Scheduler shut down")
