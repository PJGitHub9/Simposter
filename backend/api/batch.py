from fastapi import APIRouter
from ..schemas import BatchRequest
from ..config import settings, plex_remove_label, logger, get_movie_tmdb_id
from ..config import load_presets
from ..tmdb_client import get_images_for_movie, get_movie_details
from ..rendering import render_poster_image
from io import BytesIO
import requests
from backend.assets.selection import pick_poster, pick_logo
from .save import apply_save_location_variables, get_save_location_template

router = APIRouter()


@router.post("/batch")
def api_batch(req: BatchRequest):

    results = []

    # Load preset options if provided
    poster_filter = req.options.get("poster_filter", "all")
    logo_preference = req.options.get("logo_preference", "first")
    logo_mode = req.options.get("logo_mode", "stock")
    render_options_base = dict(req.options or {})
    if req.preset_id:
        presets = load_presets()
        if req.template_id in presets:
            preset_list = presets[req.template_id]["presets"]
            preset = next((p for p in preset_list if p["id"] == req.preset_id), None)
            if preset:
                preset_opts = preset.get("options", {})
                render_options_base = {**preset_opts, **render_options_base}
                poster_filter = render_options_base.get("poster_filter", poster_filter)
                logo_preference = render_options_base.get("logo_preference", logo_preference)
                logo_mode = render_options_base.get("logo_mode", logo_mode)
                logger.debug("[BATCH] Applied preset '%s' options for template '%s'", req.preset_id, req.template_id)
            else:
                logger.warning("[BATCH] Preset '%s' not found for template '%s'", req.preset_id, req.template_id)
        else:
            logger.warning("[BATCH] Template '%s' not found in presets", req.template_id)

    for rating_key in req.rating_keys:
        try:
            logger.info("[BATCH] Start rating_key=%s template=%s", rating_key, req.template_id)

            # ---------------------------
            # TMDb Fetch
            # ---------------------------
            tmdb_id = get_movie_tmdb_id(rating_key)
            if not tmdb_id:
                raise Exception("No TMDb ID found.")
            logger.debug("[BATCH] rating_key=%s tmdb_id=%s", rating_key, tmdb_id)

            imgs = get_images_for_movie(tmdb_id)
            posters = imgs.get("posters", [])
            logos = imgs.get("logos", [])
            logger.debug(
                "[BATCH] rating_key=%s posters=%d logos=%d filter=%s logo_pref=%s",
                rating_key,
                len(posters),
                len(logos),
                poster_filter,
                logo_preference,
            )

            # Fetch movie details for template variables
            movie_details = get_movie_details(tmdb_id)
            logger.debug("[BATCH] Movie details: title='%s' year=%s", movie_details.get("title"), movie_details.get("year"))

            # ---------------------------
            # Auto-select assets
            # ---------------------------
            poster = pick_poster(posters, poster_filter)
            logo = None if str(logo_mode).lower() == "none" else pick_logo(logos, logo_preference)
            
            if not poster:
                raise Exception("No valid poster found.")

            poster_url = poster.get("url")
            logo_url = logo.get("url") if logo else None
            logger.info(f"[BATCH] Picked logo pref={logo_preference}")
            logger.info(f"[BATCH] Picked poster={poster_url}")
            logger.info(f"[BATCH] Picked logo={logo_url}")
            # ---------------------------
            # Render for EACH MOVIE
            # ---------------------------
            # Add movie details to options for template variable substitution
            render_options = dict(render_options_base)
            render_options["movie_title"] = movie_details.get("title", "")
            render_options["movie_year"] = movie_details.get("year", "")

            img = render_poster_image(
                req.template_id,
                poster_url,
                logo_url if logo_mode != "none" else None,
                render_options,
            )

            # ---------------------------
            # Save locally (if requested)
            # ---------------------------
            save_path = None
            if req.save_locally:
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
                        save_template = data.get("saveLocation", save_template)
                        save_batch = bool(data.get("saveBatchInSubfolder", False))
                except Exception:
                    pass

                # Apply variable substitution
                save_path_template = apply_save_location_variables(
                    save_template,
                    movie_details.get("title", rating_key),
                    movie_details.get("year", ""),
                    rating_key,
                )

                # Sanitize path components (keep dots for filenames)
                safe_path = "".join(c for c in save_path_template if c.isalnum() or c in " _-/().")
                safe_path = safe_path.strip()

                candidate = Path(safe_path)
                if candidate.suffix:
                    base_dir = candidate.parent
                    filename = candidate.name
                else:
                    base_dir = candidate
                    filename = f"{movie_details.get('title', rating_key)}"
                    yr = movie_details.get("year", "")
                    if yr:
                        filename += f" ({yr})"
                    filename += ".jpg"

                # Map explicit /output to configured OUTPUT_ROOT
                base_dir_str = str(base_dir).replace("\\", "/")
                if base_dir.is_absolute() and base_dir_str.startswith("/output"):
                    tail = base_dir_str[len("/output"):].lstrip("/")
                    base_dir = Path(settings.OUTPUT_ROOT) / tail

                # Anchor relative paths
                if not base_dir.is_absolute():
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

                img.convert("RGB").save(save_path, "JPEG", quality=95)
                logger.info(f"[BATCH] Saved locally: {save_path}")

            # ---------------------------
            # Upload to Plex (if requested)
            # ---------------------------
            if req.send_to_plex:
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

            result = {
                "rating_key": rating_key,
                "poster_used": poster_url,
                "logo_used": logo_url,
                "status": "ok",
            }
            if save_path:
                result["save_path"] = save_path
            results.append(result)

        except Exception as e:
            logger.error(f"[BATCH] Error for {rating_key}\n{e}")
            results.append({
                "rating_key": rating_key,
                "status": "error",
                "error": str(e),
            })

    return {"results": results}
