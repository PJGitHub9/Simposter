from fastapi import APIRouter
from ..schemas import BatchRequest
from ..config import settings, plex_remove_label, logger, get_movie_tmdb_id
from ..config import load_presets
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
from typing import Optional, List, Dict, Any

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
    req: BatchRequest,
    base_options: dict,
    base_poster_filter: str,
    base_logo_preference: str,
    base_logo_mode: str,
    white_logo_fallback: str,
    language_pref: str,
    presets_data: dict,
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

        # Fallback handling for poster preference (runs before any logo fallback)
        if not poster:
            fallback_action = render_options_base.get("fallbackPosterAction") or "continue"
            poster_fallback_action_used = fallback_action
            fallback_template = render_options_base.get("fallbackPosterTemplate")
            fallback_preset = render_options_base.get("fallbackPosterPreset")
            if fallback_action == "template" and fallback_template:
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
                    "status": "skipped_no_poster"
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
                    "status": "skipped_no_logo"
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
            save_template = get_save_location_template()
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
            "poster_used": poster_url,
            "logo_used": logo_url,
            "status": "ok",
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
            "status": "error",
            "error": str(e),
        }


def _process_single_tv_show(
    idx: int,
    rating_key: str,
    req: BatchRequest,
    base_options: dict,
    base_poster_filter: str,
    base_logo_preference: str,
    base_logo_mode: str,
    white_logo_fallback: str,
    language_pref: str,
    presets_data: dict,
    season_poster_filter: Optional[str] = None,
    season_options: Optional[dict] = None,
):
    """Process a single TV show in the batch. Returns result dict."""
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
                white_logo_fallback, language_pref, req
            )
        else:
            # Fetch seasons and render all with season-specific options
            return _render_all_tv_seasons(
                rating_key, tmdb_id, tvdb_id, show_details, template_id, preset_id,
                render_options_base, poster_filter, logo_preference, logo_mode,
                white_logo_fallback, language_pref, req,
                season_poster_filter_final, season_options_final
            )

    except Exception as e:
        logger.error(f"[BATCH TV] Error for {rating_key}\n{e}")
        return {
            "rating_key": rating_key,
            "status": "error",
            "error": str(e),
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
    req: BatchRequest,
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

    # Select poster and logo with textless fallback logic
    poster = None
    if poster_filter == "textless":
        # Try to find a textless poster
        poster = next((p for p in posters if p.get("has_text") == False), None)
        if not poster:
            logger.debug("[BATCH TV] No textless series poster found, using first available")
    else:
        poster = pick_poster(posters, poster_filter)
    
    if not poster:
        poster = posters[0] if posters else None
    if not poster:
        raise Exception("No poster found for series")

    logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference, white_logo_fallback, language_pref)

    poster_url = poster.get("url")
    logo_url = logo.get("url") if logo else None

    # Render the poster
    return _render_and_save_poster(
        rating_key, poster_url, logo_url, render_options, template_id, preset_id,
        show_details.get("name"), show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
        req, is_tv=True
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
    req: BatchRequest,
    season_poster_filter: str = "all",
    season_options: Optional[dict] = None,
):
    """Render all seasons for a TV show."""
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
    
    # Render series poster first before processing seasons
    logger.info("[BATCH TV] Rendering series poster for %s before seasons", show_title)
    _update_batch_status({
        "current_movie": f"{show_title} - Series Poster",
        "current_step": "Rendering series poster",
    })
    
    try:
        # Select series poster with textless fallback logic
        series_poster = None
        if poster_filter == "textless":
            series_poster = next((p for p in series_posters if p.get("has_text") == False), None)
            if not series_poster:
                logger.debug("[BATCH TV] No textless series poster found, using first available")
        else:
            series_poster = pick_poster(series_posters, poster_filter)
        
        if not series_poster:
            series_poster = series_posters[0] if series_posters else None
        
        if series_poster:
            # Select logo for series
            series_logo = None if str(logo_mode).lower() == "none" else pick_logo(series_logos, logo_preference, white_logo_fallback, language_pref)
            series_poster_url = series_poster.get("url")
            series_logo_url = series_logo.get("url") if series_logo else None
            
            # Render series poster
            series_result = _render_and_save_poster(
                rating_key, series_poster_url, series_logo_url, render_options, template_id, preset_id,
                show_title, show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
                req, is_tv=True
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
            "error": str(e)
        })
    
    # Now process individual seasons
    for season in seasons:
        season_index = season["index"]
        season_key = season["key"]
        season_title = season["title"]

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

        # Select poster with textless fallback logic using season-specific filter
        poster = None
        if season_poster_filter == "textless":
            # Try season textless first
            poster = next((p for p in season_posters if p.get("has_text") == False), None)
            # Fall back to series textless
            if not poster:
                poster = next((p for p in series_posters if p.get("has_text") == False), None)
        else:
            poster = pick_poster(all_posters, season_poster_filter)

        if not poster:
            poster = all_posters[0] if all_posters else None

        if not poster:
            logger.warning("[BATCH TV] No poster found for %s - %s, skipping", show_title, season_title)
            results.append({
                "rating_key": season_key,
                "season": season_title,
                "status": "skipped_no_poster"
            })
            continue

        # Extract logo mode from season options (may differ from series logo mode)
        season_logo_mode = final_season_options.get("logo_mode", logo_mode)
        season_logo_preference = final_season_options.get("logo_preference") or season_logo_mode or logo_preference
        season_logo_preference = map_logo_mode_to_preference(season_logo_preference)

        # Select logo using season-specific logo mode
        logo = None if str(season_logo_mode).lower() == "none" else pick_logo(series_logos, season_logo_preference, white_logo_fallback, language_pref)

        poster_url = poster.get("url")
        logo_url = logo.get("url") if logo else None

        # Add season_text to season-specific options
        season_options_final = dict(final_season_options)
        season_options_final["season_text"] = season_title

        # Render the poster
        result = _render_and_save_poster(
            season_key, poster_url, logo_url, season_options_final, template_id, preset_id,
            show_title, show_details.get("first_air_date", "")[:4] if show_details.get("first_air_date") else None,
            req, is_tv=True, season_title=season_title
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
    req: BatchRequest,
    is_tv: bool = False,
    season_title: Optional[str] = None
):
    """Common rendering and saving logic for both movies and TV shows."""
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
            template_str = get_save_location_template()
            library_label = resolve_library_label(req.library_id) if req.library_id else ""

            # Apply variable substitution
            save_path_template = apply_save_location_variables(
                template_str,
                title,
                int(year) if year else None,
                rating_key,
                library_label
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
                filename = f"{safe_title}.png"

            save_path = base_dir / filename
            save_path.parent.mkdir(parents=True, exist_ok=True)

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
            logger.info("[BATCH] Saved %s to %s", title, save_path)

            # Record history
            try:
                db.add_history(
                    rating_key=rating_key,
                    library_id=str(req.library_id or ""),
                    title=title,
                    year=year,
                    template_id=template_id,
                    preset_id=preset_id,
                    action="saved_locally",
                    save_path=str(save_path),
                )
            except Exception:
                pass
        except Exception as save_err:
            logger.error("[BATCH] Save error for %s: %s", title, save_err)

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
                db.add_history(
                    rating_key=rating_key,
                    library_id=str(req.library_id or ""),
                    title=title,
                    year=year,
                    template_id=template_id,
                    preset_id=preset_id,
                    action="sent_to_plex",
                    save_path=str(save_path) if save_path else None,
                )
            except Exception:
                pass

        except Exception as upload_err:
            logger.error("[BATCH] Plex upload failed for %s: %s", title, upload_err)
            raise

    result = {
        "rating_key": rating_key,
        "poster_used": poster_url,
        "logo_used": logo_url,
        "status": "ok",
    }
    if season_title:
        result["season"] = season_title
    if save_path:
        result["save_path"] = str(save_path)

    return result


@router.post("/batch")
def api_batch(req: BatchRequest):
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

    # Determine if we're processing TV shows or movies
    # TV shows are indicated by include_seasons being present in the request
    is_tv_batch = hasattr(req, 'include_seasons')
    processing_func = _process_single_tv_show if is_tv_batch else _process_single_movie

    item_type = "TV shows" if is_tv_batch else "movies"
    logger.info("[BATCH] Processing %d %s with %d concurrent workers", len(req.rating_keys), item_type, max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_idx = {}
        for idx, rating_key in enumerate(req.rating_keys, start=1):
            future = executor.submit(
                processing_func,
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
                season_poster_filter if is_tv_batch else None,
                season_options if is_tv_batch else None,
            )
            future_to_idx[future] = idx

        # Collect results as they complete
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                result = future.result()
                results.append(result)
                # Update processed count
                with batch_status_lock:
                    batch_status["processed"] = len(results)
            except Exception as e:
                logger.error(f"[BATCH] Unexpected error in future for movie {idx}: {e}")
                results.append({
                    "rating_key": req.rating_keys[idx-1],
                    "status": "error",
                    "error": str(e),
                })
                with batch_status_lock:
                    batch_status["processed"] = len(results)

    # Mark batch as complete
    _update_batch_status({
        "state": "done",
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "current_step": "Finished",
    })

    return {"results": results}
