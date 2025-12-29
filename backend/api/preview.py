from fastapi import APIRouter, HTTPException
from io import BytesIO
import time

from ..config import logger, load_presets, get_movie_tmdb_id
from ..rendering import render_poster_image, render_with_overlay_cache
from ..schemas import PreviewRequest
from ..tmdb_client import get_images_for_movie, get_movie_details
from ..assets.selection import pick_poster, pick_logo
from ..logo_sources import get_logos_merged

router = APIRouter()

@router.post("/preview")
def api_preview(req: PreviewRequest):
    ui_settings_data = None
    use_overlay_cache = True  # Overlay cache enabled by default
    start_time = time.perf_counter()

    try:
        from .. import database as db
        ui_settings_data = db.get_ui_settings()
        if ui_settings_data:
            use_overlay_cache = ui_settings_data.get("performance", {}).get("useOverlayCache", True)
            logger.info(f"[PREVIEW] Global overlay cache setting: {use_overlay_cache}")
        else:
            logger.info("[PREVIEW] No UI settings found, using default: overlay cache enabled")
    except Exception as e:
        logger.warning(f"[PREVIEW] Failed to load UI settings: {e}")
        pass

    try:
        # Load preset options if preset_id is provided
        render_options = dict(req.options or {})
        # Allow explicit fallback fields/logo source to come through even when options are empty
        explicit_overrides = {
            "fallbackPosterAction": req.fallbackPosterAction,
            "fallbackPosterTemplate": req.fallbackPosterTemplate,
            "fallbackPosterPreset": req.fallbackPosterPreset,
            "fallbackLogoAction": req.fallbackLogoAction,
            "fallbackLogoTemplate": req.fallbackLogoTemplate,
            "fallbackLogoPreset": req.fallbackLogoPreset,
            "logoSource": req.logoSource,
        }
        for key, value in explicit_overrides.items():
            if value is not None and key not in render_options:
                render_options[key] = value
        poster_filter = "all"
        logo_preference = render_options.get("logo_preference") or render_options.get("logo_mode") or "first"
        template_id = req.template_id

        if req.preset_id:
            logger.info("[PREVIEW] Loading preset '%s' for template '%s'", req.preset_id, template_id)
            logger.info("[PREVIEW] Incoming request options keys: %s", list(render_options.keys()))
            logger.info("[PREVIEW] season_text in request: %s", render_options.get("season_text"))
            presets = load_presets()

            if template_id in presets:
                preset_list = presets[template_id]["presets"]
                preset = next((p for p in preset_list if p["id"] == req.preset_id), None)

                if preset:
                    # Decide whether to use season-specific options based on season_text
                    is_season = False
                    try:
                        st = (render_options.get("season_text") or "").strip()
                        is_season = len(st) > 0
                    except Exception:
                        is_season = False

                    # Prefer season_options when rendering a season target
                    if is_season and isinstance(preset.get("season_options"), dict):
                        preset_options = preset.get("season_options", {})
                        logger.info("[PREVIEW] Using season_options for preset '%s' (season_text='%s')", req.preset_id, st)
                        logger.info("[PREVIEW] season_options from DB: text_overlay_enabled=%s custom_text=%s logo_mode=%s", 
                                    preset_options.get("text_overlay_enabled"), 
                                    preset_options.get("custom_text"), 
                                    preset_options.get("logo_mode"))
                    else:
                        preset_options = preset.get("options", {})
                        logger.info("[PREVIEW] Using regular options for preset '%s' (is_season=%s)", req.preset_id, is_season)
                    
                    # Remove deprecated disableOverlayCache flag from preset options
                    # (overlay cache now respects global settings)
                    if "disableOverlayCache" in preset_options:
                        del preset_options["disableOverlayCache"]
                        logger.info("[PREVIEW] Removed deprecated disableOverlayCache flag from preset '%s'", req.preset_id)
                    
                    # Merge preset options (request options take precedence so sliders work)
                    render_options = {**preset_options, **render_options}
                    poster_filter = render_options.get("poster_filter", preset_options.get("poster_filter", "all"))
                    logo_preference = render_options.get("logo_preference") or render_options.get("logo_mode") or preset_options.get("logo_preference") or preset_options.get("logo_mode") or "first"
                    logger.debug("[PREVIEW] Applied preset '%s' options (is_season=%s): %s", req.preset_id, is_season, preset_options)
                    logger.info("[PREVIEW] Effective opts: text_overlay_enabled=%s custom_text=%s logo_mode=%s", render_options.get("text_overlay_enabled"), render_options.get("custom_text"), render_options.get("logo_mode"))
                    logo_override = render_options.get("logo_url") or render_options.get("logoUrl")
                    if logo_override:
                        logo_url = logo_override
                else:
                    logger.warning("[PREVIEW] Preset '%s' not found for template '%s'", req.preset_id, template_id)
            else:
                logger.warning("[PREVIEW] Template '%s' not found in presets", template_id)

        # Add movie details to options for template variable substitution
        if req.movie_title:
            render_options["movie_title"] = req.movie_title
        if req.movie_year:
            render_options["movie_year"] = str(req.movie_year)

        # Allow per-request opt-out of overlay cache for live editing
        # Only disable cache if explicitly requested; respect global setting otherwise
        disable_overlay_cache = render_options.get("disableOverlayCache")
        if req.disableOverlayCache is not None:
            disable_overlay_cache = req.disableOverlayCache
        
        if disable_overlay_cache is True:  # Explicitly True, not just falsy
            use_overlay_cache = False
            logger.info(f"[PREVIEW] Overlay cache disabled via preset/request flag (disableOverlayCache={disable_overlay_cache})")
        else:
            logger.info(f"[PREVIEW] Using global overlay cache setting: {use_overlay_cache}")

        # If background_url contains a rating key pattern, try TMDB lookup
        background_url = req.background_url
        logo_url = req.logo_url

        # Check if this is a Plex URL or API URL - if so, extract rating key and fetch from TMDB
        rating_key = None
        if "/library/metadata/" in background_url and "/thumb" in background_url:
            # Plex URL format
            rating_key = background_url.split("/library/metadata/")[1].split("/")[0]
        elif "/api/movie/" in background_url and "/poster" in background_url:
            # API URL format: /api/movie/{rating_key}/poster
            rating_key = background_url.split("/api/movie/")[1].split("/")[0]

        if rating_key:
            try:
                logger.debug("[PREVIEW] Detected rating_key=%s from URL", rating_key)

                # Get TMDB ID
                tmdb_id = get_movie_tmdb_id(rating_key)
                if tmdb_id:
                    logger.debug("[PREVIEW] Found tmdb_id=%s for rating_key=%s", tmdb_id, rating_key)

                    # Fetch TMDB images (respect language preference with original language fallback)
                    movie_details = get_movie_details(tmdb_id)
                    imgs = get_images_for_movie(tmdb_id, movie_details.get("original_language"))
                    posters = imgs.get("posters", [])

                    # Get logos using merged sources based on preference
                    logo_source_pref = render_options.get("logoSource") or render_options.get("logo_source")
                    logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)

                    # Pick poster based on filter
                    poster = pick_poster(posters, poster_filter)
                    poster_fallback_action_used = None

                    # Poster fallback handling (precedes any logo fallback)
                    if not poster:
                        fallback_action = render_options.get("fallbackPosterAction") or "continue"
                        poster_fallback_action_used = fallback_action
                        fallback_poster_template = render_options.get("fallbackPosterTemplate")
                        fallback_poster_preset = render_options.get("fallbackPosterPreset")
                        if fallback_action == "template" and fallback_poster_template:
                            presets = load_presets()
                            tpl_presets = presets.get(fallback_poster_template, {}).get("presets", [])
                            fpreset = next((p for p in tpl_presets if p.get("id") == fallback_poster_preset), None) if fallback_poster_preset else None
                            if fpreset:
                                fp_opts = fpreset.get("options", {})
                                # Merge fallback preset options, letting fallback override current options to mirror batch behavior
                                render_options = {**render_options, **fp_opts}
                                poster_filter = render_options.get("poster_filter", poster_filter)
                                logo_preference = render_options.get("logo_preference") or render_options.get("logo_mode") or logo_preference
                                logo_mode = render_options.get("logo_mode", "first")
                                template_id = fallback_poster_template
                                logo_source_pref = render_options.get("logoSource") or render_options.get("logo_source")
                                logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"), tmdb_imgs=imgs)
                            else:
                                logger.warning("[PREVIEW] Fallback poster preset '%s' not found for template '%s'", fallback_poster_preset, fallback_poster_template)
                            # Re-pick poster with updated filter from fallback preset (or same filter if no preset options)
                            poster = pick_poster(posters, poster_filter)
                        elif fallback_action == "skip":
                            raise HTTPException(status_code=400, detail="Poster fallback is set to skip (no poster found).")
                        else:  # continue
                            poster = posters[0] if posters else None

                    if poster:
                        background_url = poster.get("url")
                        logger.info("[PREVIEW] Picked TMDB poster with filter='%s': %s", poster_filter, background_url)
                    else:
                        raise HTTPException(status_code=404, detail="No valid poster found (even after fallback).")

                    # Pick logo based on preference (only if logo_mode is not 'none')
                    logo_mode = render_options.get("logo_mode", "first")
                    allow_logo_fallback = poster_fallback_action_used in (None, "continue")
                    if not logo_url and logo_mode != "none":
                        logo = pick_logo(logos, logo_preference)

                        # If no logo, try fallback template/preset (append mode, similar to batch) — only when poster allowed it
                        if not logo and allow_logo_fallback:
                            logger.info(
                                "[PREVIEW] No logo before fallback; action=%s template=%s preset=%s logos=%s",
                                render_options.get("fallbackLogoAction"),
                                render_options.get("fallbackLogoTemplate"),
                                render_options.get("fallbackLogoPreset"),
                                len(logos) if logos is not None else "n/a",
                            )
                            fallback_logo_action = render_options.get("fallbackLogoAction") or "continue"
                            fallback_logo_template = render_options.get("fallbackLogoTemplate")
                            fallback_logo_preset = render_options.get("fallbackLogoPreset")
                            if fallback_logo_action == "template" and fallback_logo_template:
                                presets = load_presets()
                                tpl_presets = presets.get(fallback_logo_template, {}).get("presets", [])
                                fpreset = next((p for p in tpl_presets if p.get("id") == fallback_logo_preset), None) if fallback_logo_preset else None
                                if fpreset:
                                    fp_opts = fpreset.get("options", {})
                                    # Merge fallback preset options, letting fallback override current options
                                    # to mirror batch behavior and ensure template-specific settings (e.g., text overlay)
                                    # take effect. Request-supplied transient sliders can still override both.
                                    render_options = {**render_options, **fp_opts}
                                    poster_filter = render_options.get("poster_filter", poster_filter)
                                    logo_preference = render_options.get("logo_preference") or render_options.get("logo_mode") or logo_preference
                                    logo_mode = render_options.get("logo_mode", logo_mode)
                                    template_id = fallback_logo_template
                                    logo_source_pref = render_options.get("logoSource") or render_options.get("logo_source")
                                    logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"))
                                    # If fallback preset provides a static logo URL, use it directly
                                    logo_override = render_options.get("logo_url") or render_options.get("logoUrl")
                                    if logo_override:
                                        logo_url = logo_override
                                        logo = None
                                    if logo_url is None:
                                        logo = pick_logo(logos, logo_preference)
                                    if logo:
                                        logger.info("[PREVIEW] Fallback logo from template '%s' preset '%s'", fallback_logo_template, fallback_logo_preset)
                                else:
                                    logger.warning("[PREVIEW] Fallback logo preset '%s' not found for template '%s'", fallback_logo_preset, fallback_logo_template)
                            elif fallback_logo_action == "skip":
                                logger.info("[PREVIEW] Skipping logo due to fallback action 'skip'")
                            # else: continue without logo
                        elif not logo and not allow_logo_fallback:
                            logger.info("[PREVIEW] Skipping logo fallback because poster fallback action was '%s'", poster_fallback_action_used)

                        if logo:
                            logo_url = logo.get("url")
                            logger.info("[PREVIEW] Picked TMDB logo with preference='%s': %s", logo_preference, logo_url)
                    elif logo_mode == "none":
                        logger.debug("[PREVIEW] Skipping logo fetch because logo_mode='none'")
                else:
                    logger.warning("[PREVIEW] Could not find TMDB ID for rating_key=%s", rating_key)
            except Exception as e:
                logger.warning("[PREVIEW] TMDB lookup failed, using original URL: %s", e)

        logo_mode_val = render_options.get("logo_mode", "first")
        effective_logo_url = None if logo_mode_val == "none" else logo_url

        if req.preset_id:
            img = render_with_overlay_cache(
                template_id,
                req.preset_id,
                background_url,
                effective_logo_url,
                render_options,
                use_cache=use_overlay_cache,
            )
        else:
            img = render_poster_image(
                template_id,
                background_url,
                effective_logo_url,
                render_options,
            )

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "[PREVIEW] Render time %.1f ms template=%s preset=%s cache=%s",
            elapsed_ms,
            template_id,
            req.preset_id or "none",
            "on" if use_overlay_cache else "off",
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid background image.")
    except Exception:
        logger.exception("Preview render failed")
        raise HTTPException(status_code=500, detail="Preview failed.")

    buf = BytesIO()
    # Get JPEG quality from settings
    quality = 95
    try:
        if ui_settings_data and "imageQuality" in ui_settings_data:
            quality = ui_settings_data["imageQuality"].get("jpgQuality", 95)
        elif ui_settings_data is None:
            from .. import database as db
            ui_settings_data = db.get_ui_settings()
            if ui_settings_data and "imageQuality" in ui_settings_data:
                quality = ui_settings_data["imageQuality"].get("jpgQuality", 95)
    except Exception:
        pass
    img.convert("RGB").save(buf, "JPEG", quality=quality)

    import base64
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}
