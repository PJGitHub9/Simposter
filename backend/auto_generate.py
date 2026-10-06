"""
Automatic poster generation for new content detected during library scans.
"""
import logging
from typing import List, Dict, Any, Optional
from . import database as db
from .api.batch import process_single_movie_poster, process_single_tv_show_poster
from .api.webhooks import _get_item_labels, _get_webhook_ignore_labels, _get_default_remove_labels, _webhook_cooldowns, _webhook_cooldown_lock, WEBHOOK_COOLDOWN_SECONDS
from .api.notifications import send_apprise_notification, send_discord_notification
from .config import settings, plex_session, plex_headers, load_render_cache, plex_remove_label, plex_add_label, get_label_to_add

# Use the shared logger so logs appear in the main log
logger = logging.getLogger("simposter")


def _recently_handled_by_webhook(rating_key: str, tmdb_id: Optional[Any] = None, tvdb_id: Optional[Any] = None) -> bool:
    """Return True if a webhook processed this item within the cooldown window.

    Cooldown keys are colon-separated (webhooks.py): Radarr keys on the TMDb
    id (`radarr:{tmdb_id}:{template}:{preset}`), Sonarr on the TVDB id
    (`sonarr:{tvdb_id}:...`), Tautulli on the rating key
    (`tautulli:{movie|tv}:{rating_key}:...`). Each id is compared EXACTLY
    against its own segment. The old version looked Radarr/Sonarr keys up by
    rating key (so it never matched a real webhook) and then fell back to a
    substring check (`rating_key in key`), which could match an unrelated
    item -- rating key "58" matched "radarr:5825:..." -- the same class of
    bug as CLAUDE.md Quirk #25.
    """
    import time as _time
    rk = str(rating_key) if rating_key else None
    tmdb = str(tmdb_id) if tmdb_id else None
    tvdb = str(tvdb_id) if tvdb_id else None
    now = _time.time()
    with _webhook_cooldown_lock:
        for key, last in _webhook_cooldowns.items():
            if not last or (now - last) >= WEBHOOK_COOLDOWN_SECONDS:
                continue
            parts = str(key).split(":")
            kind = parts[0] if parts else ""
            if kind == "radarr" and tmdb and len(parts) > 1 and parts[1] == tmdb:
                return True
            if kind == "sonarr" and tvdb and len(parts) > 1 and parts[1] == tvdb:
                return True
            if kind == "tautulli" and rk and len(parts) > 2 and parts[2] == rk:
                return True
    return False


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
        send_logos = bool(plex_settings.get("sendLogosToPlex", False))
        logger.info("[AUTO_GEN] sendLogosToPlex=%s", send_logos)

        retry_settings = ui_settings.get("automation", {})
        retry_enabled = bool(retry_settings.get("retryUntilTemplateMet", False))

        # Get automation settings for this library
        automation_config = ui_settings.get("automation", {})
        auto_labels = automation_config.get("webhookAutoLabels", "Simposter").split(",")
        auto_labels = [label.strip() for label in auto_labels if label.strip()]

        # Process movies
        if new_movies:
            library_mappings = plex_settings.get("libraryMappings", [])
            library_config = next((lib for lib in library_mappings if str(lib.get("id", "")) == str(library_id)), None)

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

                            # Resend cached poster if setting requests it and one exists
                            if auto_send and ui_settings.get("automation", {}).get("existingContentMode") == "resend":
                                cached = load_render_cache(rating_key)
                                if cached:
                                    try:
                                        plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
                                        plex_session.post(
                                            plex_url,
                                            headers={**plex_headers(), "Content-Type": "image/jpeg"},
                                            data=cached,
                                            timeout=20,
                                        ).raise_for_status()
                                        results["movies_succeeded"] += 1
                                        logger.info(f"[AUTO_GEN] Resent cached poster for {title} (existingContentMode=resend)")
                                        db.record_poster_history(
                                            rating_key=rating_key,
                                            library_id=str(library_id or ""),
                                            title=title,
                                            year=year,
                                            template_id=template_id,
                                            preset_id=preset_id,
                                            action="resent_to_plex",
                                            source="auto_generate",
                                            poster_data=cached,
                                        )
                                        # Remove configured labels after resend
                                        try:
                                            _rm_labels = list(auto_labels)
                                            lib_default_labels = _get_default_remove_labels(library_id)
                                            if lib_default_labels:
                                                _rm_labels = list({*_rm_labels, *lib_default_labels})
                                            if _rm_labels:
                                                logger.info(f"[AUTO_GEN] Removing labels {_rm_labels} from {rating_key} (resend)")
                                                _removed = []
                                                for _lbl in _rm_labels:
                                                    plex_remove_label(rating_key, _lbl)
                                                    logger.info(f"[AUTO_GEN] Removed label '{_lbl}' from {rating_key}")
                                                    _removed.append(_lbl.lower())
                                                if _removed:
                                                    _cur = db.get_movie_labels(rating_key)
                                                    db.update_movie_labels(rating_key, [l for l in _cur if l.lower() not in _removed])
                                        except Exception as _lbl_err:
                                            logger.warning(f"[AUTO_GEN] Label removal after resend failed for {title}: {_lbl_err}")
                                        # Add tracking label if configured (opposite direction
                                        # from the removal above — see get_label_to_add()'s docstring)
                                        try:
                                            _label_to_add = get_label_to_add()
                                            if _label_to_add:
                                                plex_add_label(rating_key, _label_to_add, content_type="1")
                                                logger.info(f"[AUTO_GEN] Added label '{_label_to_add}' to {rating_key} (resend)")
                                                _cur = db.get_movie_labels(rating_key)
                                                if _label_to_add.lower() not in [l.lower() for l in _cur]:
                                                    db.update_movie_labels(rating_key, _cur + [_label_to_add])
                                        except Exception as _lbl_err:
                                            logger.warning(f"[AUTO_GEN] Label add after resend failed for {title}: {_lbl_err}")
                                    except Exception as resend_err:
                                        logger.warning(f"[AUTO_GEN] Cache resend failed for {title}: {resend_err} — falling through to generation")
                                    else:
                                        continue

                            # Merge global auto_labels with per-library default labels to remove
                            remove_labels = list(auto_labels)
                            if auto_send:
                                lib_default_labels = _get_default_remove_labels(library_id)
                                if lib_default_labels:
                                    remove_labels = list({*remove_labels, *lib_default_labels})

                            # Use the batch processing logic which includes fallback handling
                            result = process_single_movie_poster(
                                rating_key=rating_key,
                                template_id=template_id,
                                preset_id=preset_id,
                                send_to_plex=auto_send,
                                library_id=library_id,
                                labels=remove_labels if auto_send else [],
                                source='auto_generate',
                                send_logos_to_plex=send_logos if auto_send else False,
                            )

                            if result.get("status") == "ok":
                                results["movies_succeeded"] += 1
                                logger.info(f"[AUTO_GEN] Successfully generated poster for {title}")
                                # Enqueue for retry if ideal template conditions weren't met
                                if retry_enabled and result.get("needs_retry"):
                                    try:
                                        db.add_to_retry_queue(
                                            rating_key=rating_key,
                                            media_type="movie",
                                            library_id=library_id,
                                            template_id=template_id,
                                            preset_id=preset_id,
                                            title=title,
                                            reason=result.get("retry_reason", "unknown"),
                                        )
                                        logger.info("[AUTO_GEN] Queued %s for retry (reason=%s)", title, result.get("retry_reason"))
                                    except Exception as queue_err:
                                        logger.debug("[AUTO_GEN] Failed to enqueue retry for %s: %s", title, queue_err)
                                elif retry_enabled:
                                    # Ideal conditions met — remove from queue if it was previously pending
                                    try:
                                        db.remove_from_retry_queue(rating_key)
                                    except Exception:
                                        pass
                                # Send per-item notification with poster preview
                                _notif_kwargs = dict(
                                    title=title or result.get("title", "Unknown"),
                                    year=year,
                                    template_id=template_id,
                                    preset_id=preset_id,
                                    library_id=library_id,
                                    source="auto_generate",
                                    action="sent_to_plex" if auto_send else "saved",
                                )
                                try:
                                    send_discord_notification(**_notif_kwargs, poster_data=result.get("poster_data"))
                                except Exception as notif_err:
                                    logger.debug(f"[AUTO_GEN] Discord notification failed: {notif_err}")
                                try:
                                    send_apprise_notification(**_notif_kwargs, poster_data=result.get("poster_data"))
                                except Exception as notif_err:
                                    logger.debug(f"[AUTO_GEN] Apprise notification failed: {notif_err}")
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
            tv_library_config = next((lib for lib in tv_library_mappings if str(lib.get("id", "")) == str(library_id)), None)

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

                            # Resend cached poster if setting requests it and one exists
                            if auto_send and ui_settings.get("automation", {}).get("existingContentMode") == "resend":
                                cached = load_render_cache(rating_key)
                                if cached:
                                    try:
                                        plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
                                        plex_session.post(
                                            plex_url,
                                            headers={**plex_headers(), "Content-Type": "image/jpeg"},
                                            data=cached,
                                            timeout=20,
                                        ).raise_for_status()
                                        results["tv_shows_succeeded"] += 1
                                        logger.info(f"[AUTO_GEN] Resent cached poster for {title} (existingContentMode=resend)")
                                        db.record_poster_history(
                                            rating_key=rating_key,
                                            library_id=str(library_id or ""),
                                            title=title,
                                            year=year,
                                            template_id=template_id,
                                            preset_id=preset_id,
                                            action="resent_to_plex",
                                            source="auto_generate",
                                            poster_data=cached,
                                        )
                                        # Remove configured labels after resend
                                        try:
                                            _rm_labels = list(auto_labels)
                                            lib_default_labels = _get_default_remove_labels(library_id)
                                            if lib_default_labels:
                                                _rm_labels = list({*_rm_labels, *lib_default_labels})
                                            if _rm_labels:
                                                logger.info(f"[AUTO_GEN] Removing labels {_rm_labels} from {rating_key} (resend)")
                                                _removed = []
                                                for _lbl in _rm_labels:
                                                    plex_remove_label(rating_key, _lbl)
                                                    logger.info(f"[AUTO_GEN] Removed label '{_lbl}' from {rating_key}")
                                                    _removed.append(_lbl.lower())
                                                if _removed:
                                                    _cur = db.get_tv_labels(rating_key)
                                                    db.update_tv_labels(rating_key, [l for l in _cur if l.lower() not in _removed], library_id=library_id)
                                        except Exception as _lbl_err:
                                            logger.warning(f"[AUTO_GEN] Label removal after resend failed for {title}: {_lbl_err}")
                                        # Add tracking label if configured (opposite direction
                                        # from the removal above — see get_label_to_add()'s docstring)
                                        try:
                                            _label_to_add = get_label_to_add()
                                            if _label_to_add:
                                                plex_add_label(rating_key, _label_to_add)
                                                logger.info(f"[AUTO_GEN] Added label '{_label_to_add}' to {rating_key} (resend)")
                                                _cur = db.get_tv_labels(rating_key)
                                                if _label_to_add.lower() not in [l.lower() for l in _cur]:
                                                    db.update_tv_labels(rating_key, _cur + [_label_to_add], library_id=library_id)
                                        except Exception as _lbl_err:
                                            logger.warning(f"[AUTO_GEN] Label add after resend failed for {title}: {_lbl_err}")
                                    except Exception as resend_err:
                                        logger.warning(f"[AUTO_GEN] Cache resend failed for {title}: {resend_err} — falling through to generation")
                                    else:
                                        continue

                            # Merge global auto_labels with per-library default labels to remove
                            remove_labels = list(auto_labels)
                            if auto_send:
                                lib_default_labels = _get_default_remove_labels(library_id)
                                if lib_default_labels:
                                    remove_labels = list({*remove_labels, *lib_default_labels})

                            # Use the batch processing logic which includes fallback handling
                            # include_seasons=True means it will generate posters for all seasons
                            result = process_single_tv_show_poster(
                                rating_key=rating_key,
                                template_id=template_id,
                                preset_id=preset_id,
                                send_to_plex=auto_send,
                                library_id=library_id,
                                labels=remove_labels if auto_send else [],
                                include_seasons=True,  # Generate all season posters
                                source='auto_generate',
                                send_logos_to_plex=send_logos if auto_send else False
                            )

                            if result.get("status") == "ok":
                                results["tv_shows_succeeded"] += 1
                                logger.info(f"[AUTO_GEN] Successfully generated posters for {title}")
                                # Enqueue for retry if ideal template conditions weren't met
                                if retry_enabled:
                                    sub_results = result.get("results", [])
                                    needs_retry_items = [r for r in sub_results if r.get("needs_retry")]
                                    if needs_retry_items:
                                        try:
                                            db.add_to_retry_queue(
                                                rating_key=rating_key,
                                                media_type="tv",
                                                library_id=library_id,
                                                template_id=template_id,
                                                preset_id=preset_id,
                                                title=title,
                                                reason=needs_retry_items[0].get("retry_reason", "unknown"),
                                            )
                                            logger.info("[AUTO_GEN] Queued TV show %s for retry", title)
                                        except Exception as queue_err:
                                            logger.debug("[AUTO_GEN] Failed to enqueue TV retry for %s: %s", title, queue_err)
                                    else:
                                        try:
                                            db.remove_from_retry_queue(rating_key)
                                        except Exception:
                                            pass
                                # Send per-item notification with poster preview
                                _notif_kwargs = dict(
                                    title=title or result.get("title", "Unknown"),
                                    year=year,
                                    template_id=template_id,
                                    preset_id=preset_id,
                                    library_id=library_id,
                                    source="auto_generate",
                                    action="sent_to_plex" if auto_send else "saved",
                                )
                                try:
                                    send_discord_notification(**_notif_kwargs, poster_data=result.get("poster_data"))
                                except Exception as notif_err:
                                    logger.debug(f"[AUTO_GEN] Discord notification failed: {notif_err}")
                                try:
                                    send_apprise_notification(**_notif_kwargs, poster_data=result.get("poster_data"))
                                except Exception as notif_err:
                                    logger.debug(f"[AUTO_GEN] Apprise notification failed: {notif_err}")
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


def _resolve_auto_generate_config(group: Dict[str, Any], media_type: str, ui_settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Where a Library Group's auto-generate settings live depends on whether
    it has a Plex member: a Plex-anchored group still keeps them on that Plex
    library's own plex.libraryMappings/tvShowLibraryMappings entry (what the
    Plex scan path above reads), a Plex-less group keeps them on the group
    itself (LibraryGroup.autoGenerate*). Returns {template_id, preset_id} when
    auto-generate is enabled and fully configured, else None."""
    plex_member = next((m for m in group.get("members") or [] if m.get("serverId") == "plex-1"), None)
    if plex_member:
        key = "libraryMappings" if media_type == "movie" else "tvShowLibraryMappings"
        mappings = (ui_settings.get("plex") or {}).get(key) or []
        cfg = next((m for m in mappings if str(m.get("id", "")) == str(plex_member.get("libraryId"))), None) or {}
    else:
        cfg = group
    if not cfg.get("autoGenerateEnabled"):
        return None
    template_id = cfg.get("autoGenerateTemplateId")
    preset_id = cfg.get("autoGeneratePresetId")
    if not (template_id and preset_id):
        return None
    return {"template_id": template_id, "preset_id": preset_id}


def process_new_media_server_content(
    server_id: str,
    library_id: str,
    media_type: str,
    new_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Auto-generate posters for items a Jellyfin/Emby library scan just
    discovered -- the non-Plex counterpart of process_new_content_for_library().

    Before this, auto-generation only ever ran at the end of a PLEX scan, so a
    Jellyfin/Emby-only library got automatic posters solely from Radarr/Sonarr
    webhooks, never from its own (manual or scheduled) scans.

    Rendering + delivery reuses the exact webhook pipeline already built for
    non-Plex targets (process_webhook_poster_generation(server_id=...), Phase
    8b), so it gets the same sync-to-linked-servers, retry-queue, History and
    notification behavior -- just labelled source="auto_generate".

    For a group that ALSO has a Plex member, an item that Plex has too (same
    tmdb_id/tvdb_id in the Plex member's library) is skipped: the Plex scan's
    own auto-generate already renders it and syncs it to the linked servers,
    so generating it again from the Jellyfin side would double the work and
    could race the Plex render. Only items that exist on the non-Plex side
    alone get generated here.
    """
    from .config import get_library_group_for
    from .api.webhooks import process_webhook_poster_generation

    # "processed" = handed to the render pipeline; it logs/records its own
    # per-item outcome (History, notifications), so success isn't re-counted here.
    results = {"processed": 0, "failed": 0, "skipped": 0}
    if not new_items:
        return results
    try:
        ui_settings = db.get_ui_settings() or {}
        group = get_library_group_for(server_id, library_id, media_type)
        if not group:
            logger.debug("[AUTO_GEN] %s library %s isn't in a library group, skipping auto-generation", server_id, library_id)
            return results
        cfg = _resolve_auto_generate_config(group, media_type, ui_settings)
        if not cfg:
            logger.debug("[AUTO_GEN] Auto-generation not enabled for group %s", group.get("name") or group.get("id"))
            return results

        plex_member = next((m for m in group.get("members") or [] if m.get("serverId") == "plex-1"), None)
        on_plex: set = set()
        if plex_member:
            plex_lib = str(plex_member.get("libraryId"))
            rows = db.get_cached_movies(library_id=plex_lib) if media_type == "movie" else db.get_cached_tv_shows(library_id=plex_lib)
            for r in rows:
                if r.get("server_id", "plex-1") != "plex-1":
                    continue
                if r.get("tmdb_id"):
                    on_plex.add(("tmdb", str(r["tmdb_id"])))
                if r.get("tvdb_id"):
                    on_plex.add(("tvdb", str(r["tvdb_id"])))

        logger.info("[AUTO_GEN] Processing %d new %s item(s) from %s library %s with %s:%s",
                    len(new_items), media_type, server_id, library_id, cfg["template_id"], cfg["preset_id"])
        for item in new_items:
            rating_key = item.get("rating_key")
            title = item.get("title") or rating_key
            if not rating_key:
                continue
            if on_plex and (
                (item.get("tmdb_id") and ("tmdb", str(item["tmdb_id"])) in on_plex)
                or (item.get("tvdb_id") and ("tvdb", str(item["tvdb_id"])) in on_plex)
            ):
                results["skipped"] += 1
                logger.info("[AUTO_GEN] Skipping %s on %s -- also on Plex, the Plex scan handles it", title, server_id)
                continue
            if _recently_handled_by_webhook(rating_key, item.get("tmdb_id"), item.get("tvdb_id")):
                results["skipped"] += 1
                logger.info("[AUTO_GEN] Skipping %s on %s -- recently processed by a webhook", title, server_id)
                continue
            results["processed"] += 1
            try:
                process_webhook_poster_generation(
                    rating_key=rating_key,
                    template_id=cfg["template_id"],
                    preset_id=cfg["preset_id"],
                    auto_send=True,
                    auto_labels=[],
                    library_id=library_id,
                    is_tv=(media_type == "tv"),
                    include_seasons=(media_type == "tv"),
                    server_id=server_id,
                    source="auto_generate",
                )
            except Exception as e:
                results["failed"] += 1
                logger.error("[AUTO_GEN] Failed to generate poster for %s on %s: %s", title, server_id, e)
    except Exception as e:
        logger.error("[AUTO_GEN] Error processing new %s content for %s library %s: %s", media_type, server_id, library_id, e, exc_info=True)
    logger.info("[AUTO_GEN] %s library %s auto-generation complete: %s", server_id, library_id, results)
    return results


def process_new_media_server_content_async(server_id: str, library_id: str, media_type: str, new_items: List[Dict[str, Any]]) -> None:
    """Runs process_new_media_server_content() in a background thread so the
    scan that discovered the items (a manual Settings click, or the scheduled
    job) returns promptly instead of blocking on every render."""
    if not new_items:
        return
    import threading
    threading.Thread(
        target=process_new_media_server_content,
        args=(server_id, library_id, media_type, list(new_items)),
        name=f"auto-gen-{server_id}-{library_id}",
        daemon=True,
    ).start()
