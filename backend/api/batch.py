from fastapi import APIRouter
from ..schemas import BatchRequest, MovieBatchRequest, TVShowBatchRequest
from ..config import settings, plex_remove_label, logger, get_movie_tmdb_id
from ..config import load_presets
from .notifications import send_batch_notification, start_batch_progress_notification, update_batch_progress_notification, complete_batch_progress_notification
import time
from ..tmdb_client import get_images_for_movie, get_movie_details, get_tv_show_details, get_images_for_tv_show, get_tv_season_images, get_tv_external_ids
from ..rendering import render_poster_image, render_with_overlay_cache
from io import BytesIO
import requests
from backend.assets.selection import pick_poster, pick_logo, map_logo_mode_to_preference
from backend.logo_sources import get_logos_merged
from .movies import fetch_and_cache_poster
from .tv_shows import plex_session, plex_headers, extract_tmdb_id_from_metadata, extract_tvdb_id_from_metadata
from .save import apply_save_location_variables, get_save_location_template, resolve_library_label, embed_library_metadata
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
    try:
        template_id = req.template_id
        preset_id = req.preset_id
        render_options_base = dict(base_options)
        poster_filter = base_poster_filter
        logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or base_logo_preference
        logo_preference = map_logo_mode_to_preference(logo_preference)
        logo_mode = base_logo_mode

        logger.info("[BATCH] Start rating_key=%s template=%s", rating_key, template_id)

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
        logger.debug("[BATCH] rating_key=%s tmdb_id=%s", rating_key, tmdb_id)

        # Fetch movie details for template variables
        movie_details = get_movie_details(tmdb_id)
        # Fetch images honoring preferred languages (fallback to movie original language)
        imgs = get_images_for_movie(tmdb_id, movie_details.get("original_language"))
        posters = imgs.get("posters", [])

        # Get logos using merged sources based on preference
        logo_source_pref = render_options_base.get("logoSource") or render_options_base.get("logo_source")
        logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
        logger.debug(
            "[BATCH] rating_key=%s posters=%d logos=%d filter=%s logo_pref=%s",
            rating_key,
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
        logger.info(f"[BATCH] Picked logo pref={logo_preference}")
        logger.info(f"[BATCH] Picked poster={poster_url}")
        logger.info(f"[BATCH] Picked logo={logo_url}")
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
            import os
            from pathlib import Path
            import json

            # Load UI settings to respect saveLocation + batch subfolder flag
            ui_settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
            legacy_file = Path(settings.CONFIG_DIR) / "ui_settings.json"
            save_template = get_save_location_template(media_type="movie")
            save_batch = False
            try:
                data = None
                if ui_settings_file.exists():
                    data = json.loads(ui_settings_file.read_text(encoding="utf-8"))
                elif legacy_file.exists():
                    data = json.loads(legacy_file.read_text(encoding="utf-8"))
                if data:
                    save_template = data.get("saveLocation") or save_template
                    save_batch = bool(data.get("saveBatchInSubfolder", False))
            except Exception:
                pass

            # Apply variable substitution
            # Use library display name/title when available
            library_label = resolve_library_label(req.library_id)

            save_path_template = apply_save_location_variables(
                save_template,
                movie_details.get("title", rating_key),
                movie_details.get("year", ""),
                rating_key,
                library_label
            )

            # Sanitize path components (keep dots for filenames)
            # Remove colons and other special characters (similar to Kometa's structure)
            safe_path = "".join(c for c in save_path_template if c.isalnum() or c in " _-/().")
            safe_path = safe_path.strip()

            candidate = Path(safe_path)
            if candidate.suffix:
                base_dir = candidate.parent
                filename = candidate.name
            else:
                base_dir = candidate
                # Sanitize the title for filename
                title = movie_details.get('title', rating_key)
                safe_title = "".join(c for c in title if c.isalnum() or c in " _-().")
                filename = safe_title.strip()
                yr = movie_details.get("year", "")
                if yr:
                    filename += f" ({yr})"
                filename += ".jpg"

            # Map explicit /output to configured OUTPUT_ROOT
            base_dir_str = str(base_dir).replace("\\", "/")
            mapped_output = False
            if base_dir_str.startswith("/output"):
                tail = base_dir_str[len("/output"):].lstrip("/")
                base_dir = Path(settings.OUTPUT_ROOT) / tail if tail else Path(settings.OUTPUT_ROOT)
                mapped_output = True

            # Map explicit /config to configured CONFIG_DIR so default template lands in config volume
            if base_dir_str.startswith("/config"):
                tail = base_dir_str[len("/config"):].lstrip("/")
                base_dir = Path(settings.CONFIG_DIR) / tail if tail else Path(settings.CONFIG_DIR)
                mapped_output = True

            # Anchor relative paths (skip if we already mapped /output or /config)
            if not base_dir.is_absolute():
                lower_path = base_dir_str.lower()
                if lower_path.startswith("config/"):
                    tail = base_dir_str.split("/", 1)[1] if "/" in base_dir_str else ""
                    base_dir = Path(settings.CONFIG_DIR) / tail
                elif lower_path.startswith("output/"):
                    tail = base_dir_str.split("/", 1)[1] if "/" in base_dir_str else ""
                    base_dir = Path(settings.OUTPUT_ROOT) / tail
                elif not mapped_output:
                    base_dir = Path(settings.OUTPUT_ROOT) / str(base_dir).lstrip("/\\")

            # Optional batch subfolder (insert after output root)
            if save_batch:
                try:
                    rel = base_dir.relative_to(settings.OUTPUT_ROOT)
                    base_dir = Path(settings.OUTPUT_ROOT) / "batch" / rel
                except ValueError:
                    base_dir = Path(settings.OUTPUT_ROOT) / "batch" / base_dir.name

            os.makedirs(base_dir, exist_ok=True)
            save_path = base_dir / filename

            # Embed library metadata into the image
            img = embed_library_metadata(
                img,
                req.library_id,
                library_label,
                movie_details.get("title", ""),
                str(movie_details.get("year", "")) if movie_details.get("year") else None,
            )

            # Determine output format from filename extension
            file_ext = save_path.suffix.lower()

            if file_ext == '.png':
                # For PNG, properly embed metadata in PNG chunks
                pnginfo = PngImagePlugin.PngInfo()
                pnginfo.add_text("simposter_library_id", str(req.library_id or ""))
                pnginfo.add_text("simposter_library_name", str(library_label or ""))
                pnginfo.add_text("simposter_movie_title", str(movie_details.get("title", "")))
                pnginfo.add_text("simposter_movie_year", str(movie_details.get("year", "")))
                img.save(save_path, "PNG", pnginfo=pnginfo)
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
                    "simposter_movie_year": str(movie_details.get("year", ""))
                })
                exif[0x9286] = metadata_json.encode('utf-8')  # UserComment field
                exif_bytes = exif.tobytes()

                # Get JPEG quality from settings
                quality = 95
                try:
                    if ui_settings and ui_settings.imageQuality:
                        quality = ui_settings.imageQuality.jpgQuality
                except Exception:
                    pass
                img_rgb.save(save_path, "JPEG", quality=quality, exif=exif_bytes)

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
        if req.send_to_plex:
            _update_batch_status({
                "current_step": "Sending to Plex",
            })
            buf = BytesIO()
            # Get JPEG quality from settings
            quality = 95
            try:
                if ui_settings and ui_settings.imageQuality:
                    quality = ui_settings.imageQuality.jpgQuality
            except Exception:
                pass
            img.convert("RGB").save(buf, "JPEG", quality=quality)
            payload = buf.getvalue()

            plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": "image/jpeg",
            }

            r = requests.post(plex_url, headers=headers, data=payload, timeout=20)
            r.raise_for_status()

            # Label removal
            if req.labels:
                logger.info("[BATCH] Removing labels %s from %s", req.labels, rating_key)
                try:
                    for label in req.labels:
                        plex_remove_label(rating_key, label)
                        logger.info("[BATCH] Removed label '%s' from %s", label, rating_key)
                except Exception as label_err:
                    logger.warning("[BATCH] Label removal failed for %s: %s", rating_key, label_err)

            logger.info(f"[BATCH] Uploaded to Plex: {rating_key}")
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
            logger.debug("[BATCH] Failed to refresh poster cache for %s: %s", rating_key, cache_err)

        result = {
            "rating_key": rating_key,
            "title": movie_details.get("title", ""),
            "poster_used": poster_url,
            "logo_used": logo_url,
            "status": "ok",
            "poster_fallback": poster_fallback_action_used == "template",
            "logo_fallback": logo_fallback_used,
        }
        if save_path:
            result["save_path"] = str(save_path)

        _update_batch_status({
            "current_step": "Complete",
        })

        return result

    except Exception as e:
        logger.error(f"[BATCH] Error for {rating_key}\n{e}")
        return {
            "rating_key": rating_key,
            "title": "",
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
    try:
        template_id = req.template_id
        preset_id = req.preset_id
        render_options_base = dict(base_options)
        poster_filter = base_poster_filter
        logo_preference = render_options_base.get("logo_preference") or render_options_base.get("logo_mode") or base_logo_preference
        logo_preference = map_logo_mode_to_preference(logo_preference)
        logo_mode = base_logo_mode

        # For TV show season rendering, use season-specific options if available
        season_poster_filter_final = season_poster_filter or base_poster_filter
        season_options_final = dict(season_options or base_options)

        logger.info("[BATCH TV] Start rating_key=%s template=%s include_seasons=%s season_poster_filter=%s", 
                    rating_key, template_id, req.include_seasons, season_poster_filter_final)

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

        if tmdb_id and not tvdb_id:
            try:
                external_ids = get_tv_external_ids(tmdb_id)
                tvdb_id = external_ids.get("tvdb_id") or external_ids.get("id")
            except Exception:
                pass

        if not tmdb_id:
            raise Exception("No TMDB ID found for TV show")

        logger.debug("[BATCH TV] rating_key=%s tmdb_id=%s tvdb_id=%s", rating_key, tmdb_id, tvdb_id)

        # Fetch TV show details
        show_details = get_tv_show_details(tmdb_id)
        show_title = show_details.get("name", "Unknown")

        # If include_seasons is False, render series poster only
        if not req.include_seasons:
            return _render_tv_series_poster(
                rating_key, tmdb_id, tvdb_id, show_details, template_id, preset_id,
                render_options_base, poster_filter, logo_preference, logo_mode,
                white_logo_fallback, language_pref, req,
                source=source
            )
        else:
            # Fetch seasons and render all with season-specific options
            return _render_all_tv_seasons(
                rating_key, tmdb_id, tvdb_id, show_details, template_id, preset_id,
                render_options_base, poster_filter, logo_preference, logo_mode,
                white_logo_fallback, language_pref, req,
                season_poster_filter_final, season_options_final,
                source=source,
                affected_seasons=affected_seasons
            )

    except Exception as e:
        logger.error(f"[BATCH TV] Error for {rating_key}\n{e}")
        return {
            "rating_key": rating_key,
            "show_title": "",
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
):
    """Render all seasons for a TV show.

    Args:
        affected_seasons: If provided, only process these specific season numbers.
                         Used by webhooks to only generate posters for newly added seasons.
                         If None or empty, process all seasons (batch mode).
    """
    show_title = show_details.get("name", "Unknown")
    # Use season-specific options if provided
    final_season_options = dict(season_options or render_options)

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

    # Only render series poster if not in webhook mode with affected_seasons
    # (webhooks with affected_seasons should only render the specific seasons, not series poster)
    should_render_series = not affected_seasons

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
                    # Use season_options from fallback preset since this is a season
                    fp_opts = fpreset.get("season_options", {}) if "season_options" in fpreset else fpreset.get("options", {})
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

        # Add season_text to season-specific options
        season_render_options["season_text"] = season_title

        # Render the poster with potentially updated template/preset from fallback
        result = _render_and_save_poster(
            season_key, poster_url, logo_url, season_render_options, season_template_id, season_preset_id,
            show_title, show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
            req, is_tv=True, season_title=season_title, season_index=season_index,
            poster_fallback_used=season_poster_fallback_used,
            poster_fallback_template=season_poster_fallback_template,
            poster_fallback_preset=season_poster_fallback_preset,
            source=source,
        )
        results.append(result)

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
):
    """Common rendering and saving logic for both movies and TV shows."""
    # Create a combined display title for history (e.g., "Show Name - Season 1" for TV seasons)
    display_title = f"{title} - {season_title}" if season_title else title

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
            # Use appropriate save location template based on media type
            media_type = "tv-show" if is_tv else "movie"
            template_str = get_save_location_template(media_type=media_type)
            library_label = resolve_library_label(req.library_id) if req.library_id else ""

            # Apply variable substitution (include season for TV shows if provided)
            save_path_template = apply_save_location_variables(
                template_str,
                title,
                int(year) if year else None,
                rating_key,
                library_label,
                season=season_index if is_tv else None,
                is_tv_show=is_tv
            )

            # Sanitize path components
            safe_path = "".join(c for c in save_path_template if c.isalnum() or c in " _-/().")
            safe_path = safe_path.strip()

            from pathlib import Path
            candidate = Path(safe_path)
            if candidate.suffix:
                base_dir = candidate.parent
                filename = candidate.name
            else:
                base_dir = candidate
                # Sanitize the title for filename
                safe_title = "".join(c for c in title if c.isalnum() or c in " _-()")
                safe_title = safe_title.strip()

                # Add season suffix for TV show seasons
                if season_title:
                    # Extract season number from season_title (e.g., "Season 1" -> "S01")
                    import re
                    season_match = re.search(r'(\d+)', season_title)
                    if season_match:
                        season_num = int(season_match.group(1))
                        filename = f"{safe_title} - S{season_num:02d}.png"
                    else:
                        # Fallback: use sanitized season title
                        safe_season = "".join(c for c in season_title if c.isalnum() or c in " _-()")
                        filename = f"{safe_title} - {safe_season}.png"
                else:
                    filename = f"{safe_title}.png"

            save_path = base_dir / filename

            # Convert to absolute path for clarity
            save_path = save_path.resolve()

            # Create parent directory if it doesn't exist
            try:
                save_path.parent.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error("[BATCH] Failed to create directory %s: %s", save_path.parent, e)
                raise

            # Embed library metadata into the image
            rendered = embed_library_metadata(
                rendered,
                req.library_id,
                library_label,
                title,
                str(year) if year else None
            )

            # Save as PNG with metadata
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

            rendered.save(str(save_path), "PNG", pnginfo=pnginfo, optimize=False)
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
    if req.send_to_plex:
        _update_batch_status({
            "current_step": "Uploading to Plex",
        })

        buf = BytesIO()
        rendered.convert("RGB").save(buf, "JPEG", quality=95)
        payload = buf.getvalue()

        try:
            upload_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": "image/jpeg",
            }
            upload_resp = requests.post(upload_url, headers=headers, data=payload, timeout=20)
            upload_resp.raise_for_status()
            logger.info("[BATCH] Uploaded poster to Plex for %s", title)

            # Invalidate poster cache so UI shows updated poster
            if is_tv:
                from .tv_shows import _remove_poster_cache as _remove_tv_poster_cache
                _remove_tv_poster_cache(rating_key, "tv")
                logger.info("[BATCH] Invalidated TV poster cache for %s", rating_key)
            else:
                from .movies import _remove_poster_cache as _remove_movie_poster_cache
                _remove_movie_poster_cache(rating_key)
                logger.info("[BATCH] Invalidated movie poster cache for %s", rating_key)

            # Remove labels if specified
            if req.labels:
                logger.info("[BATCH] Removing labels %s from %s (%s)", req.labels, rating_key, title)
                try:
                    for label_name in req.labels:
                        plex_remove_label(rating_key, label_name)
                        logger.info("[BATCH] Removed label '%s' from %s", label_name, rating_key)
                except Exception as label_err:
                    logger.warning("[BATCH] Label removal failed for %s: %s", rating_key, label_err)

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

    result = {
        "rating_key": rating_key,
        "poster_used": poster_url,
        "logo_used": logo_url,
        "status": "ok",
        "poster_fallback": poster_fallback_used,
        "logo_fallback": logo_fallback_used,
    }
    if season_title:
        result["season"] = season_title
    if save_path:
        result["save_path"] = str(save_path)

    return result


def _execute_batch(req: Union[BatchRequest, MovieBatchRequest, TVShowBatchRequest], is_tv_batch: bool):
    """
    Shared batch processing logic for both movies and TV shows.

    Args:
        req: The batch request containing all parameters
        is_tv_batch: True for TV shows (process seasons), False for movies
    """
    # Get concurrent renders setting
    try:
        from .ui_settings import _read_settings
        ui_settings = _read_settings(include_env=False)
        max_workers = ui_settings.performance.concurrentRenders if ui_settings.performance else 2
    except Exception:
        max_workers = 2  # Default to 2 concurrent renders

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
        # Fallback to simple notification if progress tracking wasn't started
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
    Legacy batch endpoint that handles both movies and TV shows.
    Kept for backward compatibility. Use /batch-movies or /batch-tv-shows for new code.
    """
    is_tv_batch = getattr(req, 'include_seasons', False)
    logger.info("[BATCH LEGACY] Processing %d items (TV: %s)", len(req.rating_keys), is_tv_batch)
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
    source: str = "webhook"
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
            library_id=library_id
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
        base_poster_filter = preset.get("poster_filter", "any")
        base_logo_preference = preset.get("logo_preference", "white")
        base_logo_mode = base_options.get("logo_mode", "stock")
        white_logo_fallback = preset.get("white_logo_fallback", "continue")
        language_pref = preset.get("language", "en")

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

        return result.get("status") == "success"

    except Exception as e:
        logger.error(f"[{source.upper()}] Error processing movie poster: {e}", exc_info=True)
        return False


def process_single_tv_show_poster(
    rating_key: str,
    template_id: str,
    preset_id: str,
    send_to_plex: bool = False,
    library_id: str = "",
    labels: list = None,
    include_seasons: bool = True,
    source: str = "webhook"
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
            library_id=library_id
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
        base_poster_filter = preset.get("poster_filter", "any")
        base_logo_preference = preset.get("logo_preference", "white")
        base_logo_mode = base_options.get("logo_mode", "stock")
        white_logo_fallback = preset.get("white_logo_fallback", "continue")
        language_pref = preset.get("language", "en")

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

        return result.get("status") == "success"

    except Exception as e:
        logger.error(f"[{source.upper()}] Error processing TV show poster: {e}", exc_info=True)
        return False
