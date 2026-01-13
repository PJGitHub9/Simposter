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
from typing import Optional, List

logger = logging.getLogger(__name__)

# Global scheduler instance
_scheduler: Optional[BackgroundScheduler] = None
_scan_job_id = "library_scan_job"
_integration_poll_job_id = "integration_poll_job"


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
            if scheduler_settings.get("enabled", False):
                # Support both legacy libraryId and new libraryIds
                library_ids = scheduler_settings.get("libraryIds", [])
                if not library_ids:
                    library_id = scheduler_settings.get("libraryId")
                    library_ids = [library_id] if library_id else []

                schedule_library_scan(
                    scheduler_settings.get("cronExpression", "0 1 * * *"),
                    library_ids
                )
                logger.info("[SCHEDULER] Restored library scan schedule from settings: %s", scheduler_settings.get("cronExpression"))

            # Integration polling removed
            # (Radarr/Sonarr/Tautulli integrations deprecated)

        except Exception as e:
            logger.error("[SCHEDULER] Failed to restore schedule from settings: %s", e)

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
    try:
        from .config import settings

        logger.info("[SCHEDULER] Starting scheduled library scan (library_ids=%s)", library_ids or "all")

        # Make internal API call to trigger scan
        # If library_ids is empty/None, scan all libraries
        if library_ids:
            # Scan each library individually
            for library_id in library_ids:
                url = f"http://localhost:{settings.PORT}/api/scan-library?library_id={library_id}"
                try:
                    response = requests.post(url, timeout=300)  # 5 minute timeout per library
                    if response.status_code == 200:
                        logger.info("[SCHEDULER] Library scan completed successfully for library_id=%s", library_id)
                    elif response.status_code == 409:
                        logger.warning("[SCHEDULER] Library scan already in progress for library_id=%s", library_id)
                    else:
                        logger.error("[SCHEDULER] Library scan failed for library_id=%s with status %s: %s",
                                    library_id, response.status_code, response.text)
                except Exception as e:
                    logger.error("[SCHEDULER] Failed to scan library_id=%s: %s", library_id, e)
        else:
            # Scan all libraries
            url = f"http://localhost:{settings.PORT}/api/scan-library"
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
    except requests.ConnectionError as e:
        logger.error("[SCHEDULER] Connection error during library scan (server may be down): %s", e)
    except requests.RequestException as e:
        logger.error("[SCHEDULER] Network error during library scan: %s", e)
    except Exception as e:
        logger.error("[SCHEDULER] Unexpected error during scheduled library scan: %s", e, exc_info=True)


def schedule_integration_polling(interval_minutes: int = 10):
    """
    Schedule integration polling to run at regular intervals.

    Args:
        interval_minutes: How often to poll (in minutes). Default is 10 minutes.
    """
    if _scheduler is None:
        logger.error("[SCHEDULER] Scheduler not initialized, call init_scheduler() first")
        return False

    try:
        # Remove existing job if present
        if _scheduler.get_job(_integration_poll_job_id):
            _scheduler.remove_job(_integration_poll_job_id)
            logger.info("[SCHEDULER] Removed existing integration polling job")

        # Create interval trigger
        trigger = IntervalTrigger(minutes=interval_minutes)

        # Add new job
        _scheduler.add_job(
            func=_run_integration_poll,
            trigger=trigger,
            id=_integration_poll_job_id,
            name="Integration Polling",
            replace_existing=True
        )

        logger.info(f"[SCHEDULER] Scheduled integration polling every {interval_minutes} minutes")

        # Log next run time
        next_run = _scheduler.get_job(_integration_poll_job_id).next_run_time
        logger.info("[SCHEDULER] Next integration poll scheduled for: %s", next_run)

        return True

    except Exception as e:
        logger.error("[SCHEDULER] Failed to schedule integration polling: %s", e)
        return False


def cancel_integration_polling():
    """Cancel the scheduled integration polling job."""
    if _scheduler is None:
        return False

    try:
        if _scheduler.get_job(_integration_poll_job_id):
            _scheduler.remove_job(_integration_poll_job_id)
            logger.info("[SCHEDULER] Cancelled integration polling job")
            return True
        return False
    except Exception as e:
        logger.error("[SCHEDULER] Failed to cancel integration polling: %s", e)
        return False


def get_integration_poll_schedule() -> Optional[dict]:
    """Get information about the current integration polling schedule."""
    if _scheduler is None:
        return None

    job = _scheduler.get_job(_integration_poll_job_id)
    if job is None:
        return None

    return {
        "job_id": job.id,
        "name": job.name,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger)
    }


def _run_integration_poll():
    """
    Internal function to execute integration polling.
    This is called by the scheduler.
    """
    try:
        from . import integrations_poller

        logger.info("[SCHEDULER] Starting scheduled integration poll")

        # Poll all integrations
        new_content = integrations_poller.poll_all_integrations()

        movies = new_content.get("movies", [])
        tv_shows = new_content.get("tv_shows", [])

        if not movies and not tv_shows:
            logger.info("[SCHEDULER] No new content detected")
            return

        logger.info(f"[SCHEDULER] Processing {len(movies)} new movies and {len(tv_shows)} new TV shows")

        # Process movies
        if movies:
            movie_results = integrations_poller.process_new_content(movies)
            logger.info(f"[SCHEDULER] Movie processing complete: {movie_results['success']} succeeded, {movie_results['failed']} failed")

        # Process TV shows
        if tv_shows:
            tv_results = integrations_poller.process_new_content(tv_shows)
            logger.info(f"[SCHEDULER] TV show processing complete: {tv_results['success']} succeeded, {tv_results['failed']} failed")

    except Exception as e:
        logger.error("[SCHEDULER] Unexpected error during integration poll: %s", e, exc_info=True)


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[SCHEDULER] Scheduler shut down")
