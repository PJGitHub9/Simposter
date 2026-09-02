from fastapi import APIRouter
from ..schemas import BatchRequest, MovieBatchRequest, TVShowBatchRequest
from ..config import settings, plex_remove_label, plex_add_label, get_label_to_add, logger, get_movie_tmdb_id, get_movie_folder_name, get_media_folder_name
from ..config import load_presets
from .notifications import send_batch_notification, send_apprise_notification, start_batch_progress_notification, update_batch_progress_notification, complete_batch_progress_notification
import time
from ..tmdb_client import get_images_for_movie, get_movie_details, get_tv_show_details, get_images_for_tv_show, get_tv_season_images, get_tv_external_ids
from ..rendering import render_poster_image, render_with_overlay_cache
from io import BytesIO
import requests
from backend.assets.selection import pick_poster, pick_logo, map_logo_mode_to_preference
from backend.logo_sources import get_logos_merged
from .movies import fetch_and_cache_poster
from .tv_shows import plex_session, plex_headers, extract_tmdb_id_from_metadata, extract_tvdb_id_from_metadata
from .save import embed_library_metadata, normalize_logo_for_plex
from ..save_paths import SaveContext, resolve_save_path, resolve_library_label, save_or_cache_render, save_to_asset_folder_on_send_enabled
from datetime import datetime, timezone
from PIL import Image, PngImagePlugin
from .. import database as db
from .. import tvdb_client
from ..fanart_client import get_images_for_tv_show as get_fanart_tv_images
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from typing import Optional, List, Dict, Any, Union

router = APIRouter()

batch_status = {
    "state": "idle",
    "total": 0,
    "processed": 0,
    "current_movie": "",
    "current_step": "",
    "started_at": None,
    "finished_at": None,
    "error": None,
}
batch_status_lock = threading.Lock()


def _update_batch_status(updates: dict):
    """Thread-safe batch status update."""
    with batch_status_lock:
        batch_status.update(updates)


@router.get("/batch-progress")
def api_batch_progress():
    """Return current batch operation progress."""
    with batch_status_lock:
        return dict(batch_status)


def _process_single_movie(
    idx: int,
    rating_key: str,
    req: Union[BatchRequest, MovieBatchRequest],
    base_options: dict,
    base_poster_filter: str,
    base_logo_preference: str,
    base_logo_mode: str,
    white_logo_fallback: str,
    language_pref: str,
    presets_data: dict,
    source: str = "batch",
):
    """Process a single movie in the batch. Returns result dict."""
    _item_start = time.time()
    # Best-effort display title, upgraded to the real TMDb title below once fetched —
    # a cheap local DB cache lookup (movie_cache, from the last library scan) so even
    # the very first "Start" log line can show a name instead of just a rating_key.
    title_hint = rating_key
    try:
        _cached_title, _ = db.get_title_for_rating_key(rating_key)
        if _cached_title:
            title_hint = _cached_title
    except Exception:
        pass

    # Lazy, memoized {folder} lookup -- a single-element list dodges the need for
    # `nonlocal` while still letting both the save_locally and send_to_plex blocks
    # below share one Plex metadata fetch instead of firing it twice per movie.
    _folder_name_cache: list = []

    def _get_movie_folder_name_once() -> Optional[str]:
        if not _folder_name_cache:
            _folder_name_cache.append(get_movie_folder_name(rating_key))
        return _folder_name_cache[0]

    try:
        template_id = req.template_id
        preset_id = req.preset_id
        render_options_base = dict(base_options)
        poster_filter = base_poster_filter
        logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or base_logo_preference
        logo_preference = map_logo_mode_to_preference(logo_preference)
        logo_mode = base_logo_mode

        logger.info("[BATCH] Start rating_key=%s [%s] template=%s", rating_key, title_hint, template_id)

        # ---------------------------
        # TMDb Fetch
        # ---------------------------
        _update_batch_status({
            "current_movie": rating_key,
            "current_step": "Fetching TMDb data",
        })

        tmdb_id = get_movie_tmdb_id(rating_key)
        if not tmdb_id:
            raise Exception("No TMDb ID found.")
        logger.debug("[BATCH] rating_key=%s [%s] tmdb_id=%s", rating_key, title_hint, tmdb_id)

        # Fetch movie details for template variables
        movie_details = get_movie_details(tmdb_id)
        title_hint = movie_details.get("title") or title_hint
        # Fetch images honoring preferred languages (fallback to movie original language)
        imgs = get_images_for_movie(tmdb_id, movie_details.get("original_language"))
        posters = imgs.get("posters", [])

        # Get logos using merged sources based on preference
        logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
        logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
        logger.debug(
            "[BATCH] rating_key=%s [%s] posters=%d logos=%d filter=%s logo_pref=%s",
            rating_key,
            title_hint,
            len(posters),
            len(logos),
            poster_filter,
            logo_preference,
        )
        logger.debug("[BATCH] Movie details: title='%s' year=%s", movie_details.get("title"), movie_details.get("year"))

        _update_batch_status({
            "current_movie": movie_details.get("title", rating_key),
            "current_step": "Selecting assets",
        })

        # ---------------------------
        # Auto-select assets
        # ---------------------------
        poster = pick_poster(posters, poster_filter)
        logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference, white_logo_fallback, language_pref)

        poster_fallback_action_used = None
        poster_fallback_template_used = None
        poster_fallback_preset_used = None
        logo_fallback_used = False
        logo_fallback_template_used = None
        logo_fallback_preset_used = None

        # Fallback handling for poster preference (runs before any logo fallback)
        if not poster:
            fallback_action = render_options_base.get("fallbackPosterAction") or "continue"
            poster_fallback_action_used = fallback_action
            fallback_template = render_options_base.get("fallbackPosterTemplate")
            fallback_preset = render_options_base.get("fallbackPosterPreset")
            if fallback_action == "template" and fallback_template:
                poster_fallback_template_used = fallback_template
                poster_fallback_preset_used = fallback_preset
                template_id = fallback_template
                if fallback_preset:
                    tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
                    fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None)
                    if fpreset:
                        fp_opts = fpreset.get("options", {})
                        # Let fallback preset options override original options (matching preview behavior)
                        render_options_base = {**render_options_base, **fp_opts}
                        poster_filter = render_options_base.get("poster_filter", poster_filter)
                        logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or logo_preference
                        logo_preference = map_logo_mode_to_preference(logo_preference)
                        logo_mode = render_options_base.get("logo_mode", logo_mode)
                        preset_id = fallback_preset
                        logger.info("[BATCH] Applied fallback poster template '%s' preset '%s'", fallback_template, fallback_preset)
                    else:
                        logger.warning("[BATCH] Fallback preset '%s' not found for template '%s'", fallback_preset, fallback_template)
                # Re-pick poster with updated filter from fallback preset
                poster = pick_poster(posters, poster_filter)
                # Re-evaluate logos with any updated preferences from the fallback preset
                logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
                logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
                logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference, white_logo_fallback, language_pref)
            elif fallback_action == "skip":
                return {
                    "rating_key": rating_key,
                    "title": movie_details.get("title", ""),
                    "status": "skipped_no_poster",
                    "poster_fallback": False,
                    "logo_fallback": False,
                }
            else:  # continue
                poster = posters[0] if posters else None

        if not poster:
            raise Exception("No valid poster found (even after fallback).")

        poster_url = poster.get("url")
        # Initialize logo_url for fallback logic
        logo_url = None

        # Only run logo fallback when poster handling chose to continue
        allow_logo_fallback = poster_fallback_action_used in (None, "continue")

        # Logo fallback handling
        if allow_logo_fallback and not logo and logo_mode != "none":
            fallback_logo_action = render_options_base.get("fallbackLogoAction") or "continue"
            fallback_logo_template = render_options_base.get("fallbackLogoTemplate")
            fallback_logo_preset = render_options_base.get("fallbackLogoPreset")
            logger.info("[BATCH] No logo found for %s [%s] — fallback action: %s", rating_key, title_hint, fallback_logo_action)
            if fallback_logo_action == "template" and fallback_logo_template:
                logo_fallback_used = True
                logo_fallback_template_used = fallback_logo_template
                logo_fallback_preset_used = fallback_logo_preset
                template_id = fallback_logo_template
                if fallback_logo_preset:
                    tpl_presets = presets_data.get(fallback_logo_template, {}).get("presets", [])
                    fpreset = next((p for p in tpl_presets if p.get("id") == fallback_logo_preset), None)
                    if fpreset:
                        fp_opts = fpreset.get("options", {})
                        # Let fallback preset options override original options (matching preview behavior)
                        render_options_base = {**render_options_base, **fp_opts}
                        poster_filter = render_options_base.get("poster_filter", poster_filter)
                        logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or logo_preference
                        logo_preference = map_logo_mode_to_preference(logo_preference)
                        logo_mode = render_options_base.get("logo_mode", logo_mode)
                        preset_id = fallback_logo_preset
                        logger.info("[BATCH] Applied fallback logo template '%s' preset '%s'", fallback_logo_template, fallback_logo_preset)
                        # Re-fetch logos if logo source changed, or check for static logo override
                        logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
                        logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
                        # Re-pick poster with the fallback template's poster_filter
                        poster = pick_poster(posters, poster_filter)
                        if poster:
                            poster_url = poster.get("url")
                            logger.info("[BATCH] Re-picked poster with fallback filter '%s': %s", poster_filter, poster_url)
                        # Check if fallback preset provides a static logo URL
                        logo_override = render_options_base.get("logo_url") or render_options_base.get("logoUrl")
                        if logo_override:
                            logo_url = logo_override
                            logo = None
                            logger.info("[BATCH] Using static logo URL from fallback preset: %s", logo_url)
                    else:
                        logger.warning("[BATCH] Fallback logo preset '%s' not found for template '%s'", fallback_logo_preset, fallback_logo_template)
                # Re-pick logo with updated preference and mode from fallback preset
                if logo_mode != "none" and logo_url is None:
                    logo = pick_logo(logos, logo_preference, white_logo_fallback, language_pref)
                    if logo:
                        logger.info("[BATCH] Picked logo after fallback: preference=%s", logo_preference)
            elif fallback_logo_action == "skip":
                return {
                    "rating_key": rating_key,
                    "title": movie_details.get("title", ""),
                    "status": "skipped_no_logo",
                    "poster_fallback": False,
                    "logo_fallback": False,
                }
            # else continue without logo

        # Set final logo_url if not already set by fallback override
        if logo_url is None:
            logo_url = logo.get("url") if logo else None
        logger.info(f"[BATCH] [{title_hint}] Picked logo pref={logo_preference}")
        logger.info(f"[BATCH] [{title_hint}] Picked poster={poster_url}")
        logger.info(f"[BATCH] [{title_hint}] Picked logo={logo_url}")

        # Determine whether the ideal template conditions were met.
        # logo_was_expected uses the original logo_mode (before fallback may have overwritten it
        # with "none") — but logo_fallback_used captures the case where the fallback fires and
        # logo_mode becomes "none", which would otherwise make logo_was_expected False.
        logo_was_expected = str(logo_mode).lower() != "none"
        needs_retry = (logo_was_expected and logo_url is None) or (poster_fallback_action_used == "template") or logo_fallback_used
        # Retry-queue runs only want to upload once the render actually meets the template spec
        skip_send_not_ideal = getattr(req, 'send_only_if_ideal', False) and needs_retry

        # ---------------------------
        # Render
        # ---------------------------
        _update_batch_status({
            "current_step": "Rendering poster",
        })

        # Add movie details to options for template variable substitution
        render_options = dict(render_options_base)
        render_options["movie_title"] = movie_details.get("title", "")
        render_options["movie_year"] = movie_details.get("year", "")

        # Inject Plex media metadata for overlay badges
        from ..config import get_plex_media_info
        plex_media = get_plex_media_info(rating_key)
        if plex_media:
            existing_meta = render_options.get("metadata") or {}
            render_options["metadata"] = {**existing_meta, **plex_media}

        # Inject tmdb_id and media_type for streaming platform badge resolution
        if tmdb_id:
            render_options.setdefault("metadata", {})
            render_options["metadata"]["tmdb_id"] = tmdb_id
            render_options["metadata"]["media_type"] = "movie"

        # Pass preset_id so the template renderer can look up linked overlay configs
        if preset_id:
            render_options["preset_id"] = preset_id

        # Check if overlay caching is enabled
        ui_settings = db.get_ui_settings()
        use_overlay_cache = ui_settings.get("performance", {}).get("useOverlayCache", True)

        img = render_with_overlay_cache(
            template_id,
            preset_id,
            poster_url,
            logo_url if logo_mode != "none" else None,
            render_options,
            use_cache=use_overlay_cache
        )

        # ---------------------------
        # Save locally (if requested)
        # ---------------------------
        save_path = None
        if req.save_locally:
            _update_batch_status({
                "current_step": "Saving locally",
            })

            library_label = resolve_library_label(req.library_id)
            from .save import get_output_format_settings
            fmt_settings = get_output_format_settings()

            movie_year = movie_details.get("year")
            ctx = SaveContext(
                media_type="movie",
                title=movie_details.get("title", rating_key),
                year=int(movie_year) if movie_year else None,
                rating_key=rating_key,
                library_label=library_label,
                folder_name=_get_movie_folder_name_once(),
            )
            save_path = resolve_save_path(ctx, fmt_settings["ext"], batch_subfolder=req.batch_subfolder)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Embed library metadata into the image
            img = embed_library_metadata(
                img,
                req.library_id,
                library_label,
                movie_details.get("title", ""),
                str(movie_details.get("year", "")) if movie_details.get("year") else None,
            )

            # Save in user's preferred format using fmt_settings
            pil_format = fmt_settings["pil_format"]

            if pil_format == "PNG":
                # For PNG, properly embed metadata in PNG chunks
                pnginfo = PngImagePlugin.PngInfo()
                pnginfo.add_text("simposter_library_id", str(req.library_id or ""))
                pnginfo.add_text("simposter_library_name", str(library_label or ""))
                pnginfo.add_text("simposter_movie_title", str(movie_details.get("title", "")))
                pnginfo.add_text("simposter_movie_year", str(movie_details.get("year", "")))
                pnginfo.add_text("simposter_rating_key", str(rating_key or ""))
                pnginfo.add_text("simposter_is_tv", "0")
                img.save(save_path, "PNG", pnginfo=pnginfo, compress_level=fmt_settings["quality"])
            elif pil_format == "WEBP":
                img.convert("RGB").save(save_path, "WEBP", quality=fmt_settings["quality"])
            else:
                # For JPEG, embed metadata in EXIF UserComment field
                img_rgb = img.convert("RGB")

                # Create EXIF data with library metadata
                exif = img_rgb.getexif()
                if exif is None:
                    from PIL.Image import Exif
                    exif = Exif()

                # EXIF UserComment tag (0x9286) - store as JSON for easy parsing
                import json
                metadata_json = json.dumps({
                    "simposter_library_id": str(req.library_id or ""),
                    "simposter_library_name": str(library_label or ""),
                    "simposter_movie_title": str(movie_details.get("title", "")),
                    "simposter_movie_year": str(movie_details.get("year", "")),
                    "simposter_rating_key": str(rating_key or ""),
                    "simposter_is_tv": "0",
                })
                exif[0x9286] = metadata_json.encode('utf-8')  # UserComment field
                exif_bytes = exif.tobytes()
                img_rgb.save(save_path, "JPEG", quality=fmt_settings["quality"], exif=exif_bytes, subsampling=0)

            logger.info(f"[BATCH] Saved locally: {save_path} (library: {library_label})")
            # Record history entry for local save
            try:
                db.record_poster_history(
                    rating_key=rating_key,
                    library_id=str(req.library_id or ""),
                    title=movie_details.get("title"),
                    year=movie_details.get("year"),
                    template_id=template_id,
                    preset_id=preset_id,
                    action="saved_local",
                    save_path=str(save_path),
                    source=source,
                    poster_fallback_used=poster_fallback_action_used == "template",
                    poster_fallback_template=poster_fallback_template_used,
                    poster_fallback_preset=poster_fallback_preset_used,
                    logo_fallback_used=logo_fallback_used,
                    logo_fallback_template=logo_fallback_template_used,
                    logo_fallback_preset=logo_fallback_preset_used,
                )
            except Exception as history_err:
                logger.debug(f"[BATCH] Failed to record history for local save: {history_err}")

        # ---------------------------
        # Upload to Plex (if requested)
        # ---------------------------
        payload = None
        # Defaults to the raw source URL (today's existing behavior for the DB's cached
        # logo_url); upgraded to a locally-cached URL further below if a logo actually
        # gets uploaded to Plex this run. Must be set unconditionally here since it's
        # read unconditionally at the bottom of this function, regardless of whether
        # a Plex send even happens this run.
        logo_url_for_cache = logo_url
        if skip_send_not_ideal:
            logger.info("[BATCH] Skipping Plex upload for %s [%s] — still needs_retry and send_only_if_ideal is set", rating_key, title_hint)
        elif req.send_to_plex:
            _update_batch_status({
                "current_step": "Sending to Plex",
            })
            # PNG when the user's output format is PNG (lossless, matches a manual
            # Plex upload of the saved file), otherwise a high-quality JPEG.
            from .save import encode_poster_for_plex
            payload, content_type = encode_poster_for_plex(img)

            plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": content_type,
            }

            r = plex_session.post(plex_url, headers=headers, data=payload, timeout=20)
            r.raise_for_status()
            try:
                cache_ctx = SaveContext(
                    media_type="movie",
                    title=movie_details.get("title", rating_key),
                    year=int(movie_details["year"]) if movie_details.get("year") else None,
                    rating_key=rating_key,
                    library_label=resolve_library_label(req.library_id),
                    folder_name=_get_movie_folder_name_once() if save_to_asset_folder_on_send_enabled() else None,
                )
            except Exception:
                cache_ctx = None
            save_or_cache_render(rating_key, payload, cache_ctx)

            # Manual batch send resolves any pending retry for this item
            if source == "batch":
                try:
                    db.remove_from_retry_queue(rating_key)
                except Exception:
                    pass

            # Label removal
            if req.labels:
                logger.info("[BATCH] Removing labels %s from %s [%s]", req.labels, rating_key, title_hint)
                removed_labels = []
                try:
                    for label in req.labels:
                        # This function is movie-only — content_type is always "1", so
                        # skip plex_remove_label()'s own metadata fetch to determine it.
                        plex_remove_label(rating_key, label, content_type="1")
                        logger.info("[BATCH] Removed label '%s' from %s [%s]", label, rating_key, title_hint)
                        removed_labels.append(label.lower())
                except Exception as label_err:
                    logger.warning("[BATCH] Label removal failed for %s [%s]: %s", rating_key, title_hint, label_err)
                # Sync label cache — strip removed labels so the filter doesn't show stale results
                if removed_labels:
                    current = db.get_movie_labels(rating_key)
                    updated = [l for l in current if l.lower() not in removed_labels]
                    db.update_movie_labels(rating_key, updated)

            # Add tracking label if configured (opposite direction from the removal above —
            # see get_label_to_add()'s docstring)
            label_to_add = get_label_to_add()
            if label_to_add:
                try:
                    plex_add_label(rating_key, label_to_add, content_type="1")
                    logger.info("[BATCH] Added label '%s' to %s [%s]", label_to_add, rating_key, title_hint)
                    current = db.get_movie_labels(rating_key)
                    if label_to_add.lower() not in [l.lower() for l in current]:
                        db.update_movie_labels(rating_key, current + [label_to_add])
                except Exception as label_err:
                    logger.warning("[BATCH] Label add failed for %s [%s]: %s", rating_key, title_hint, label_err)

            logger.info("[BATCH] Uploaded to Plex: %s [%s]", rating_key, title_hint)

            # Send logo to Plex if requested and a logo was used
            logger.info("[BATCH] Logo upload check: send_logos_to_plex=%s logo_url=%s rating_key=%s [%s]",
                        getattr(req, 'send_logos_to_plex', False), bool(logo_url), rating_key, title_hint)
            if getattr(req, 'send_logos_to_plex', False) and logo_url:
                try:
                    logo_r = requests.get(logo_url, timeout=10)
                    if logo_r.status_code == 200:
                        ct = logo_r.headers.get("content-type", "image/png").split(";")[0].strip()
                        logo_bytes, ct = normalize_logo_for_plex(logo_r.content, ct)
                        plex_logo_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/clearLogos"
                        logo_hdrs = {"X-Plex-Token": settings.PLEX_TOKEN, "Content-Type": ct}
                        plex_session.post(plex_logo_url, headers=logo_hdrs, data=logo_bytes, timeout=20)
                        logger.info("[BATCH] Uploaded logo to Plex for %s [%s]", rating_key, title_hint)
                        # Cache the just-uploaded bytes locally and point the DB's cached
                        # logo_url at that copy (served via /api/logo/{rating_key}) instead of
                        # the raw external TMDb/Fanart source below -- matches the safe pattern
                        # plexsend.py's dedicated send-logo endpoint already uses. Re-fetching
                        # from Plex right now would be unsafe (Plex may not have processed the
                        # upload yet), so this reuses the bytes already in hand. Without this,
                        # the Logos tab (LogosView.vue) depends on the external host staying
                        # reachable indefinitely for every batch-sent logo — see CLAUDE.md
                        # Quirk #29 for the class of failure ("tile shows up blank") this invites.
                        from .movies import _save_logo_cache, _logo_cache_url
                        cached_logo_path = _save_logo_cache(rating_key, logo_bytes, ct)
                        if cached_logo_path:
                            logo_url_for_cache = _logo_cache_url(rating_key, cached_logo_path)
                    else:
                        logger.warning("[BATCH] Logo fetch returned %s for %s [%s] — skipping clearLogo upload", logo_r.status_code, rating_key, title_hint)
                except Exception as logo_err:
                    logger.warning("[BATCH] Logo send to Plex failed for %s [%s]: %s", rating_key, title_hint, logo_err)

            try:
                db.record_poster_history(
                    rating_key=rating_key,
                    library_id=str(req.library_id or ""),
                    title=movie_details.get("title"),
                    year=movie_details.get("year"),
                    template_id=template_id,
                    preset_id=preset_id,
                    action="sent_to_plex",
                    save_path=str(save_path) if save_path else None,
                    source=source,
                    poster_fallback_used=poster_fallback_action_used == "template",
                    poster_fallback_template=poster_fallback_template_used,
                    poster_fallback_preset=poster_fallback_preset_used,
                    logo_fallback_used=logo_fallback_used,
                    logo_fallback_template=logo_fallback_template_used,
                    logo_fallback_preset=logo_fallback_preset_used,
                    poster_data=payload,  # Save thumbnail for history preview
                )
            except Exception as history_err:
                logger.debug(f"[BATCH] Failed to record history for plex send: {history_err}")

        # Refresh cached poster from Plex so UI sees the new image
        try:
            fetch_and_cache_poster(rating_key, force_refresh=True)
        except Exception as cache_err:
            logger.debug("[BATCH] Failed to refresh poster cache for %s [%s]: %s", rating_key, title_hint, cache_err)

        try:
            db.update_movie_logo_url(rating_key, logo_url_for_cache)
        except Exception as logo_cache_err:
            logger.debug("[BATCH] Failed to cache logo_url for %s [%s]: %s", rating_key, title_hint, logo_cache_err)

        logger.info("[BATCH] '%s' done in %.1fs (rating_key=%s)", title_hint, time.time() - _item_start, rating_key)

        result = {
            "rating_key": rating_key,
            "title": movie_details.get("title", ""),
            "poster_used": poster_url,
            "logo_used": logo_url,
            "status": "ok",
            "poster_fallback": poster_fallback_action_used == "template",
            "logo_fallback": logo_fallback_used,
            "needs_retry": needs_retry,
            "retry_reason": (
                "no_logo_and_poster_fallback" if (logo_was_expected and logo_url is None and poster_fallback_action_used == "template")
                else "no_logo" if (logo_was_expected and logo_url is None)
                else "poster_fallback" if poster_fallback_action_used == "template"
                else "logo_fallback" if logo_fallback_used
                else None
            ),
        }
        if save_path:
            result["save_path"] = str(save_path)
        # Include poster bytes for single-item notifications (webhook, auto_generate)
        if source in ("webhook", "auto_generate") and req.send_to_plex and payload:
            result["poster_data"] = payload

        _update_batch_status({
            "current_step": "Complete",
        })

        return result

    except Exception as e:
        logger.error("[BATCH] Error for %s (%s): %s", title_hint, rating_key, e)
        # A failure this early (e.g. "No TMDb ID found") means title_hint never
        # advanced past the raw rating_key. That's usually recoverable — the last
        # library scan's movie_cache already has Plex's own title/year for this
        # item, independent of any TMDb match, so History can show a real title
        # instead of an opaque "(rating key N)" the user has to look up by hand.
        display_title = title_hint
        if display_title == rating_key:
            cached_title, _ = db.get_title_for_rating_key(rating_key)
            display_title = cached_title or f"(rating key {rating_key})"
        try:
            db.record_poster_history(
                rating_key=rating_key,
                library_id=str(req.library_id or ""),
                title=display_title,
                year=None,
                template_id=req.template_id,
                preset_id=req.preset_id,
                action="failed",
                source=source,
                status="failed",
                error_message=str(e),
            )
        except Exception:
            pass
        return {
            "rating_key": rating_key,
            "title": display_title if display_title != f"(rating key {rating_key})" else "",
            "status": "error",
            "error": str(e),
            "poster_fallback": False,
            "logo_fallback": False,
        }


def _process_single_tv_show(
    idx: int,
    rating_key: str,
    req: Union[BatchRequest, TVShowBatchRequest],
    base_options: dict,
    base_poster_filter: str,
    base_logo_preference: str,
    base_logo_mode: str,
    white_logo_fallback: str,
    language_pref: str,
    presets_data: dict,
    season_poster_filter: Optional[str] = None,
    season_options: Optional[dict] = None,
    source: str = "batch",
    affected_seasons: Optional[List[int]] = None,
):
    """Process a single TV show in the batch. Returns result dict.

    Args:
        affected_seasons: If provided, only process these specific season numbers.
                         Used by webhooks to only generate posters for newly added seasons.
                         If None or empty, process all seasons.
    """
    # Best-effort display title, upgraded to the real TMDb show name below once
    # fetched — a cheap local DB cache lookup (tv_cache, from the last library scan)
    # so even the very first "Start" log line can show a name instead of just a
    # rating_key.
    title_hint = rating_key
    try:
        _cached_title, _ = db.get_title_for_rating_key(rating_key)
        if _cached_title:
            title_hint = _cached_title
    except Exception:
        pass
    try:
        template_id = req.template_id
        preset_id = req.preset_id
        render_options_base = dict(base_options)
        poster_filter = base_poster_filter
        logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or base_logo_preference
        logo_preference = map_logo_mode_to_preference(logo_preference)
        logo_mode = base_logo_mode

        # For TV show season rendering, use season-specific options if available, merged on
        # top of the series options so a sparse season-preset diff resolves to a complete set.
        season_poster_filter_final = season_poster_filter or base_poster_filter
        season_options_final = db.resolve_season_options(base_options, season_options)

        logger.info("[BATCH TV] Start rating_key=%s [%s] template=%s include_seasons=%s season_poster_filter=%s",
                    rating_key, title_hint, template_id, req.include_seasons, season_poster_filter_final)

        # Fetch TV show TMDB/TVDB IDs from Plex
        _update_batch_status({
            "current_movie": rating_key,
            "current_step": "Fetching TV show metadata",
        })

        url = f"{settings.PLEX_URL}/library/metadata/{rating_key}"
        try:
            r = plex_session.get(url, headers=plex_headers(), timeout=6)
            r.raise_for_status()
        except Exception as e:
            raise Exception(f"Failed to fetch TV show metadata: {e}")

        tmdb_id = extract_tmdb_id_from_metadata(r.text)
        tvdb_id = extract_tvdb_id_from_metadata(r.text)

        # Piggyback: cache media info from the same response
        try:
            from ..config import extract_media_info_from_metadata
            media_info = extract_media_info_from_metadata(r.text)
            if media_info:
                db.update_tv_media_info(
                    rating_key,
                    media_info.get("video_resolution"),
                    media_info.get("audio_codec"),
                    media_info.get("audio_channels"),
                    video_codec=media_info.get("video_codec"),
                    audio_language=media_info.get("audio_language"),
                    edition=media_info.get("edition"),
                )
        except Exception:
            pass  # Non-critical

        if tmdb_id and not tvdb_id:
            try:
                external_ids = get_tv_external_ids(tmdb_id)
                tvdb_id = external_ids.get("tvdb_id") or external_ids.get("id")
            except Exception:
                pass

        if not tmdb_id:
            raise Exception("No TMDB ID found for TV show")

        logger.debug("[BATCH TV] rating_key=%s [%s] tmdb_id=%s tvdb_id=%s", rating_key, title_hint, tmdb_id, tvdb_id)

        # Fetch TV show details
        show_details = get_tv_show_details(tmdb_id)
        show_title = show_details.get("name") or title_hint
        title_hint = show_title

        include_series = getattr(req, 'include_series', True)

        # Neither type selected — nothing to do
        if not req.include_seasons and not include_series:
            return {
                "rating_key": rating_key,
                "show_title": show_details.get("name", ""),
                "status": "skipped",
                "reason": "No poster types selected (include_series=False, include_seasons=False)",
                "poster_fallback": False,
                "logo_fallback": False,
            }

        if not req.include_seasons:
            # Series poster only
            return _render_tv_series_poster(
                rating_key, tmdb_id, tvdb_id, show_details, template_id, preset_id,
                render_options_base, poster_filter, logo_preference, logo_mode,
                white_logo_fallback, language_pref, req,
                source=source
            )
        else:
            # Season posters (and optionally series poster)
            return _render_all_tv_seasons(
                rating_key, tmdb_id, tvdb_id, show_details, template_id, preset_id,
                render_options_base, poster_filter, logo_preference, logo_mode,
                white_logo_fallback, language_pref, req,
                season_poster_filter_final, season_options_final,
                source=source,
                affected_seasons=affected_seasons,
                include_series=include_series,
            )

    except Exception as e:
        logger.error("[BATCH TV] Error for %s (%s): %s", title_hint, rating_key, e)
        # See the matching comment in _process_single_movie's except block: fall
        # back to tv_cache's own Plex title (from the last scan) before the
        # opaque "(rating key N)" placeholder.
        display_title = title_hint
        if display_title == rating_key:
            cached_title, _ = db.get_title_for_rating_key(rating_key)
            display_title = cached_title or f"(rating key {rating_key})"
        try:
            db.record_poster_history(
                rating_key=rating_key,
                library_id=str(req.library_id or ""),
                title=display_title,
                year=None,
                template_id=req.template_id,
                preset_id=req.preset_id,
                action="failed",
                source=source,
                status="failed",
                error_message=str(e),
            )
        except Exception:
            pass
        return {
            "rating_key": rating_key,
            "show_title": display_title if display_title != f"(rating key {rating_key})" else "",
            "status": "error",
            "error": str(e),
            "poster_fallback": False,
            "logo_fallback": False,
        }


def _render_tv_series_poster(
    rating_key: str,
    tmdb_id: int,
    tvdb_id: Optional[int],
    show_details: dict,
    template_id: str,
    preset_id: Optional[str],
    render_options: dict,
    poster_filter: str,
    logo_preference: str,
    logo_mode: str,
    white_logo_fallback: str,
    language_pref: str,
    req: Union[BatchRequest, TVShowBatchRequest],
    source: str = "batch",
):
    """Render series-level poster for a TV show."""
    _update_batch_status({
        "current_movie": show_details.get("name", rating_key),
        "current_step": "Fetching series images",
    })

    # Get series-level images
    show_imgs = get_images_for_tv_show(tmdb_id, show_details.get("original_language"))
    posters = show_imgs.get("posters", [])
    logos = show_imgs.get("logos", [])

    # Merge with TVDB/Fanart if available
    if tvdb_id:
        try:
            if settings.TVDB_API_KEY:
                tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                posters.extend(tvdb_imgs.get("posters", []))
                logos.extend(tvdb_imgs.get("logos", []))
        except Exception as e:
            logger.warning("[BATCH TV] TVDB series fetch failed: %s", e)

        try:
            if settings.FANART_API_KEY:
                fanart_imgs = fanart_client.get_images_for_tv_show(int(tvdb_id))
                logos.extend(fanart_imgs.get("logos", []))
        except Exception as e:
            logger.warning("[BATCH TV] Fanart series fetch failed: %s", e)

    logger.debug("[BATCH TV] Series posters=%d logos=%d filter=%s", len(posters), len(logos), poster_filter)

    _update_batch_status({
        "current_step": "Selecting assets",
    })

    # Track fallback usage
    poster_fallback_used = False
    poster_fallback_template_used = None
    poster_fallback_preset_used = None

    # Select poster with template fallback logic (matching preview.py behavior)
    poster = pick_poster(posters, poster_filter)

    if not poster:
        # Apply template fallback if no poster found with filter
        fallback_action = render_options.get("fallbackPosterAction") or req.fallbackPosterAction or "continue"
        fallback_template = render_options.get("fallbackPosterTemplate") or req.fallbackPosterTemplate
        fallback_preset = render_options.get("fallbackPosterPreset") or req.fallbackPosterPreset

        if fallback_action == "skip":
            # Skip action - do not render this series
            logger.info("[BATCH TV] Skipping series poster (fallbackPosterAction=skip, no poster found with filter)")
            return {
                "rating_key": rating_key,
                "status": "skipped",
                "reason": "No poster found with filter, fallback action is skip",
                "poster_fallback": False,
                "logo_fallback": False,
            }
        elif fallback_action == "template" and fallback_template:
            poster_fallback_used = True
            poster_fallback_template_used = fallback_template
            poster_fallback_preset_used = fallback_preset
            logger.info("[BATCH TV] Applying template fallback: %s/%s", fallback_template, fallback_preset)
            # Load fallback preset and merge options
            from ..config import load_presets
            presets_data = load_presets()
            tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
            fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None) if fallback_preset else None
            if fpreset:
                fp_opts = fpreset.get("options", {})
                render_options = {**render_options, **fp_opts}
                template_id = fallback_template
                preset_id = fallback_preset
                # Now try to get ANY available poster
                poster = pick_poster(posters, "all")
                logger.info("[BATCH TV] Using fallback poster from TMDB after template switch")
            else:
                logger.warning("[BATCH TV] Fallback preset '%s' not found for template '%s'", fallback_preset, fallback_template)
        else:
            # continue action - try to get any available poster
            poster = pick_poster(posters, "all")

    if not poster:
        raise Exception("No poster found for series")

    logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference, white_logo_fallback, language_pref)

    poster_url = poster.get("url")
    logo_url = logo.get("url") if logo else None

    # Render the poster
    return _render_and_save_poster(
        rating_key, poster_url, logo_url, render_options, template_id, preset_id,
        show_details.get("name"), show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
        req, is_tv=True,
        poster_fallback_used=poster_fallback_used,
        poster_fallback_template=poster_fallback_template_used,
        poster_fallback_preset=poster_fallback_preset_used,
        source=source,
        tmdb_id=tmdb_id,
        logo_was_expected=str(logo_mode).lower() != "none",
    )


def _render_all_tv_seasons(
    rating_key: str,
    tmdb_id: int,
    tvdb_id: Optional[int],
    show_details: dict,
    template_id: str,
    preset_id: Optional[str],
    render_options: dict,
    poster_filter: str,
    logo_preference: str,
    logo_mode: str,
    white_logo_fallback: str,
    language_pref: str,
    req: Union[BatchRequest, TVShowBatchRequest],
    season_poster_filter: str = "all",
    season_options: Optional[dict] = None,
    source: str = "batch",
    affected_seasons: Optional[List[int]] = None,
    include_series: bool = True,
):
    """Render all seasons for a TV show.

    Args:
        affected_seasons: If provided, only process these specific season numbers.
                         Used by webhooks to only generate posters for newly added seasons.
                         If None or empty, process all seasons (batch mode).
    """
    _seasons_start = time.time()
    show_title = show_details.get("name", "Unknown")
    # Use season-specific options if provided, merged on top of the series options so a
    # season preset stored as a sparse diff (v1.6.32+) still resolves to a complete option set.
    final_season_options = db.resolve_season_options(render_options, season_options)

    # Fetch seasons from Plex
    url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/children"
    try:
        r = plex_session.get(url, headers=plex_headers(), timeout=6)
        r.raise_for_status()
    except Exception as e:
        raise Exception(f"Failed to fetch seasons: {e}")

    import xml.etree.ElementTree as ET
    root = ET.fromstring(r.text)
    seasons = []
    for directory in root.findall(".//Directory"):
        season_index = int(directory.get("index", -1))
        season_key = directory.get("ratingKey", "")
        season_title = directory.get("title", f"Season {season_index}")
        if season_index >= 0:
            seasons.append({
                "index": season_index,
                "key": season_key,
                "title": season_title
            })

    seasons.sort(key=lambda s: s["index"])
    logger.info("[BATCH TV] Found %d seasons for %s", len(seasons), show_title)

    # Filter seasons if affected_seasons is provided (webhook mode)
    # This prevents re-rendering all seasons when only one season has new episodes
    if affected_seasons:
        original_count = len(seasons)
        seasons = [s for s in seasons if s["index"] in affected_seasons]
        logger.info("[BATCH TV] Filtered to %d affected seasons from %d total: %s",
                    len(seasons), original_count, affected_seasons)

    # Get series-level logos (reused for all seasons)
    show_imgs = get_images_for_tv_show(tmdb_id, show_details.get("original_language"))
    series_logos = show_imgs.get("logos", [])
    series_posters = show_imgs.get("posters", [])

    if tvdb_id:
        try:
            if settings.TVDB_API_KEY:
                tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                series_logos.extend(tvdb_imgs.get("logos", []))
                series_posters.extend(tvdb_imgs.get("posters", []))
        except Exception:
            pass
        try:
            if settings.FANART_API_KEY:
                fanart_imgs = fanart_client.get_images_for_tv_show(int(tvdb_id))
                series_logos.extend(fanart_imgs.get("logos", []))
        except Exception:
            pass

    results = []

    # Render series poster only when:
    # - include_series is True (user opted in), AND
    # - not in webhook mode with affected_seasons (webhooks with affected_seasons target specific seasons only)
    should_render_series = include_series and not affected_seasons

    if should_render_series:
        # Render series poster first before processing seasons
        logger.info("[BATCH TV] Rendering series poster for %s before seasons", show_title)
        _update_batch_status({
            "current_movie": f"{show_title} - Series Poster",
            "current_step": "Rendering series poster",
        })

        try:
            # Select series poster with template fallback logic (matching _render_tv_series_poster)
            series_poster = pick_poster(series_posters, poster_filter)

            series_template_id = template_id
            series_preset_id = preset_id
            series_render_options = dict(render_options)

            # Track fallback usage for series
            series_poster_fallback_used = False
            series_poster_fallback_template = None
            series_poster_fallback_preset = None

            if not series_poster:
                # Apply template fallback if no poster found with filter
                fallback_action = render_options.get("fallbackPosterAction") or req.fallbackPosterAction or "continue"
                fallback_template = render_options.get("fallbackPosterTemplate") or req.fallbackPosterTemplate
                fallback_preset = render_options.get("fallbackPosterPreset") or req.fallbackPosterPreset

                if fallback_action == "skip":
                    # Skip action - do not render this item
                    logger.info("[BATCH TV] Skipping series poster (fallbackPosterAction=skip, no poster found with filter)")
                elif fallback_action == "template" and fallback_template:
                    series_poster_fallback_used = True
                    series_poster_fallback_template = fallback_template
                    series_poster_fallback_preset = fallback_preset
                    logger.info("[BATCH TV] Applying template fallback for series: %s/%s", fallback_template, fallback_preset)
                    # Load fallback preset and merge options
                    from ..config import load_presets
                    presets_data = load_presets()
                    tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
                    fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None) if fallback_preset else None
                    if fpreset:
                        fp_opts = fpreset.get("options", {})
                        series_render_options = {**render_options, **fp_opts}
                        series_template_id = fallback_template
                        series_preset_id = fallback_preset
                        # Now try to get ANY available poster
                        series_poster = pick_poster(series_posters, "all")
                        logger.info("[BATCH TV] Using fallback poster from TMDB after template switch")
                    else:
                        logger.warning("[BATCH TV] Fallback preset '%s' not found for template '%s'", fallback_preset, fallback_template)
                else:
                    # continue action - try to get any available poster
                    series_poster = pick_poster(series_posters, "all")

            if series_poster:
                # Select logo for series
                series_logo = None if str(logo_mode).lower() == "none" else pick_logo(series_logos, logo_preference, white_logo_fallback, language_pref)
                series_poster_url = series_poster.get("url")
                series_logo_url = series_logo.get("url") if series_logo else None

                # Render series poster with potentially updated template/preset from fallback
                series_result = _render_and_save_poster(
                    rating_key, series_poster_url, series_logo_url, series_render_options, series_template_id, series_preset_id,
                    show_title, show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
                    req, is_tv=True,
                    poster_fallback_used=series_poster_fallback_used,
                    poster_fallback_template=series_poster_fallback_template,
                    poster_fallback_preset=series_poster_fallback_preset,
                    source=source,
                    tmdb_id=tmdb_id,
                    logo_was_expected=str(logo_mode).lower() != "none",
                )
                results.append({
                    **series_result,
                    "season": "Series",
                    "is_series": True
                })
                logger.info("[BATCH TV] Series poster rendered successfully for %s", show_title)
            else:
                logger.warning("[BATCH TV] No series poster found for %s", show_title)
        except Exception as e:
            logger.error("[BATCH TV] Failed to render series poster for %s: %s", show_title, e)
            results.append({
                "rating_key": rating_key,
                "season": "Series",
                "is_series": True,
                "status": "error",
                "error": str(e),
                "poster_fallback": False,
                "logo_fallback": False,
            })
    else:
        # Webhook mode with affected_seasons - skip series poster
        logger.info("[BATCH TV] Skipping series poster for %s (webhook mode, affected_seasons=%s)", show_title, affected_seasons)
    
    # For webhook mode, check if we should skip seasons that already have posters
    skip_existing_seasons = False
    if source == "webhook":
        try:
            ui_settings = db.get_ui_settings()
            always_regen = (ui_settings or {}).get("automation", {}).get("webhookAlwaysRegenerateSeason", False)
            skip_existing_seasons = not always_regen
        except Exception:
            skip_existing_seasons = True  # Default: skip existing

    # Now process individual seasons
    for season in seasons:
        season_index = season["index"]
        season_key = season["key"]
        season_title = season["title"]

        # Skip season if poster already sent (webhook mode only)
        if skip_existing_seasons and db.has_poster_been_sent(season_key):
            logger.info("[BATCH TV] Season poster already sent for %s - %s (season_key=%s), skipping", show_title, season_title, season_key)
            results.append({
                "rating_key": season_key,
                "season": season_title,
                "status": "skipped_existing",
                "poster_fallback": False,
                "logo_fallback": False,
            })
            continue

        logger.info("[BATCH TV] Processing %s - %s", show_title, season_title)

        _update_batch_status({
            "current_movie": f"{show_title} - {season_title}",
            "current_step": "Fetching season images",
        })

        # Get season-specific images
        try:
            season_imgs = get_tv_season_images(tmdb_id, season_index, show_details.get("original_language"))
            season_posters = season_imgs.get("posters", [])
        except Exception as e:
            logger.warning("[BATCH TV] Failed to get TMDB season images for season %d: %s", season_index, e)
            season_posters = []

        if tvdb_id:
            try:
                if settings.TVDB_API_KEY:
                    tvdb_season_imgs = tvdb_client.get_season_images(int(tvdb_id), season_index)
                    season_posters.extend(tvdb_season_imgs.get("posters", []))
            except Exception:
                pass

        # Combine season + series posters for selection
        all_posters = season_posters + series_posters

        logger.debug("[BATCH TV] Season %d: posters=%d (season=%d series=%d) logos=%d filter=%s",
                    season_index, len(all_posters), len(season_posters), len(series_posters),
                    len(series_logos), season_poster_filter)

        # Select poster with template fallback logic (matching preview.py behavior)
        poster = pick_poster(all_posters, season_poster_filter)

        season_template_id = template_id
        season_preset_id = preset_id
        season_render_options = dict(final_season_options)

        # Track fallback usage for season
        season_poster_fallback_used = False
        season_poster_fallback_template = None
        season_poster_fallback_preset = None

        if not poster:
            # Apply template fallback if no poster found with filter
            fallback_action = final_season_options.get("fallbackPosterAction") or req.fallbackPosterAction or "continue"
            fallback_template = final_season_options.get("fallbackPosterTemplate") or req.fallbackPosterTemplate
            fallback_preset = final_season_options.get("fallbackPosterPreset") or req.fallbackPosterPreset

            if fallback_action == "skip":
                # Skip action - do not render this season
                logger.info("[BATCH TV] Skipping %s (fallbackPosterAction=skip, no poster found with filter)", season_title)
            elif fallback_action == "template" and fallback_template:
                season_poster_fallback_used = True
                season_poster_fallback_template = fallback_template
                season_poster_fallback_preset = fallback_preset
                logger.info("[BATCH TV] Applying template fallback for season %s: %s/%s", season_title, fallback_template, fallback_preset)
                # Load fallback preset and merge options
                from ..config import load_presets
                presets_data = load_presets()
                tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
                fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None) if fallback_preset else None
                if fpreset:
                    # Use the fallback preset's season options, resolved against its own base
                    # options (season_options may be stored as a sparse diff, not a full copy).
                    fp_opts = db.resolve_season_options(fpreset.get("options", {}), fpreset.get("season_options", {}))
                    season_render_options = {**final_season_options, **fp_opts}
                    season_template_id = fallback_template
                    season_preset_id = fallback_preset
                    # Now try to get ANY available poster
                    poster = pick_poster(all_posters, "all")
                    logger.info("[BATCH TV] Using fallback poster from TMDB after template switch")
                else:
                    logger.warning("[BATCH TV] Fallback preset '%s' not found for template '%s'", fallback_preset, fallback_template)
            else:
                # continue action - try to get any available poster
                poster = pick_poster(all_posters, "all")

        if not poster:
            logger.warning("[BATCH TV] No poster found for %s - %s, skipping", show_title, season_title)
            results.append({
                "rating_key": season_key,
                "season": season_title,
                "status": "skipped_no_poster",
                "poster_fallback": False,
                "logo_fallback": False,
            })
            continue

        # Extract logo mode from season options (may differ from series logo mode)
        season_logo_mode = season_render_options.get("logo_mode", logo_mode)
        season_logo_preference = season_render_options.get("logo_preference") or season_logo_mode or logo_preference
        season_logo_preference = map_logo_mode_to_preference(season_logo_preference)

        # Select logo using season-specific logo mode
        logo = None if str(season_logo_mode).lower() == "none" else pick_logo(series_logos, season_logo_preference, white_logo_fallback, language_pref)

        poster_url = poster.get("url")
        logo_url = logo.get("url") if logo else None

        # Add season_text/season_number to season-specific options
        season_render_options["season_text"] = season_title
        season_render_options["season_number"] = str(season_index) if season_index is not None else ""

        # Render the poster with potentially updated template/preset from fallback
        result = _render_and_save_poster(
            season_key, poster_url, logo_url, season_render_options, season_template_id, season_preset_id,
            show_title, show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
            req, is_tv=True, season_title=season_title, season_index=season_index,
            poster_fallback_used=season_poster_fallback_used,
            poster_fallback_template=season_poster_fallback_template,
            poster_fallback_preset=season_poster_fallback_preset,
            source=source,
            tmdb_id=tmdb_id,
            logo_was_expected=str(season_logo_mode).lower() != "none",
        )
        results.append(result)

    logger.info("[BATCH TV] '%s' done in %.1fs (rating_key=%s, %d season(s))",
                show_title, time.time() - _seasons_start, rating_key, len(results))

    return {
        "rating_key": rating_key,
        "show_title": show_title,
        "status": "ok",
        "seasons_processed": len(results),
        "results": results
    }


def _render_and_save_poster(
    rating_key: str,
    poster_url: str,
    logo_url: Optional[str],
    render_options: dict,
    template_id: str,
    preset_id: Optional[str],
    title: str,
    year: Optional[str],
    req: Union[BatchRequest, MovieBatchRequest, TVShowBatchRequest],
    is_tv: bool = False,
    season_title: Optional[str] = None,
    season_index: Optional[int] = None,
    poster_fallback_used: bool = False,
    poster_fallback_template: Optional[str] = None,
    poster_fallback_preset: Optional[str] = None,
    logo_fallback_used: bool = False,
    logo_fallback_template: Optional[str] = None,
    logo_fallback_preset: Optional[str] = None,
    source: str = "batch",
    tmdb_id: Optional[int] = None,
    logo_was_expected: bool = True,
):
    """Common rendering and saving logic for both movies and TV shows."""
    _render_start = time.time()
    # Create a combined display title for history (e.g., "Show Name - Season 1" for TV seasons)
    display_title = f"{title} - {season_title}" if season_title else title

    # Lazy, memoized {folder} lookup -- shares one Plex metadata fetch between the
    # save_locally and send_to_plex blocks below instead of firing it twice per item.
    # TV: show-level only (season_title is None) -- a show's folder is fetched by
    # walking up from an episode's file path, so resolving it once per show is
    # enough; per-season resolution would mean N redundant Plex fetches per show
    # (episodes always live under the same one show folder either way). Season
    # posters keep falling back to {title}, matching the existing documented
    # behavior (see OutputTab.vue's "{folder} ... show-level only, not individual
    # seasons" copy).
    _folder_name_cache: list = []

    def _get_movie_folder_name_once() -> Optional[str]:
        if is_tv and season_title is not None:
            return None
        if not _folder_name_cache:
            _folder_name_cache.append(get_media_folder_name(rating_key, is_tv))
        return _folder_name_cache[0]

    needs_retry = (logo_was_expected and logo_url is None) or poster_fallback_used or logo_fallback_used
    # Retry-queue runs only want to upload once the render actually meets the template spec
    skip_send_not_ideal = getattr(req, 'send_only_if_ideal', False) and needs_retry

    # Inject Plex media metadata for overlay badges
    from ..config import get_plex_media_info
    plex_media = get_plex_media_info(rating_key)
    if plex_media:
        existing_meta = render_options.get("metadata") or {}
        render_options["metadata"] = {**existing_meta, **plex_media}

    # Inject tmdb_id and media_type for streaming platform badge resolution
    if tmdb_id:
        render_options.setdefault("metadata", {})
        render_options["metadata"]["tmdb_id"] = tmdb_id
        render_options["metadata"]["media_type"] = "tv" if is_tv else "movie"

    # Pass preset_id so the template renderer can look up linked overlay configs
    if preset_id:
        render_options["preset_id"] = preset_id

    _update_batch_status({
        "current_step": "Rendering poster",
    })

    # Check if overlay caching is enabled
    ui_settings = db.get_ui_settings()
    use_overlay_cache = ui_settings.get("performance", {}).get("useOverlayCache", True)

    # Use overlay cache rendering (takes URLs directly)
    rendered = render_with_overlay_cache(
        template_id,
        preset_id,
        poster_url,
        logo_url,
        render_options,
        use_cache=use_overlay_cache
    )

    # Save locally if requested
    save_path = None
    if req.save_locally:
        _update_batch_status({
            "current_step": "Saving to disk",
        })

        try:
            media_type = "tv-show" if is_tv else "movie"
            library_label = resolve_library_label(req.library_id) if req.library_id else ""
            from .save import get_output_format_settings
            fmt_settings = get_output_format_settings()

            ctx = SaveContext(
                media_type=media_type,
                title=title,
                year=int(year) if year else None,
                rating_key=rating_key,
                library_label=library_label,
                season=season_index if is_tv else None,
                folder_name=_get_movie_folder_name_once(),
            )
            save_path = resolve_save_path(ctx, fmt_settings["ext"], batch_subfolder=req.batch_subfolder)
            save_path.parent.mkdir(parents=True, exist_ok=True)

            # Embed library metadata into the image
            rendered = embed_library_metadata(
                rendered,
                req.library_id,
                library_label,
                title,
                str(year) if year else None
            )

            # Save in the user's preferred format
            pil_format = fmt_settings["pil_format"]

            if pil_format == "PNG":
                pnginfo = PngImagePlugin.PngInfo()
                pnginfo.add_text("simposter_library_id", str(req.library_id or ""))
                pnginfo.add_text("simposter_library_name", library_label or "")
                if title:
                    pnginfo.add_text("simposter_movie_title", title)
                if year:
                    pnginfo.add_text("simposter_movie_year", str(year))
                if template_id:
                    pnginfo.add_text("simposter_template_id", template_id)
                if preset_id:
                    pnginfo.add_text("simposter_preset_id", preset_id)
                pnginfo.add_text("simposter_rating_key", str(rating_key or ""))
                pnginfo.add_text("simposter_is_tv", "1" if is_tv else "0")
                rendered.save(str(save_path), "PNG", pnginfo=pnginfo, optimize=False, compress_level=fmt_settings["quality"])
            elif pil_format == "WEBP":
                rendered.convert("RGB").save(str(save_path), "WEBP", quality=fmt_settings["quality"])
            else:
                # For JPEG, embed metadata in EXIF UserComment field (matching the PNG
                # branch above — this was previously missing, so JPEG-format TV/season
                # local assets had no embedded metadata at all: no library, title, or
                # rating_key, which also broke Local Assets library-filtering for them).
                import json
                rendered_rgb = rendered.convert("RGB")
                exif = rendered_rgb.getexif()
                if exif is None:
                    from PIL.Image import Exif
                    exif = Exif()
                metadata_json = json.dumps({
                    "simposter_library_id": str(req.library_id or ""),
                    "simposter_library_name": library_label or "",
                    "simposter_movie_title": title or "",
                    "simposter_movie_year": str(year) if year else "",
                    "simposter_rating_key": str(rating_key or ""),
                    "simposter_is_tv": "1" if is_tv else "0",
                })
                exif[0x9286] = metadata_json.encode('utf-8')
                rendered_rgb.save(str(save_path), "JPEG", quality=fmt_settings["quality"], exif=exif.tobytes(), subsampling=0)
            logger.info("[BATCH] Saved %s to: %s", title, save_path)

            # Record history
            try:
                db.record_poster_history(
                    rating_key=rating_key,
                    library_id=str(req.library_id or ""),
                    title=display_title,
                    year=year,
                    template_id=template_id,
                    preset_id=preset_id,
                    action="saved_local",
                    save_path=str(save_path),
                    source=source,
                    poster_fallback_used=poster_fallback_used,
                    poster_fallback_template=poster_fallback_template,
                    poster_fallback_preset=poster_fallback_preset,
                    logo_fallback_used=logo_fallback_used,
                    logo_fallback_template=logo_fallback_template,
                    logo_fallback_preset=logo_fallback_preset,
                )
            except Exception:
                pass
        except Exception as save_err:
            logger.error("[BATCH] Save error for %s: %s", display_title, save_err)

    # Send to Plex if requested
    payload = None
    # Defaults to the raw source URL (today's existing behavior for the DB's cached
    # logo_url); upgraded to a locally-cached URL further below if a logo actually
    # gets uploaded to Plex this run. Must be set unconditionally here since it's
    # read unconditionally at the bottom of this function, regardless of whether
    # a Plex send even happens this run.
    logo_url_for_cache = logo_url
    if skip_send_not_ideal:
        logger.info("[BATCH] Skipping Plex upload for %s — still needs_retry and send_only_if_ideal is set", display_title)
    elif req.send_to_plex:
        _update_batch_status({
            "current_step": "Uploading to Plex",
        })

        # PNG when the user's output format is PNG (lossless, matches a manual Plex
        # upload of the saved file), otherwise a high-quality JPEG.
        from .save import encode_poster_for_plex
        payload, content_type = encode_poster_for_plex(rendered)

        try:
            upload_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": content_type,
            }
            upload_resp = plex_session.post(upload_url, headers=headers, data=payload, timeout=20)
            upload_resp.raise_for_status()
            logger.info("[BATCH] Uploaded poster to Plex for %s", title)
            try:
                cache_ctx = SaveContext(
                    media_type="tv-show" if is_tv else "movie",
                    title=title,
                    year=int(year) if year else None,
                    rating_key=rating_key,
                    library_label=resolve_library_label(req.library_id) if req.library_id else "",
                    season=season_index if is_tv else None,
                    folder_name=_get_movie_folder_name_once() if save_to_asset_folder_on_send_enabled() else None,
                )
            except Exception:
                cache_ctx = None
            save_or_cache_render(rating_key, payload, cache_ctx)

            # Manual batch send resolves any pending retry for this item
            if source == "batch":
                try:
                    db.remove_from_retry_queue(rating_key)
                except Exception:
                    pass

            # Send logo to Plex if requested and a logo was used
            logger.info("[BATCH] Logo upload check: send_logos_to_plex=%s logo_url=%s rating_key=%s [%s]",
                        getattr(req, 'send_logos_to_plex', False), bool(logo_url), rating_key, display_title)
            if getattr(req, 'send_logos_to_plex', False) and logo_url:
                try:
                    logo_r = requests.get(logo_url, timeout=10)
                    if logo_r.status_code == 200:
                        ct = logo_r.headers.get("content-type", "image/png").split(";")[0].strip()
                        logo_bytes, ct = normalize_logo_for_plex(logo_r.content, ct)
                        plex_logo_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/clearLogos"
                        logo_hdrs = {"X-Plex-Token": settings.PLEX_TOKEN, "Content-Type": ct}
                        plex_session.post(plex_logo_url, headers=logo_hdrs, data=logo_bytes, timeout=20)
                        logger.info("[BATCH] Uploaded logo to Plex for %s [%s]", rating_key, display_title)
                        # Cache the just-uploaded bytes locally instead of caching the raw
                        # external TMDb/Fanart URL below -- see the matching comment in
                        # _process_single_movie() and CLAUDE.md Quirk #29 for why. The logo
                        # disk cache is shared and media-type-agnostic (keyed by rating_key,
                        # which is unique across the whole Plex server), so this always comes
                        # from movies.py even for TV/season items -- tv_shows.py has no logo
                        # cache functions of its own (the scan path for TV shows already
                        # reuses movies.py's fetch_and_cache_logo() the same way).
                        from .movies import _save_logo_cache, _logo_cache_url
                        cached_logo_path = _save_logo_cache(rating_key, logo_bytes, ct)
                        if cached_logo_path:
                            logo_url_for_cache = _logo_cache_url(rating_key, cached_logo_path)
                    else:
                        logger.warning("[BATCH] Logo fetch returned %s for %s [%s] — skipping clearLogo upload", logo_r.status_code, rating_key, display_title)
                except Exception as logo_err:
                    logger.warning("[BATCH] Logo send to Plex failed for %s [%s]: %s", rating_key, display_title, logo_err)

            # Invalidate poster cache so UI shows updated poster
            if is_tv:
                from .tv_shows import _remove_poster_cache as _remove_tv_poster_cache
                _remove_tv_poster_cache(rating_key, "tv")
                logger.info("[BATCH] Invalidated TV poster cache for %s [%s]", rating_key, display_title)
            else:
                from .movies import _remove_poster_cache as _remove_movie_poster_cache
                _remove_movie_poster_cache(rating_key)
                logger.info("[BATCH] Invalidated movie poster cache for %s [%s]", rating_key, display_title)

            # Remove labels if specified
            if req.labels:
                logger.info("[BATCH] Removing labels %s from %s (%s)", req.labels, rating_key, display_title)
                removed_labels = []
                try:
                    for label_name in req.labels:
                        plex_remove_label(rating_key, label_name)
                        logger.info("[BATCH] Removed label '%s' from %s [%s]", label_name, rating_key, display_title)
                        removed_labels.append(label_name.lower())
                except Exception as label_err:
                    logger.warning("[BATCH] Label removal failed for %s [%s]: %s", rating_key, display_title, label_err)
                # Sync label cache — strip removed labels so the filter doesn't show stale results
                if removed_labels:
                    current = db.get_tv_labels(rating_key)
                    updated = [l for l in current if l.lower() not in removed_labels]
                    db.update_tv_labels(rating_key, updated, library_id=req.library_id or "default")

            # Add tracking label if configured (opposite direction from the removal above —
            # see get_label_to_add()'s docstring)
            label_to_add = get_label_to_add()
            if label_to_add:
                try:
                    plex_add_label(rating_key, label_to_add)
                    logger.info("[BATCH] Added label '%s' to %s [%s]", label_to_add, rating_key, display_title)
                    current = db.get_tv_labels(rating_key)
                    if label_to_add.lower() not in [l.lower() for l in current]:
                        db.update_tv_labels(rating_key, current + [label_to_add], library_id=req.library_id or "default")
                except Exception as label_err:
                    logger.warning("[BATCH] Label add failed for %s [%s]: %s", rating_key, display_title, label_err)

            # Record history
            try:
                db.record_poster_history(
                    rating_key=rating_key,
                    library_id=str(req.library_id or ""),
                    title=display_title,
                    year=year,
                    template_id=template_id,
                    preset_id=preset_id,
                    action="sent_to_plex",
                    save_path=str(save_path) if save_path else None,
                    source=source,
                    poster_fallback_used=poster_fallback_used,
                    poster_fallback_template=poster_fallback_template,
                    poster_fallback_preset=poster_fallback_preset,
                    logo_fallback_used=logo_fallback_used,
                    logo_fallback_template=logo_fallback_template,
                    logo_fallback_preset=logo_fallback_preset,
                    poster_data=payload,  # Save thumbnail for history preview
                )
            except Exception:
                pass

        except Exception as upload_err:
            logger.error("[BATCH] Plex upload failed for %s: %s", display_title, upload_err)
            raise

    try:
        if is_tv:
            db.update_tv_logo_url(rating_key, logo_url_for_cache)
        else:
            db.update_movie_logo_url(rating_key, logo_url_for_cache)
    except Exception as logo_cache_err:
        logger.debug("[BATCH] Failed to cache logo_url for %s [%s]: %s", rating_key, display_title, logo_cache_err)

    logger.info("[BATCH] '%s' done in %.1fs (rating_key=%s)", display_title, time.time() - _render_start, rating_key)

    result = {
        "rating_key": rating_key,
        "poster_used": poster_url,
        "logo_used": logo_url,
        "status": "ok",
        "poster_fallback": poster_fallback_used,
        "logo_fallback": logo_fallback_used,
        "needs_retry": needs_retry,
        "retry_reason": (
            "no_logo_and_poster_fallback" if (logo_was_expected and logo_url is None and poster_fallback_used)
            else "no_logo" if (logo_was_expected and logo_url is None)
            else "poster_fallback" if poster_fallback_used
            else "logo_fallback" if logo_fallback_used
            else None
        ),
    }
    if season_title:
        result["season"] = season_title
    if save_path:
        result["save_path"] = str(save_path)
    # Include poster bytes for single-item notifications (webhook, auto_generate)
    if source in ("webhook", "auto_generate") and req.send_to_plex and payload:
        result["poster_data"] = payload

    return result


def _execute_batch(req: Union[BatchRequest, MovieBatchRequest, TVShowBatchRequest], is_tv_batch: bool):
    """
    Shared batch processing logic for both movies and TV shows.

    Args:
        req: The batch request containing all parameters
        is_tv_batch: True for TV shows (process seasons), False for movies
    """
    # Get concurrent renders setting and retry config
    retry_enabled = False
    save_batch_in_subfolder = False
    try:
        from .ui_settings import _read_settings
        ui_settings = _read_settings(include_env=False)
        max_workers = ui_settings.performance.concurrentRenders if ui_settings.performance else 2
        retry_enabled = ui_settings.automation.retryUntilTemplateMet if ui_settings.automation else False
        save_batch_in_subfolder = bool(ui_settings.saveBatchInSubfolder)
    except Exception:
        max_workers = 2  # Default to 2 concurrent renders

    # One timestamp for the whole run so every item (movies and TV alike) lands in the
    # same batch-<timestamp> folder, instead of a new folder per item.
    if req.save_locally and save_batch_in_subfolder:
        from ..save_paths import make_batch_subfolder_name
        req.batch_subfolder = make_batch_subfolder_name()

    results = []

    # Initialize batch status
    _update_batch_status({
        "state": "running",
        "total": len(req.rating_keys),
        "processed": 0,
        "current_movie": "",
        "current_step": "",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
        "error": None,
    })

    # Load preset options if provided
    presets_data = load_presets() or {}
    base_options = dict(req.options or {})
    base_poster_filter = base_options.get("poster_filter", "all")
    base_logo_mode = base_options.get("logo_mode", "first")
    base_logo_preference = base_options.get("logo_preference") or base_logo_mode or "first"
    base_logo_preference = map_logo_mode_to_preference(base_logo_preference)
    season_poster_filter = base_poster_filter  # Default to same as series
    season_options = dict(base_options)  # Default to same as series
    white_logo_fallback = db.get_setting("fallback.white_logo_fallback") or "use_next"
    language_pref = db.get_setting("pref.language") or "en"  # Language preference for logo selection
    if req.preset_id:
        if req.template_id in presets_data:
            preset_list = presets_data[req.template_id]["presets"]
            preset = next((p for p in preset_list if p["id"] == req.preset_id), None)
            if preset:
                preset_opts = preset.get("options", {})
                base_options = {**preset_opts, **base_options}
                base_poster_filter = base_options.get("poster_filter", base_poster_filter)
                base_logo_mode = base_options.get("logo_mode", base_logo_mode)
                base_logo_preference = base_options.get("logo_preference") or base_logo_mode or base_logo_preference
                base_logo_preference = map_logo_mode_to_preference(base_logo_preference)
                logger.debug("[BATCH] Applied preset '%s' options for template '%s'", req.preset_id, req.template_id)
                
                # Extract season_options if available (for TV show batch)
                season_opts = preset.get("season_options", {})
                if season_opts:
                    season_options = {**season_opts}
                    season_poster_filter = season_options.get("poster_filter", base_poster_filter)
                    logger.debug("[BATCH] Extracted season_options with poster_filter='%s'", season_poster_filter)
                else:
                    season_options = dict(base_options)
                    season_poster_filter = base_poster_filter
            else:
                logger.warning("[BATCH] Preset '%s' not found for template '%s'", req.preset_id, req.template_id)
        else:
            logger.warning("[BATCH] Template '%s' not found in presets", req.template_id)

    item_type = "TV shows" if is_tv_batch else "movies"
    total_count = len(req.rating_keys)
    logger.info("[BATCH] Processing %d %s with %d concurrent workers", total_count, item_type, max_workers)

    # Start Discord progress notification (returns message_id for updates)
    discord_message_id = None
    try:
        discord_message_id = start_batch_progress_notification(
            library_id=req.library_id,
            template_id=req.template_id,
            total_count=total_count,
            source="batch"
        )
    except Exception as notif_err:
        logger.debug("[BATCH] Failed to start Discord progress: %s", notif_err)

    last_discord_update = time.time()
    discord_update_interval = 15  # seconds
    last_title = ""
    success_count = 0
    failed_count = 0
    poster_fallback_count = 0
    logo_fallback_count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_idx = {}
        for idx, rating_key in enumerate(req.rating_keys, start=1):
            if is_tv_batch:
                future = executor.submit(
                    _process_single_tv_show,
                    idx,
                    rating_key,
                    req,
                    base_options,
                    base_poster_filter,
                    base_logo_preference,
                    base_logo_mode,
                    white_logo_fallback,
                    language_pref,
                    presets_data,
                    season_poster_filter,
                    season_options,
                )
            else:
                future = executor.submit(
                    _process_single_movie,
                    idx,
                    rating_key,
                    req,
                    base_options,
                    base_poster_filter,
                    base_logo_preference,
                    base_logo_mode,
                    white_logo_fallback,
                    language_pref,
                    presets_data,
                )
            future_to_idx[future] = idx

        # Collect results as they complete
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results.append(result)
                # Track success/failure
                if result.get("status") == "ok":
                    success_count += 1
                else:
                    failed_count += 1
                # Enqueue for retry if ideal template conditions weren't met
                if retry_enabled:
                    if result.get("needs_retry"):
                        # Movie path: needs_retry is at the top level
                        try:
                            db.add_to_retry_queue(
                                rating_key=result.get("rating_key", ""),
                                media_type="movie",
                                library_id=str(req.library_id or ""),
                                template_id=req.template_id,
                                preset_id=req.preset_id or "",
                                title=result.get("title", ""),
                                reason=result.get("retry_reason", "unknown"),
                            )
                            logger.info("[BATCH] Queued %s for retry (reason=%s)", result.get("title"), result.get("retry_reason"))
                        except Exception as queue_err:
                            logger.debug("[BATCH] Failed to enqueue retry for %s: %s", result.get("rating_key"), queue_err)
                    elif is_tv_batch and result.get("status") == "ok":
                        # TV path: needs_retry lives in sub-results; enqueue the show once if any sub needs retry
                        sub_needing_retry = next((s for s in result.get("results", []) if s.get("needs_retry")), None)
                        if sub_needing_retry:
                            try:
                                db.add_to_retry_queue(
                                    rating_key=result.get("rating_key", ""),
                                    media_type="tv",
                                    library_id=str(req.library_id or ""),
                                    template_id=req.template_id,
                                    preset_id=req.preset_id or "",
                                    title=result.get("show_title", ""),
                                    reason=sub_needing_retry.get("retry_reason", "unknown"),
                                )
                                logger.info("[BATCH] Queued TV show %s for retry (reason=%s)", result.get("show_title"), sub_needing_retry.get("retry_reason"))
                            except Exception as queue_err:
                                logger.debug("[BATCH] Failed to enqueue TV retry for %s: %s", result.get("rating_key"), queue_err)
                # Track fallback usage (direct flags for movies, nested results for TV shows)
                if result.get("poster_fallback"):
                    poster_fallback_count += 1
                if result.get("logo_fallback"):
                    logo_fallback_count += 1
                # For TV shows with season results, aggregate from sub-results
                for sub in result.get("results", []):
                    if sub.get("poster_fallback"):
                        poster_fallback_count += 1
                    if sub.get("logo_fallback"):
                        logo_fallback_count += 1
                # Track title for Discord updates
                last_title = result.get("title") or result.get("show_title") or ""
                # Update processed count
                with batch_status_lock:
                    batch_status["processed"] = len(results)
            except Exception as e:
                logger.error(f"[BATCH] Unexpected error in future for movie {idx}: {e}")
                results.append({
                    "rating_key": req.rating_keys[idx-1],
                    "title": "",
                    "status": "error",
                    "error": str(e),
                })
                failed_count += 1
                with batch_status_lock:
                    batch_status["processed"] = len(results)

            # Update Discord progress every N seconds
            if discord_message_id and (time.time() - last_discord_update) >= discord_update_interval:
                try:
                    update_batch_progress_notification(
                        message_id=discord_message_id,
                        library_id=req.library_id,
                        template_id=req.template_id,
                        current_index=len(results),
                        total_count=total_count,
                        current_title=last_title,
                        success_count=success_count,
                        failed_count=failed_count,
                        source="batch",
                        poster_fallback_count=poster_fallback_count,
                        logo_fallback_count=logo_fallback_count,
                    )
                    last_discord_update = time.time()
                except Exception as update_err:
                    logger.debug("[BATCH] Failed to update Discord progress: %s", update_err)

    # Mark batch as complete
    _update_batch_status({
        "state": "done",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "current_step": "Finished",
    })

    # Send Discord completion notification
    if discord_message_id:
        try:
            complete_batch_progress_notification(
                message_id=discord_message_id,
                library_id=req.library_id,
                template_id=req.template_id,
                total_count=total_count,
                success_count=success_count,
                failed_count=failed_count,
                source="batch",
                poster_fallback_count=poster_fallback_count,
                logo_fallback_count=logo_fallback_count,
            )
        except Exception as notif_err:
            logger.debug("[BATCH] Failed to complete Discord progress: %s", notif_err)
    else:
        # Fallback to simple Discord notification if progress tracking wasn't started
        try:
            send_batch_notification(
                library_id=req.library_id,
                template_id=req.template_id,
                preset_id=req.preset_id or "",
                success_count=success_count,
                failed_count=failed_count,
                source="batch"
            )
        except Exception as notif_err:
            logger.debug("[BATCH] Failed to send Discord notification: %s", notif_err)

    # Send Apprise completion notification (always fires independently of Discord)
    try:
        send_apprise_notification(
            title=f"{total_count} posters processed",
            template_id=req.template_id,
            preset_id=req.preset_id or "",
            library_id=req.library_id,
            source="batch",
            action="sent_to_plex",
            count=total_count,
            success_count=success_count,
            failed_count=failed_count,
        )
    except Exception as notif_err:
        logger.debug("[BATCH] Failed to send Apprise notification: %s", notif_err)

    return {"results": results}


@router.post("/batch-movies")
def api_batch_movies(req: MovieBatchRequest):
    """
    Batch process multiple movies with the same template and preset.
    This endpoint is specifically for movies only.
    """
    logger.info("[BATCH MOVIES] Processing %d movies", len(req.rating_keys))
    return _execute_batch(req, is_tv_batch=False)


@router.post("/batch-tv-shows")
def api_batch_tv_shows(req: TVShowBatchRequest):
    """
    Batch process multiple TV shows with the same template and preset.
    This endpoint handles TV shows and their seasons.
    """
    logger.info("[BATCH TV SHOWS] Processing %d TV shows", len(req.rating_keys))
    return _execute_batch(req, is_tv_batch=True)


@router.post("/batch")
def api_batch(req: BatchRequest):
    """
    Legacy batch endpoint — DEPRECATED.
    Use /batch-movies or /batch-tv-shows instead.
    This endpoint uses include_seasons to guess media type, which can cause
    TV show TMDB IDs to be looked up as movies (returning wrong posters).
    """
    is_tv_batch = getattr(req, 'include_seasons', False)
    logger.warning("[BATCH LEGACY] Deprecated /batch endpoint called with %d items (TV: %s). "
                   "Use /batch-movies or /batch-tv-shows instead.", len(req.rating_keys), is_tv_batch)
    return _execute_batch(req, is_tv_batch=is_tv_batch)


# ==============================================================================
# Public wrapper functions for programmatic use (auto_generate, webhooks, etc.)
# ==============================================================================

def process_single_movie_poster(
    rating_key: str,
    template_id: str,
    preset_id: str,
    send_to_plex: bool = False,
    library_id: str = "",
    labels: list = None,
    source: str = "webhook",
    send_logos_to_plex: bool = False,
    send_only_if_ideal: bool = False,
) -> bool:
    """
    Process a single movie poster programmatically.
    Used by auto_generate and webhook handlers.

    Args:
        rating_key: Plex rating key
        template_id: Template to use
        preset_id: Preset to use
        send_to_plex: Whether to upload to Plex
        library_id: Library ID for history tracking
        labels: Labels to apply if sending to Plex
        source: Source identifier for history ('webhook', 'auto_generate', etc.)
        send_only_if_ideal: If True, skip the Plex upload when the render still needs_retry
            (i.e. no logo found / a fallback was used). Used by the retry queue so it doesn't
            keep re-sending the same fallback poster on every retry pass.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create a minimal request object
        req = MovieBatchRequest(
            rating_keys=[rating_key],
            template_id=template_id,
            preset_id=preset_id,
            options={},
            send_to_plex=send_to_plex,
            labels=labels or [],
            library_id=library_id,
            send_logos_to_plex=send_logos_to_plex,
            send_only_if_ideal=send_only_if_ideal,
        )

        # Load presets for options
        from ..config import load_presets
        presets_data = load_presets()
        template_presets = presets_data.get(template_id, {}).get("presets", [])
        preset = next((p for p in template_presets if p.get("id") == preset_id), None)

        if not preset:
            logger.error(f"[{source.upper()}] Preset {preset_id} not found for template {template_id}")
            return False

        base_options = preset.get("options", {})
        # Read settings from options (where they're stored), not from preset root
        base_poster_filter = base_options.get("poster_filter", "any")
        base_logo_preference = base_options.get("logo_preference", "white")
        base_logo_mode = base_options.get("logo_mode", "stock")
        # Read white_logo_fallback from global DB setting (same as _execute_batch), fall back to preset option
        white_logo_fallback = db.get_setting("fallback.white_logo_fallback") or base_options.get("white_logo_fallback", "use_next")
        language_pref = db.get_setting("pref.language") or base_options.get("language", "en")
        logger.debug("[%s] Fallback settings for %s: logo_action=%s white_fallback=%s",
                     source.upper(), preset_id,
                     base_options.get("fallbackLogoAction", "continue"),
                     white_logo_fallback)

        # Process the movie with proper source tracking
        result = _process_single_movie(
            idx=0,
            rating_key=rating_key,
            req=req,
            base_options=base_options,
            base_poster_filter=base_poster_filter,
            base_logo_preference=base_logo_preference,
            base_logo_mode=base_logo_mode,
            white_logo_fallback=white_logo_fallback,
            language_pref=language_pref,
            presets_data=presets_data,
            source=source  # Pass source for history tracking
        )

        return result

    except Exception as e:
        logger.error(f"[{source.upper()}] Error processing movie poster: {e}", exc_info=True)
        return {}


def process_single_tv_show_poster(
    rating_key: str,
    template_id: str,
    preset_id: str,
    send_to_plex: bool = False,
    library_id: str = "",
    labels: list = None,
    include_seasons: bool = True,
    source: str = "webhook",
    send_logos_to_plex: bool = False,
    send_only_if_ideal: bool = False,
) -> bool:
    """
    Process a single TV show poster programmatically.
    Used by auto_generate and webhook handlers.

    Args:
        rating_key: Plex rating key
        template_id: Template to use
        preset_id: Preset to use
        send_to_plex: Whether to upload to Plex
        library_id: Library ID for history tracking
        labels: Labels to apply if sending to Plex
        include_seasons: Whether to generate season posters
        source: Source identifier for history ('webhook', 'auto_generate', etc.)
        send_only_if_ideal: If True, skip the Plex upload for any series/season poster that
            still needs_retry. Used by the retry queue so it doesn't keep re-sending the same
            fallback poster on every retry pass.

    Returns:
        True if successful, False otherwise
    """
    try:
        # Create a minimal request object
        req = TVShowBatchRequest(
            rating_keys=[rating_key],
            template_id=template_id,
            preset_id=preset_id,
            options={},
            send_to_plex=send_to_plex,
            labels=labels or [],
            include_seasons=include_seasons,
            library_id=library_id,
            send_logos_to_plex=send_logos_to_plex,
            send_only_if_ideal=send_only_if_ideal,
        )

        # Load presets for options
        from ..config import load_presets
        presets_data = load_presets()
        template_presets = presets_data.get(template_id, {}).get("presets", [])
        preset = next((p for p in template_presets if p.get("id") == preset_id), None)

        if not preset:
            logger.error(f"[{source.upper()}] Preset {preset_id} not found for template {template_id}")
            return False

        base_options = preset.get("options", {})
        # Read settings from options (where they're stored), not from preset root
        base_poster_filter = base_options.get("poster_filter", "any")
        base_logo_preference = base_options.get("logo_preference", "white")
        base_logo_mode = base_options.get("logo_mode", "stock")
        # Read white_logo_fallback from global DB setting (same as _execute_batch), fall back to preset option
        white_logo_fallback = db.get_setting("fallback.white_logo_fallback") or base_options.get("white_logo_fallback", "use_next")
        language_pref = db.get_setting("pref.language") or base_options.get("language", "en")
        logger.debug("[%s] Fallback settings for %s: logo_action=%s white_fallback=%s",
                     source.upper(), preset_id,
                     base_options.get("fallbackLogoAction", "continue"),
                     white_logo_fallback)

        # Process the TV show with proper source tracking
        result = _process_single_tv_show(
            idx=0,
            rating_key=rating_key,
            req=req,
            base_options=base_options,
            base_poster_filter=base_poster_filter,
            base_logo_preference=base_logo_preference,
            base_logo_mode=base_logo_mode,
            white_logo_fallback=white_logo_fallback,
            language_pref=language_pref,
            presets_data=presets_data,
            source=source  # Pass source for history tracking
        )

        return result

    except Exception as e:
        logger.error(f"[{source.upper()}] Error processing TV show poster: {e}", exc_info=True)
        return {}
