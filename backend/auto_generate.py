"""
Automatic poster generation for new content detected during library scans.
"""
import logging
from typing import List, Dict, Any, Optional
from . import database as db
from .api.batch import process_single_movie_poster, process_single_tv_show_poster
from .api.webhooks import _get_item_labels, _get_webhook_ignore_labels

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
        auto_labels = automation_config.get("webhookAutoLabels", "Overlay").split(",")
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

    return results
