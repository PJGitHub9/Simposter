from fastapi import APIRouter
from ..schemas import BatchRequest
from ..config import settings, plex_remove_label, logger, get_movie_tmdb_id
from ..config import load_presets
from ..tmdb_client import get_images_for_movie, get_movie_details
from ..rendering import render_poster_image
from io import BytesIO
import requests
from backend.assets.selection import pick_poster, pick_logo
from backend.logo_sources import get_logos_merged
from .movies import fetch_and_cache_poster
from .save import apply_save_location_variables, get_save_location_template, resolve_library_label, embed_library_metadata
from datetime import datetime, timezone
from PIL import PngImagePlugin
from .. import database as db
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

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
    presets_data: dict,
):
    """Process a single movie in the batch. Returns result dict."""
    try:
        template_id = req.template_id
        preset_id = req.preset_id
        render_options_base = dict(base_options)
        poster_filter = base_poster_filter
        logo_preference = base_logo_preference
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
        logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"))
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
        logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference)

        # Fallback handling for poster preference
        if not poster:
            fallback_action = render_options_base.get("fallbackPosterAction") or "continue"
            fallback_template = render_options_base.get("fallbackPosterTemplate")
            fallback_preset = render_options_base.get("fallbackPosterPreset")
            if fallback_action == "template" and fallback_template:
                template_id = fallback_template
                if fallback_preset:
                    tpl_presets = presets_data.get(fallback_template, {}).get("presets", [])
                    fpreset = next((p for p in tpl_presets if p.get("id") == fallback_preset), None)
                    if fpreset:
                        fp_opts = fpreset.get("options", {})
                        render_options_base = {**fp_opts, **render_options_base}
                        poster_filter = render_options_base.get("poster_filter", poster_filter)
                        logo_preference = render_options_base.get("logo_preference", logo_preference)
                        logo_mode = render_options_base.get("logo_mode", logo_mode)
                        preset_id = fallback_preset
                    else:
                        logger.warning("[BATCH] Fallback preset '%s' not found for template '%s'", fallback_preset, fallback_template)
                poster = posters[0] if posters else None
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
        # Logo fallback handling
        if not logo and logo_mode != "none":
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
                        render_options_base = {**fp_opts, **render_options_base}
                        poster_filter = render_options_base.get("poster_filter", poster_filter)
                        logo_preference = render_options_base.get("logo_preference", logo_preference)
                        logo_mode = render_options_base.get("logo_mode", logo_mode)
                        preset_id = fallback_logo_preset
                    else:
                        logger.warning("[BATCH] Fallback logo preset '%s' not found for template '%s'", fallback_logo_preset, fallback_logo_template)
            elif fallback_logo_action == "skip":
                return {
                    "rating_key": rating_key,
                    "status": "skipped_no_logo"
                }
            # else continue without logo

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

        img = render_poster_image(
            template_id,
            poster_url,
            logo_url if logo_mode != "none" else None,
            render_options,
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

                img_rgb.save(save_path, "JPEG", quality=95, exif=exif_bytes)

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
            img.convert("RGB").save(buf, "JPEG", quality=95)
            payload = buf.getvalue()

            plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
            headers = {
                "X-Plex-Token": settings.PLEX_TOKEN,
                "Content-Type": "image/jpeg",
            }

            r = requests.post(plex_url, headers=headers, data=payload, timeout=20)
            r.raise_for_status()

            # Label removal
            for label in req.labels or []:
                plex_remove_label(rating_key, label)

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
    base_logo_preference = base_options.get("logo_preference", "first")
    base_logo_mode = base_options.get("logo_mode", "stock")
    if req.preset_id:
        if req.template_id in presets_data:
            preset_list = presets_data[req.template_id]["presets"]
            preset = next((p for p in preset_list if p["id"] == req.preset_id), None)
            if preset:
                preset_opts = preset.get("options", {})
                base_options = {**preset_opts, **base_options}
                base_poster_filter = base_options.get("poster_filter", base_poster_filter)
                base_logo_preference = base_options.get("logo_preference", base_logo_preference)
                base_logo_mode = base_options.get("logo_mode", base_logo_mode)
                logger.debug("[BATCH] Applied preset '%s' options for template '%s'", req.preset_id, req.template_id)
            else:
                logger.warning("[BATCH] Preset '%s' not found for template '%s'", req.preset_id, req.template_id)
        else:
            logger.warning("[BATCH] Template '%s' not found in presets", req.template_id)

    # Process movies concurrently using ThreadPoolExecutor
    logger.info("[BATCH] Processing %d movies with %d concurrent workers", len(req.rating_keys), max_workers)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_idx = {}
        for idx, rating_key in enumerate(req.rating_keys, start=1):
            future = executor.submit(
                _process_single_movie,
                idx,
                rating_key,
                req,
                base_options,
                base_poster_filter,
                base_logo_preference,
                base_logo_mode,
                presets_data,
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
