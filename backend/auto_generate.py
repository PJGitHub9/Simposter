"""
Automatic poster generation for new content detected during library scans.
"""
import logging
import time
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from . import database as db
from .api.batch import process_single_movie_poster, process_single_tv_show_poster
from .api.webhooks import _get_item_labels, _get_webhook_ignore_labels
from .api.notifications import send_batch_notification

# Use the shared logger so logs appear in the main log
logger = logging.getLogger("simposter")


def _should_skip_auto_generate(rating_key: str, library_id: str, is_tv: bool = False) -> bool:
    """
    Check if auto-generation should be skipped based on item labels.

    Returns:
        True if the item should be skipped (has an ignore label), False otherwise
    """
    ignore_labels = _get_webhook_ignore_labels(library_id, is_tv)
    if not ignore_labels:
        return False

    item_labels = _get_item_labels(rating_key)
    if not item_labels:
        return False

    # Check if any item label matches an ignore label (case-insensitive)
    ignore_labels_lower = [label.lower() for label in ignore_labels]
    for label in item_labels:
        if label.lower() in ignore_labels_lower:
            logger.info(f"[AUTO_GEN] Skipping {rating_key} - has ignore label '{label}'")
            return True

    return False


def process_new_content_for_library(
    library_id: str,
    new_movies: List[Dict[str, Any]],
    new_tv_shows: List[Dict[str, Any]],
    auto_send: bool = True
) -> Dict[str, Any]:
    """
    Process new movies and TV shows for automatic poster generation.

    Args:
        library_id: The library ID to check automation settings for
        new_movies: List of new movie objects with keys: rating_key, title, year
        new_tv_shows: List of new TV show objects with keys: rating_key, title, year
        auto_send: Whether to automatically send generated posters to Plex

    Returns:
        Dictionary with success/failure counts
    """
    results = {
        "movies_processed": 0,
        "movies_succeeded": 0,
        "movies_failed": 0,
        "movies_skipped": 0,
        "tv_shows_processed": 0,
        "tv_shows_succeeded": 0,
        "tv_shows_failed": 0,
        "tv_shows_skipped": 0,
    }

    # Get UI settings to check library automation config
    try:
        ui_settings = db.get_ui_settings()
        if not ui_settings:
            logger.debug("[AUTO_GEN] No UI settings found, skipping auto-generation")
            return results

        plex_settings = ui_settings.get("plex", {})

        # Get automation settings for this library
        automation_config = ui_settings.get("automation", {})
        auto_labels = automation_config.get("webhookAutoLabels", "Simposter").split(",")
        auto_labels = [label.strip() for label in auto_labels if label.strip()]

        # Process movies
        if new_movies:
            library_mappings = plex_settings.get("libraryMappings", [])
            library_config = next((lib for lib in library_mappings if lib.get("id") == library_id), None)

            if library_config and library_config.get("autoGenerateEnabled"):
                template_id = library_config.get("autoGenerateTemplateId")
                preset_id = library_config.get("autoGeneratePresetId")

                if template_id and preset_id:
                    logger.info(f"[AUTO_GEN] Processing {len(new_movies)} new movies for library {library_id} with {template_id}:{preset_id}")

                    for movie in new_movies:
                        results["movies_processed"] += 1
                        try:
                            rating_key = movie.get("rating_key") or movie.get("key")
                            title = movie.get("title")
                            year = movie.get("year")

                            # Check if item has ignore labels - skip generation but item is still scanned/added
                            if _should_skip_auto_generate(rating_key, library_id, is_tv=False):
                                results["movies_skipped"] += 1
                                logger.info(f"[AUTO_GEN] Skipping poster generation for {title} ({year}) - has ignore label")
                                continue

                            logger.info(f"[AUTO_GEN] Generating poster for movie: {title} ({year}) [key={rating_key}]")

                            # Use the batch processing logic which includes fallback handling
                            success = process_single_movie_poster(
                                rating_key=rating_key,
                                template_id=template_id,
                                preset_id=preset_id,
                                send_to_plex=auto_send,
                                library_id=library_id,
                                labels=auto_labels if auto_send else [],
                                source='auto_generate'
                            )

                            if success:
                                results["movies_succeeded"] += 1
                                logger.info(f"[AUTO_GEN] Successfully generated poster for {title}")
                            else:
                                results["movies_failed"] += 1
                                logger.warning(f"[AUTO_GEN] Failed to generate poster for {title}")

                        except Exception as e:
                            results["movies_failed"] += 1
                            logger.error(f"[AUTO_GEN] Error generating poster for movie {movie.get('title')}: {e}")
                else:
                    logger.debug(f"[AUTO_GEN] Library {library_id} has auto-generation enabled but no template/preset configured")
            else:
                logger.debug(f"[AUTO_GEN] Auto-generation not enabled for movie library {library_id}")

        # Process TV shows
        if new_tv_shows:
            tv_library_mappings = plex_settings.get("tvShowLibraryMappings", [])
            tv_library_config = next((lib for lib in tv_library_mappings if lib.get("id") == library_id), None)

            if tv_library_config and tv_library_config.get("autoGenerateEnabled"):
                template_id = tv_library_config.get("autoGenerateTemplateId")
                preset_id = tv_library_config.get("autoGeneratePresetId")

                if template_id and preset_id:
                    logger.info(f"[AUTO_GEN] Processing {len(new_tv_shows)} new TV shows for library {library_id} with {template_id}:{preset_id}")

                    for show in new_tv_shows:
                        results["tv_shows_processed"] += 1
                        try:
                            rating_key = show.get("rating_key") or show.get("key")
                            title = show.get("title")
                            year = show.get("year")

                            # Check if item has ignore labels - skip generation but item is still scanned/added
                            if _should_skip_auto_generate(rating_key, library_id, is_tv=True):
                                results["tv_shows_skipped"] += 1
                                logger.info(f"[AUTO_GEN] Skipping poster generation for {title} ({year}) - has ignore label")
                                continue

                            logger.info(f"[AUTO_GEN] Generating posters for TV show: {title} ({year}) [key={rating_key}]")

                            # Use the batch processing logic which includes fallback handling
                            # include_seasons=True means it will generate posters for all seasons
                            success = process_single_tv_show_poster(
                                rating_key=rating_key,
                                template_id=template_id,
                                preset_id=preset_id,
                                send_to_plex=auto_send,
                                library_id=library_id,
                                labels=auto_labels if auto_send else [],
                                include_seasons=True,  # Generate all season posters
                                source='auto_generate'
                            )

                            if success:
                                results["tv_shows_succeeded"] += 1
                                logger.info(f"[AUTO_GEN] Successfully generated posters for {title}")
                            else:
                                results["tv_shows_failed"] += 1
                                logger.warning(f"[AUTO_GEN] Failed to generate posters for {title}")

                        except Exception as e:
                            results["tv_shows_failed"] += 1
                            logger.error(f"[AUTO_GEN] Error generating posters for TV show {show.get('title')}: {e}")
                else:
                    logger.debug(f"[AUTO_GEN] Library {library_id} has auto-generation enabled but no template/preset configured")
            else:
                logger.debug(f"[AUTO_GEN] Auto-generation not enabled for TV library {library_id}")

    except Exception as e:
        logger.error(f"[AUTO_GEN] Error processing new content for library {library_id}: {e}", exc_info=True)

    # Send Discord notification for auto-generation completion
    total_succeeded = results["movies_succeeded"] + results["tv_shows_succeeded"]
    total_failed = results["movies_failed"] + results["tv_shows_failed"]
    if total_succeeded > 0 or total_failed > 0:
        try:
            # Get the template_id/preset_id from the library config
            template_id = ""
            preset_id = ""
            try:
                plex_settings = ui_settings.get("plex", {}) if ui_settings else {}
                library_mappings = plex_settings.get("libraryMappings", [])
                tv_mappings = plex_settings.get("tvShowLibraryMappings", [])
                config = next((lib for lib in library_mappings + tv_mappings if lib.get("id") == library_id), None)
                if config:
                    template_id = config.get("autoGenerateTemplateId", "")
                    preset_id = config.get("autoGeneratePresetId", "")
            except Exception:
                pass

            send_batch_notification(
                library_id=library_id,
                template_id=template_id,
                preset_id=preset_id,
                success_count=total_succeeded,
                failed_count=total_failed,
                source="auto_generate"
            )
        except Exception as notif_err:
            logger.debug(f"[AUTO_GEN] Failed to send Discord notification: {notif_err}")

    return results


def check_recently_added(lookback_minutes: int = 20) -> Dict[str, Any]:
    """
    Poll Plex for items added in the last `lookback_minutes` and auto-generate
    posters for any that aren't already in the Simposter cache.

    Runs efficiently — only fetches recently added items, not the full library.
    Called by the scheduler every 15 minutes so new content from any source
    (not just Radarr/Sonarr) gets posters without a manual scan.
    """
    from .config import settings as config_settings, plex_session, plex_headers
    from . import cache
    from .schemas import Movie

    results: Dict[str, Any] = {
        "libraries_checked": 0,
        "new_movies": 0,
        "new_tv": 0,
        "errors": [],
    }

    since_timestamp = int(time.time()) - (lookback_minutes * 60)

    try:
        ui_settings = db.get_ui_settings()
        if not ui_settings:
            return results

        plex_settings = ui_settings.get("plex", {})

        # Collect all unique library IDs across movie and TV mappings
        library_ids: set = set()
        for mapping in plex_settings.get("libraryMappings", []):
            if mapping.get("id"):
                library_ids.add(str(mapping["id"]))
        for mapping in plex_settings.get("tvShowLibraryMappings", []):
            if mapping.get("id"):
                library_ids.add(str(mapping["id"]))

        if not library_ids:
            logger.debug("[AUTO_GEN] No libraries configured, skipping recently added check")
            return results

        logger.debug("[AUTO_GEN] Checking for recently added items in %d libraries (since %ds ago)",
                     len(library_ids), lookback_minutes * 60)

        for library_id in library_ids:
            results["libraries_checked"] += 1

            # --- Movies (Plex type=1) ---
            existing_movie_keys = {m.get("rating_key") for m in cache.get_cached_movies(library_id=library_id)}
            new_movies: List[Dict[str, Any]] = []

            try:
                url = (
                    f"{config_settings.PLEX_URL}/library/sections/{library_id}/all"
                    f"?type=1&addedAt>={since_timestamp}&sort=addedAt:desc"
                    f"&X-Plex-Container-Size=100"
                )
                r = plex_session.get(url, headers=plex_headers(), timeout=10)
                if r.ok:
                    root = ET.fromstring(r.text)
                    for video in root.findall(".//Video"):
                        key = video.get("ratingKey")
                        if not key or key in existing_movie_keys:
                            continue
                        title = video.get("title", "Unknown")
                        year = video.get("year")
                        added_at = video.get("addedAt")
                        # Add to cache so future scans don't re-process it
                        cache.upsert_movie(Movie(
                            key=key,
                            title=title,
                            year=int(year) if year else None,
                            addedAt=int(added_at) if added_at else None,
                            library_id=library_id,
                        ))
                        new_movies.append({
                            "rating_key": key,
                            "title": title,
                            "year": int(year) if year else None,
                        })
                        logger.info("[AUTO_GEN] Recently added movie: %s (key=%s, library=%s)", title, key, library_id)
            except Exception as e:
                logger.warning("[AUTO_GEN] Error fetching recently added movies for library %s: %s", library_id, e)
                results["errors"].append(str(e))

            if new_movies:
                results["new_movies"] += len(new_movies)
                process_new_content_for_library(
                    library_id=library_id,
                    new_movies=new_movies,
                    new_tv_shows=[],
                    auto_send=True,
                )

            # --- TV Shows (Plex type=2) ---
            existing_tv_keys = {s.get("rating_key") for s in cache.get_cached_tv_shows(library_id=library_id)}
            new_tv: List[Dict[str, Any]] = []

            try:
                url_tv = (
                    f"{config_settings.PLEX_URL}/library/sections/{library_id}/all"
                    f"?type=2&addedAt>={since_timestamp}&sort=addedAt:desc"
                    f"&X-Plex-Container-Size=100"
                )
                r_tv = plex_session.get(url_tv, headers=plex_headers(), timeout=10)
                if r_tv.ok:
                    root_tv = ET.fromstring(r_tv.text)
                    for directory in root_tv.findall(".//Directory"):
                        key = directory.get("ratingKey")
                        if not key or key in existing_tv_keys:
                            continue
                        title = directory.get("title", "Unknown")
                        year = directory.get("year")
                        added_at = directory.get("addedAt")
                        # Add to cache so future scans don't re-process it
                        cache.upsert_tv_show({
                            "key": key,
                            "title": title,
                            "year": int(year) if year else None,
                            "addedAt": int(added_at) if added_at else None,
                            "library_id": library_id,
                        })
                        new_tv.append({
                            "rating_key": key,
                            "title": title,
                            "year": int(year) if year else None,
                        })
                        logger.info("[AUTO_GEN] Recently added TV show: %s (key=%s, library=%s)", title, key, library_id)
            except Exception as e:
                logger.warning("[AUTO_GEN] Error fetching recently added TV shows for library %s: %s", library_id, e)
                results["errors"].append(str(e))

            if new_tv:
                results["new_tv"] += len(new_tv)
                process_new_content_for_library(
                    library_id=library_id,
                    new_movies=[],
                    new_tv_shows=new_tv,
                    auto_send=True,
                )

    except Exception as e:
        logger.error("[AUTO_GEN] Unexpected error in check_recently_added: %s", e, exc_info=True)
        results["errors"].append(str(e))

    return results
