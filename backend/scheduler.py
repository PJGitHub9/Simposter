"""
Background task scheduler for periodic operations like library scans.
Uses APScheduler for cron-style scheduling.
"""
import logging
import time
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

            # Restore scheduled cleanup job if enabled
            if scheduler_settings.get("cleanupEnabled", False):
                cleanup_cron = scheduler_settings.get("cleanupCronExpression", "0 3 * * 0")
                cleanup_categories = scheduler_settings.get("cleanupCategories") or [
                    "poster_cache", "logo_cache", "backdrop_cache", "square_art_cache",
                    "overlay_effect_cache", "uploaded_files", "overlay_assets", "poster_history",
                ]
                cleanup_history_days = int(scheduler_settings.get("cleanupHistoryDays", 180))
                if schedule_cleanup(cleanup_cron, cleanup_categories, cleanup_history_days):
                    logger.info("[SCHEDULER] Restored cleanup schedule: cron=%s, categories=%s", cleanup_cron, cleanup_categories)
                else:
                    logger.error("[SCHEDULER] Failed to restore cleanup schedule")
            else:
                logger.info("[SCHEDULER] Scheduled cleanup is disabled in settings")

            # Restore poster retry job if enabled
            automation = settings_dict.get("automation", {})
            if automation.get("retryUntilTemplateMet", False):
                interval_hours = float(automation.get("retryIntervalHours", 24))
                schedule_poster_retry(interval_hours)
            else:
                logger.info("[SCHEDULER] Poster retry is disabled in settings")

            # Restore every Library Group's own scheduled media mirror job
            # (Quirk #123's scheduler follow-up) -- genuinely per-group, not
            # a single global on/off the way scan/cleanup/retry are above,
            # since MediaMirrorConfig.scheduleEnabled/scheduleCron live on
            # each group's own `mirror` config.
            library_groups = settings_dict.get("libraryGroups") or []
            restored_mirror_count = 0
            for group in library_groups:
                mirror = (group or {}).get("mirror") or {}
                if not mirror.get("enabled") or not mirror.get("scheduleEnabled"):
                    continue
                cron_expr = mirror.get("scheduleCron")
                members = group.get("members") or []
                if not cron_expr or not members:
                    continue
                # Any one real member identifies this group server-side
                # (get_library_group_for() matches on ANY member, not
                # specifically the first) -- the job itself always runs the
                # group's OWN saved source/targets, not this particular pair.
                first_member = members[0]
                if schedule_media_mirror(first_member.get("serverId"), first_member.get("libraryId"), group.get("mediaType"), cron_expr):
                    restored_mirror_count += 1
            if restored_mirror_count:
                logger.info("[SCHEDULER] Restored %d scheduled media mirror job(s)", restored_mirror_count)

        except Exception as e:
            logger.error("[SCHEDULER] Failed to restore schedule from settings: %s", e, exc_info=True)

    return _scheduler


def get_scheduler() -> Optional[BackgroundScheduler]:
    """Get the scheduler instance."""
    return _scheduler


def _build_cron_trigger(cron_expression: str) -> Optional[CronTrigger]:
    """Parses and validates a 5-field cron expression, returning a CronTrigger
    (local timezone) or None if invalid -- logs the specific problem itself, so
    every caller can just check for None. Shared by schedule_library_scan() and
    schedule_cleanup() so the same validation rules apply to both schedulable
    jobs in this app rather than drifting between two copies.

    Cron format: minute hour day month day_of_week
    Examples:
        "0 2 * * *"     - Every day at 2:00 AM
        "0 */6 * * *"   - Every 6 hours
        "0 0 * * 0"     - Every Sunday at midnight
        "30 3 * * 1-5"  - Weekdays at 3:30 AM
    """
    parts = cron_expression.strip().split()
    if len(parts) != 5:
        logger.error("[SCHEDULER] Invalid cron expression: %s (must be 5 fields)", cron_expression)
        return None

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
        return None

    if not validate_cron_field(hour, 0, 23, 'hour'):
        logger.error("[SCHEDULER] Invalid hour value: %s (must be 0-23)", hour)
        return None

    if not validate_cron_field(day, 1, 31, 'day'):
        logger.error("[SCHEDULER] Invalid day value: %s (must be 1-31)", day)
        return None

    if not validate_cron_field(month, 1, 12, 'month'):
        logger.error("[SCHEDULER] Invalid month value: %s (must be 1-12)", month)
        return None

    if not validate_cron_field(day_of_week, 0, 6, 'day_of_week'):
        logger.error("[SCHEDULER] Invalid day_of_week value: %s (must be 0-6)", day_of_week)
        return None

    # Create trigger using local timezone
    import tzlocal
    local_tz = tzlocal.get_localzone()

    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone=local_tz
    )


def schedule_library_scan(cron_expression: str, library_ids: Optional[List[str]] = None):
    """
    Schedule a library scan using a cron expression.

    Args:
        cron_expression: Cron expression (e.g., "0 2 * * *" for 2 AM daily)
        library_ids: Optional list of library IDs to scan (None or empty = all libraries)
    """
    if _scheduler is None:
        logger.error("[SCHEDULER] Scheduler not initialized, call init_scheduler() first")
        return False

    try:
        trigger = _build_cron_trigger(cron_expression)
        if trigger is None:
            return False

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


_cleanup_job_id = "cleanup_job"


def schedule_cleanup(cron_expression: str, categories: List[str], history_days: int = 180):
    """Schedule the Simposter cache cleanup tool (backend/api/cleanup.py) using a
    cron expression -- mirrors schedule_library_scan() above, including using the
    same _build_cron_trigger() validation. Runs scan-then-clean for `categories`
    on the given schedule; never empties the cleanup trash automatically (see
    _run_cleanup() below)."""
    if _scheduler is None:
        logger.error("[SCHEDULER] Scheduler not initialized, call init_scheduler() first")
        return False

    try:
        trigger = _build_cron_trigger(cron_expression)
        if trigger is None:
            return False

        if _scheduler.get_job(_cleanup_job_id):
            _scheduler.remove_job(_cleanup_job_id)
            logger.info("[SCHEDULER] Removed existing cleanup job")

        _scheduler.add_job(
            func=_run_cleanup,
            trigger=trigger,
            id=_cleanup_job_id,
            name="Cleanup",
            args=[categories, history_days],
            replace_existing=True
        )

        logger.info("[SCHEDULER] Scheduled cleanup with cron: %s (categories=%s)", cron_expression, categories)
        next_run = _scheduler.get_job(_cleanup_job_id).next_run_time
        logger.info("[SCHEDULER] Next cleanup scheduled for: %s", next_run)
        return True

    except Exception as e:
        logger.error("[SCHEDULER] Failed to schedule cleanup: %s", e)
        return False


def cancel_cleanup():
    """Cancel the scheduled cleanup job."""
    if _scheduler is None:
        return False

    try:
        if _scheduler.get_job(_cleanup_job_id):
            _scheduler.remove_job(_cleanup_job_id)
            logger.info("[SCHEDULER] Cancelled cleanup job")
            return True
        return False
    except Exception as e:
        logger.error("[SCHEDULER] Failed to cancel cleanup: %s", e)
        return False


def get_cleanup_schedule() -> Optional[dict]:
    """Get information about the current cleanup schedule."""
    if _scheduler is None:
        return None

    job = _scheduler.get_job(_cleanup_job_id)
    if job is None:
        return None

    return {
        "job_id": job.id,
        "name": job.name,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger)
    }


def _media_mirror_job_id(server_id: str, library_id: str, media_type: str) -> str:
    return f"media_mirror_{server_id}_{library_id}_{media_type}"


def schedule_media_mirror(server_id: str, library_id: str, media_type: str, cron_expression: str) -> bool:
    """Schedules a recurring Media Mirror sync for one Library Group (Quirk
    #123's scheduler follow-up). Unlike scan/cleanup/retry above (one single
    global job each), this is genuinely per-group -- MediaMirrorConfig's
    scheduleEnabled/scheduleCron live on the owning group's own `mirror`
    config, not a global setting, so each group that opts in gets its own
    independent APScheduler job, keyed by (server_id, library_id, media_type)
    the same way mirror_status/_status_key() already are in api/media_mirror.py.
    Runs a full sync every time it fires -- true incremental change-detection
    (only re-copying items whose source image actually changed since the last
    run) is still deliberately deferred, per Quirk #123's own original scope
    note: it needs a verified per-item "has this changed" signal (Plex's
    thumb/art path version suffix, Jellyfin's ImageTags hash) that hasn't
    been checked against a real server yet. A full sync on a schedule is
    always correct, just not bandwidth-optimal for a large library re-run
    often -- a real, useful default, not a placeholder."""
    if _scheduler is None:
        logger.error("[SCHEDULER] Scheduler not initialized, call init_scheduler() first")
        return False
    try:
        trigger = _build_cron_trigger(cron_expression)
        if trigger is None:
            return False

        job_id = _media_mirror_job_id(server_id, library_id, media_type)
        if _scheduler.get_job(job_id):
            _scheduler.remove_job(job_id)
            logger.info("[SCHEDULER] Removed existing media mirror job for %s/%s/%s", server_id, library_id, media_type)

        _scheduler.add_job(
            func=_run_scheduled_media_mirror,
            trigger=trigger,
            id=job_id,
            name=f"Media Mirror ({server_id}/{library_id}/{media_type})",
            args=[server_id, library_id, media_type],
            replace_existing=True,
        )

        logger.info("[SCHEDULER] Scheduled media mirror for %s/%s/%s with cron: %s", server_id, library_id, media_type, cron_expression)
        next_run = _scheduler.get_job(job_id).next_run_time
        logger.info("[SCHEDULER] Next media mirror run for %s/%s/%s: %s", server_id, library_id, media_type, next_run)
        return True

    except Exception as e:
        logger.error("[SCHEDULER] Failed to schedule media mirror for %s/%s/%s: %s", server_id, library_id, media_type, e)
        return False


def cancel_media_mirror(server_id: str, library_id: str, media_type: str) -> bool:
    """Cancel one group's scheduled media mirror job, if any."""
    if _scheduler is None:
        return False
    try:
        job_id = _media_mirror_job_id(server_id, library_id, media_type)
        if _scheduler.get_job(job_id):
            _scheduler.remove_job(job_id)
            logger.info("[SCHEDULER] Cancelled media mirror job for %s/%s/%s", server_id, library_id, media_type)
            return True
        return False
    except Exception as e:
        logger.error("[SCHEDULER] Failed to cancel media mirror for %s/%s/%s: %s", server_id, library_id, media_type, e)
        return False


def get_media_mirror_schedule(server_id: str, library_id: str, media_type: str) -> Optional[dict]:
    """Get information about one group's current media mirror schedule."""
    if _scheduler is None:
        return None
    job = _scheduler.get_job(_media_mirror_job_id(server_id, library_id, media_type))
    if job is None:
        return None
    return {
        "job_id": job.id,
        "name": job.name,
        "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
        "trigger": str(job.trigger),
    }


def _run_scheduled_media_mirror(server_id: str, library_id: str, media_type: str):
    """Internal function the scheduler calls for one group's scheduled mirror
    run. A failure here is logged and swallowed, not raised -- matching
    _run_cleanup()/_run_library_scan() below, a bad run must never crash the
    scheduler thread or take down any other scheduled job (including another
    group's own mirror schedule)."""
    try:
        from .api.media_mirror import _run_mirror

        logger.info("[SCHEDULER] ========== SCHEDULED MEDIA MIRROR TRIGGERED (%s/%s/%s) ==========", server_id, library_id, media_type)
        _run_mirror(server_id, library_id, media_type, scheduled=True)
        logger.info("[SCHEDULER] ========== SCHEDULED MEDIA MIRROR FINISHED (%s/%s/%s) ==========", server_id, library_id, media_type)
    except Exception as e:
        logger.error("[SCHEDULER] Scheduled media mirror failed for %s/%s/%s: %s", server_id, library_id, media_type, e, exc_info=True)


def _run_cleanup(categories: List[str], history_days: int = 180):
    """Internal function the scheduler calls -- scans, then moves every matched
    candidate in `categories` to the cleanup trash (never permanently deletes;
    see backend/api/cleanup.py's module docstring on why nothing here skips the
    reversible trash step just because it's unattended). A failure here is
    logged and swallowed, not raised -- a bad run must never crash the
    scheduler thread or take down any other scheduled job."""
    try:
        from .api import cleanup as cleanup_api

        logger.info("[SCHEDULER] ========== SCHEDULED CLEANUP TRIGGERED ==========")
        scan = cleanup_api.api_cleanup_scan(history_days=history_days)
        logger.info("[SCHEDULER] Cleanup scan found %s across %d categories", scan.get("total_bytes_human"), len(scan.get("categories", [])))

        result = cleanup_api.api_cleanup_clean(cleanup_api.CleanRequest(categories=categories, history_days=history_days))
        logger.info("[SCHEDULER] Cleanup moved %d file(s) and removed %d row(s) to trash (batch %s)",
                    result.get("moved_files", 0), result.get("deleted_rows", 0), result.get("batch_id"))
        logger.info("[SCHEDULER] ========== SCHEDULED CLEANUP FINISHED ==========")
    except Exception as e:
        logger.error("[SCHEDULER] Scheduled cleanup failed: %s", e, exc_info=True)


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

        # force_poster_refresh=False (changed from True) -- a routine scheduled
        # scan's job is catching new/removed content, not re-verifying every
        # unchanged item's art against Plex every single run. Forcing a full
        # re-download+re-encode of every poster/logo/backdrop/square_art on
        # every scheduled run (often nightly) was real, repeated, avoidable
        # CPU/network cost for a library that rarely changes wholesale between
        # runs. A genuine "re-sync everything" need is covered by the manual
        # "Force Refresh All Art" action (Settings -> Libraries) instead.
        from .config import settings as _cfg
        from . import database as _db
        plex_configured = bool(_cfg.PLEX_URL and _cfg.PLEX_TOKEN)

        # What to scan. Entries are either "group:<id>" (a Library Group --
        # every server in it; what Settings -> Libraries saves now) or a bare
        # Plex library id (selections saved before groups were selectable,
        # still honored). Empty = everything on every server.
        groups = (_db.get_ui_settings() or {}).get("libraryGroups") or []
        selected_group_ids = {str(x)[6:] for x in (library_ids or []) if str(x).startswith("group:")}
        legacy_plex_ids = [x for x in (library_ids or []) if not str(x).startswith("group:")]
        if selected_group_ids:
            scope_groups = [g for g in groups if g.get("id") in selected_group_ids]
            plex_scope = [m.get("libraryId") for g in scope_groups for m in g.get("members") or []
                          if m.get("serverId") == "plex-1" and m.get("libraryId")]
            scan_all_plex = False
        else:
            scope_groups = groups
            plex_scope = legacy_plex_ids
            scan_all_plex = not legacy_plex_ids

        # 1. Plex. A Plex scan also scans the Jellyfin/Emby libraries linked to
        #    each scanned Plex library (api_scan_library() calls
        #    scan_all_linked_plex_libraries() itself), so those aren't scanned
        #    again below. Skipped silently when Plex isn't configured.
        if plex_configured and (scan_all_plex or plex_scope):
            for library_id in ([None] if scan_all_plex else plex_scope):
                try:
                    result = api_scan_library(library_id=library_id, force_poster_refresh=False)
                    logger.info("[SCHEDULER] Plex scan completed for %s in %.1fs: %s movies, %s TV shows, %s collections",
                                library_id or "all libraries", time.time() - scan_start,
                                result.get("movies_count", 0), result.get("tv_shows_count", 0), result.get("collections_count", 0))
                except HTTPException as e:
                    if e.status_code == 409:
                        logger.warning("[SCHEDULER] Plex scan already in progress (%s)", library_id or "all libraries")
                    else:
                        logger.error("[SCHEDULER] Plex scan failed for %s: %s", library_id or "all libraries", e.detail)
                except Exception as e:
                    logger.error("[SCHEDULER] Plex scan failed for %s: %s", library_id or "all libraries", e)

        # 2. Jellyfin/Emby libraries the Plex scan above didn't already cover:
        #    groups with no Plex library, or every group when Plex isn't
        #    configured. With a legacy Plex-only selection, all such groups are
        #    still scanned, matching the old behavior.
        try:
            _scan_standalone_nonplex_groups(scope_groups, plex_configured)
        except Exception as e:
            logger.error("[SCHEDULER] Failed to scan Jellyfin/Emby libraries: %s", e, exc_info=True)

        logger.info("[SCHEDULER] ========== SCHEDULED SCAN FINISHED ==========")

    except Exception as e:
        logger.error("[SCHEDULER] Unexpected error during scheduled library scan: %s", e, exc_info=True)


def _scan_standalone_nonplex_groups(groups: Optional[list] = None, plex_configured: bool = True) -> None:
    """Scans the Jellyfin/Emby libraries of `groups` (default: every Library
    Group) that a Plex scan doesn't already cover: groups with no Plex member,
    or every group's Jellyfin/Emby members when Plex isn't configured at all.
    (A Plex scan scans the Jellyfin/Emby libraries linked to each Plex library
    itself, via scan_all_linked_plex_libraries().) Reuses the same scoped
    per-library scan each group's own "Scan" button makes."""
    from . import database as db
    from .api.media_server import api_scan_media_server

    if groups is None:
        groups = (db.get_ui_settings() or {}).get("libraryGroups") or []
    standalone_members = []
    for group in groups:
        members = group.get("members") or []
        if not members:
            continue
        if plex_configured and any(m.get("serverId") == "plex-1" for m in members):
            continue
        media_type = "movie" if group.get("mediaType") == "movie" else "tv"
        for member in members:
            server_id = member.get("serverId")
            library_id = member.get("libraryId")
            if server_id and library_id and server_id != "plex-1":
                standalone_members.append((server_id, library_id, media_type))

    if not standalone_members:
        return

    import time
    from fastapi import HTTPException
    from .api.movies import scan_status

    def _wait_for_other_scan(max_wait_seconds: int = 1800) -> bool:
        """A manual scan (Settings → Scan) can be running when the scheduled
        job reaches this step -- api_scan_media_server() then refuses with a
        409. Wait for it to finish instead of logging a failure and silently
        skipping this library until the next scheduled run."""
        waited = 0
        while scan_status.get("state") == "running" and waited < max_wait_seconds:
            time.sleep(10)
            waited += 10
        return scan_status.get("state") != "running"

    logger.info("[SCHEDULER] Scanning %d standalone Jellyfin/Emby library group member(s) with no Plex counterpart", len(standalone_members))
    for server_id, library_id, media_type in standalone_members:
        for attempt in (1, 2):
            try:
                result = api_scan_media_server(server_id=server_id, library_id=library_id, media_type=media_type)
                logger.info("[SCHEDULER] Standalone scan for %s library %s: %d item(s)", server_id, library_id,
                            result.get("total_movies_found", 0) + result.get("total_shows_found", 0))
                break
            except HTTPException as e:
                if e.status_code == 409 and attempt == 1 and _wait_for_other_scan():
                    continue  # the other scan finished -- try this library again
                if e.status_code == 409:
                    logger.info("[SCHEDULER] Skipped %s library %s -- another scan was still running after waiting; it'll be picked up next run",
                                server_id, library_id)
                else:
                    logger.error("[SCHEDULER] Standalone scan failed for %s library %s: %s", server_id, library_id, e.detail)
                break
            except Exception as e:
                logger.error("[SCHEDULER] Standalone scan failed for %s library %s: %s", server_id, library_id, e)
                break


_retry_job_id = "poster_retry_job"


def schedule_poster_retry(interval_hours: float):
    """Schedule the poster retry job to run every interval_hours hours."""
    if _scheduler is None:
        logger.error("[SCHEDULER] Scheduler not initialized")
        return False
    try:
        if _scheduler.get_job(_retry_job_id):
            _scheduler.remove_job(_retry_job_id)

        from apscheduler.triggers.interval import IntervalTrigger
        _scheduler.add_job(
            func=_run_poster_retry,
            trigger=IntervalTrigger(hours=interval_hours),
            id=_retry_job_id,
            name="Poster Retry",
            replace_existing=True,
        )
        logger.info("[SCHEDULER] Scheduled poster retry every %.1f hours", interval_hours)
        return True
    except Exception as e:
        logger.error("[SCHEDULER] Failed to schedule poster retry: %s", e)
        return False


def cancel_poster_retry():
    """Cancel the poster retry job."""
    if _scheduler is None:
        return False
    try:
        if _scheduler.get_job(_retry_job_id):
            _scheduler.remove_job(_retry_job_id)
            logger.info("[SCHEDULER] Cancelled poster retry job")
            return True
        return False
    except Exception as e:
        logger.error("[SCHEDULER] Failed to cancel poster retry: %s", e)
        return False


def _plex_item_exists(rating_key: str) -> Optional[bool]:
    """Check whether a rating_key still exists in Plex at all.

    Returns True/False on a definitive answer, or None if the check itself
    failed (network blip, timeout, etc.) — callers must treat None as "unknown,
    don't act on it" rather than "gone", so a transient error never gets
    mistaken for a deleted item.
    """
    try:
        from .config import settings, plex_headers, plex_session
        r = plex_session.get(
            f"{settings.PLEX_URL}/library/metadata/{rating_key}",
            headers=plex_headers(),
            timeout=6,
        )
        if r.status_code == 404:
            return False
        if r.status_code == 200:
            return True
        return None
    except Exception:
        return None


def _run_poster_retry():
    """Retry pending items from the poster retry queue."""
    try:
        from . import database as db
        from .api.ui_settings import _read_settings
        from .api.batch import process_single_movie_poster, process_single_tv_show_poster
        from .api.webhooks import _get_default_remove_labels

        ui = db.get_ui_settings() or {}
        automation = ui.get("automation", {})

        if not automation.get("retryUntilTemplateMet", False):
            logger.debug("[RETRY] retryUntilTemplateMet is off — skipping retry run")
            return

        max_attempts = int(automation.get("retryMaxAttempts", 0))
        send_logos = bool(ui.get("plex", {}).get("sendLogosToPlex", False))

        # Build base label list (same source as auto_generate / webhooks)
        auto_labels_raw = automation.get("webhookAutoLabels", "Simposter")
        auto_labels = [l.strip() for l in auto_labels_raw.split(",") if l.strip()]

        pending = db.get_pending_retry_items(max_attempts=max_attempts)
        if not pending:
            logger.debug("[RETRY] No pending items in retry queue")
            return

        logger.info("[RETRY] Running retry job — %d pending items (max_attempts=%s)", len(pending), max_attempts or "unlimited")
        _job_start = time.time()

        for item in pending:
            rating_key = item["rating_key"]
            media_type = item.get("media_type", "movie")
            library_id = item.get("library_id", "")
            template_id = item["template_id"]
            preset_id = item["preset_id"]
            title = item.get("title", rating_key)
            retry_count = item.get("retry_count", 0)

            # Abandon if max_attempts exceeded -- removed outright, not just marked, so a
            # later delete-then-re-add of the same title (which arrives under a brand-new
            # rating_key, see CLAUDE.md Quirk #41) can't show up as two rows in the queue.
            if max_attempts > 0 and retry_count >= max_attempts:
                db.remove_from_retry_queue(rating_key)
                logger.info("[RETRY] Abandoned %s after %d attempts — removed from retry queue", title, retry_count)
                continue

            logger.info("[RETRY] Retrying %s (%s) attempt #%d", title, media_type, retry_count + 1)
            db.update_retry_attempt(rating_key)
            _retry_item_start = time.time()

            # Merge global auto_labels with per-library default labels for this item
            remove_labels = list(auto_labels)
            if library_id:
                lib_default_labels = _get_default_remove_labels(library_id)
                if lib_default_labels:
                    remove_labels = list({*remove_labels, *lib_default_labels})

            require_textless_poster = item.get("reason") == db.RETRY_REASON_MANUAL_TEXTLESS

            try:
                if media_type == "tv":
                    result = process_single_tv_show_poster(
                        rating_key=rating_key,
                        template_id=template_id,
                        preset_id=preset_id,
                        send_to_plex=True,
                        library_id=library_id,
                        labels=remove_labels,
                        include_seasons=True,
                        source="auto_generate",
                        send_logos_to_plex=send_logos,
                        send_only_if_ideal=True,
                        require_textless_poster=require_textless_poster,
                    )
                    # A dict without a populated "results" list means the render errored out
                    # before producing per-season results (e.g. a transient TMDb/network failure) —
                    # treat that as "still needs retry", not "nothing left to retry".
                    if isinstance(result, dict) and result.get("results"):
                        still_needs_retry = any(r.get("needs_retry", True) for r in result["results"])
                    else:
                        still_needs_retry = True
                else:
                    result = process_single_movie_poster(
                        rating_key=rating_key,
                        template_id=template_id,
                        preset_id=preset_id,
                        send_to_plex=True,
                        library_id=library_id,
                        labels=remove_labels,
                        source="auto_generate",
                        send_logos_to_plex=send_logos,
                        send_only_if_ideal=True,
                        require_textless_poster=require_textless_poster,
                    )
                    # Default True: an error dict (e.g. TMDb request failure) has no "needs_retry"
                    # key, and must NOT be read as "ideal conditions met" — that silently drops the
                    # item from the queue on a transient failure instead of leaving it pending.
                    still_needs_retry = result.get("needs_retry", True) if isinstance(result, dict) else True

                _retry_elapsed = time.time() - _retry_item_start
                if not still_needs_retry:
                    db.resolve_retry_queue_item(rating_key, "resolved")
                    logger.info("[RETRY] Successfully resolved %s in %.1fs — ideal template conditions met", title, _retry_elapsed)
                    continue

                # _process_single_movie()/_process_single_tv_show() already caught their own
                # exception internally (e.g. "No TMDb ID found" from a deleted/reorganized Plex
                # item) and returned a normal-looking error dict instead of raising -- so a hard
                # failure like this never reaches the `except Exception as retry_err` block below,
                # and the existence check there never runs. Checking here too closes that gap:
                # without it, an item whose Plex entry is genuinely gone retries forever, exactly
                # like the except block's own comment already warns about, just via a path it can't
                # see. Confirmed live: a deleted movie retried 72 times over ~18 days, a fresh
                # "failed" History row every cycle, before this branch existed.
                is_hard_error = isinstance(result, dict) and result.get("status") == "error"
                if is_hard_error and _plex_item_exists(rating_key) is False:
                    db.remove_from_retry_queue(rating_key)
                    logger.info(
                        "[RETRY] %s (rating_key=%s) no longer exists in Plex — removed from retry queue",
                        title, rating_key
                    )
                else:
                    logger.info("[RETRY] %s still pending in %.1fs (attempt #%d) — will retry again", title, _retry_elapsed, retry_count + 1)

            except Exception as retry_err:
                logger.warning("[RETRY] Error retrying %s after %.1fs: %s", title, time.time() - _retry_item_start, retry_err)
                # A render error here (as opposed to a clean "needs_retry" result
                # above) most often means the Plex fetch itself failed -- and if
                # that's because the item was deleted/reorganized in Plex (a
                # definitive 404, not a transient network error), it will NEVER
                # succeed no matter how many times this job retries it. Without
                # this check such an item retries forever whenever
                # retryMaxAttempts is 0 (unlimited), silently filling History
                # with a fresh "failed" entry every retry cycle.
                if _plex_item_exists(rating_key) is False:
                    db.remove_from_retry_queue(rating_key)
                    logger.info(
                        "[RETRY] %s (rating_key=%s) no longer exists in Plex — removed from retry queue",
                        title, rating_key
                    )

        logger.info("[RETRY] Retry job complete — %d items in %.1fs", len(pending), time.time() - _job_start)

    except Exception as e:
        logger.error("[RETRY] Unexpected error in retry job: %s", e, exc_info=True)


def shutdown_scheduler():
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("[SCHEDULER] Scheduler shut down")
