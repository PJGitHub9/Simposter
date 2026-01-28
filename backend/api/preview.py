from fastapi import APIRouter, HTTPException
from io import BytesIO
import time
import sqlite3

from ..config import logger, load_presets, get_movie_tmdb_id
from ..rendering import render_poster_image, render_with_overlay_cache
from ..schemas import PreviewRequest
from ..tmdb_client import get_images_for_movie, get_movie_details
from ..assets.selection import pick_poster, pick_logo, map_logo_mode_to_preference
from ..logo_sources import get_logos_merged
from ..middleware.validation import (
    validate_template_id,
    validate_preset_id,
    validate_url,
    validate_options
)

router = APIRouter()

@router.post("/preview")
def api_preview(req: PreviewRequest):
    # Input validation
    try:
        if req.template_id:
            req.template_id = validate_template_id(req.template_id)
        if req.preset_id:
            req.preset_id = validate_preset_id(req.preset_id)
        if req.background_url:
            req.background_url = validate_url(req.background_url, allow_data_uri=True)
        if req.logo_url:
            req.logo_url = validate_url(req.logo_url, allow_data_uri=True)
        if req.options:
            req.options = validate_options(req.options)
    except HTTPException:
        raise  # Re-raise validation errors
    except Exception as e:
        logger.error(f"[PREVIEW] Validation error: {e}")
        raise HTTPException(status_code=400, detail=f"Validation error: {str(e)}")

    ui_settings_data = None
    use_overlay_cache = True  # Overlay cache enabled by default
    white_logo_fallback = "use_next"  # Default fallback behavior
    language_pref = "en"  # Default language preference
    start_time = time.perf_counter()

    try:
        from .. import database as db
        ui_settings_data = db.get_ui_settings()
        if ui_settings_data:
            use_overlay_cache = ui_settings_data.get("performance", {}).get("useOverlayCache", True)
            logger.info(f"[PREVIEW] Global overlay cache setting: {use_overlay_cache}")
        else:
            logger.info("[PREVIEW] No UI settings found, using default: overlay cache enabled")

        # Load white logo fallback setting
        white_logo_fallback = db.get_setting("fallback.white_logo_fallback") or "use_next"
        logger.debug(f"[PREVIEW] White logo fallback setting: {white_logo_fallback}")

        # Load language preference
        language_pref = db.get_setting("pref.language") or "en"
        logger.debug(f"[PREVIEW] Language preference: {language_pref}")
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
        # Map logo_mode values (like "original") to valid pick_logo preferences (like "white")
        logo_preference = map_logo_mode_to_preference(logo_preference)

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
                    except (AttributeError, TypeError) as e:
                        logger.debug("Failed to parse season_text: %s", e)
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
                    logo_preference = map_logo_mode_to_preference(logo_preference)
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

        # Merge top-level fallback fields from request into render_options
        # Only add if not already present (preset values take precedence)
        if req.fallbackPosterAction and "fallbackPosterAction" not in render_options:
            render_options["fallbackPosterAction"] = req.fallbackPosterAction
        if req.fallbackPosterTemplate and "fallbackPosterTemplate" not in render_options:
            render_options["fallbackPosterTemplate"] = req.fallbackPosterTemplate
        if req.fallbackPosterPreset and "fallbackPosterPreset" not in render_options:
            render_options["fallbackPosterPreset"] = req.fallbackPosterPreset
        if req.fallbackLogoAction and "fallbackLogoAction" not in render_options:
            render_options["fallbackLogoAction"] = req.fallbackLogoAction
        if req.fallbackLogoTemplate and "fallbackLogoTemplate" not in render_options:
            render_options["fallbackLogoTemplate"] = req.fallbackLogoTemplate
        if req.fallbackLogoPreset and "fallbackLogoPreset" not in render_options:
            render_options["fallbackLogoPreset"] = req.fallbackLogoPreset

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

        logger.debug("[PREVIEW] background_url=%s logo_url=%s", background_url[:100] if background_url else None, logo_url)

        # Check if this is a Plex URL or API URL - if so, extract rating key and fetch from TMDB
        rating_key = None
        is_tv_show = False
        if background_url:
            if "/library/metadata/" in background_url and "/thumb" in background_url:
                # Plex URL format
                rating_key = background_url.split("/library/metadata/")[1].split("/")[0]
            elif "/api/movie/" in background_url and "/poster" in background_url:
                # API URL format: /api/movie/{rating_key}/poster
                rating_key = background_url.split("/api/movie/")[1].split("/")[0]
            elif "/api/tv-show/" in background_url and "/poster" in background_url:
                # API URL format: /api/tv-show/{rating_key}/poster
                rating_key = background_url.split("/api/tv-show/")[1].split("/")[0]
                is_tv_show = True

        # Also check if tv_show_rating_key was explicitly provided
        if req.tv_show_rating_key and not rating_key:
            rating_key = req.tv_show_rating_key
            is_tv_show = True
            logger.debug("[PREVIEW] Using explicitly provided TV show rating_key=%s", rating_key)

        logger.debug("[PREVIEW] Detected rating_key=%s is_tv_show=%s", rating_key, is_tv_show)

        if rating_key and not is_tv_show:
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

                    # Poster fallback handling
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
                                logo_preference = map_logo_mode_to_preference(logo_preference)
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
                    # Disable logo fallback only if poster fallback was actually used
                    # (not just configured - only when it actually triggered)
                    allow_logo_fallback = poster_fallback_action_used in (None, "continue")
                    if not logo_url and logo_mode != "none":
                        logo = pick_logo(logos, logo_preference, white_logo_fallback, language_pref)

                        # If no logo, try logo fallback — only if poster fallback wasn't already used
                        # (poster fallback takes precedence when it triggers)
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
                                    logo_preference = map_logo_mode_to_preference(logo_preference)
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
                                        logo = pick_logo(logos, logo_preference, white_logo_fallback, language_pref)
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
                    logger.warning("[PREVIEW] Could not find TMDB ID for rating_key=%s, trying Plex poster", rating_key)
                    # Fallback: Try Plex poster directly
                    if not background_url:
                        try:
                            from ..config import settings as config_settings
                            plex_base = config_settings.PLEX_URL.rstrip('/')
                            plex_poster_url = f"{plex_base}/library/metadata/{rating_key}/thumb?X-Plex-Token={config_settings.PLEX_TOKEN}"
                            background_url = plex_poster_url
                            logger.info("[PREVIEW] Using Plex poster as fallback for movie: %s", plex_poster_url.split('?')[0])
                        except Exception as plex_err:
                            logger.warning("[PREVIEW] Failed to construct Plex poster URL: %s", plex_err)
            except Exception as e:
                logger.warning("[PREVIEW] TMDB lookup failed: %s", e)
                # Fallback: try to fetch poster directly from Plex
                if not background_url and rating_key:
                    try:
                        from ..config import settings as config_settings
                        plex_base = config_settings.PLEX_URL.rstrip('/')
                        plex_poster_url = f"{plex_base}/library/metadata/{rating_key}/thumb?X-Plex-Token={config_settings.PLEX_TOKEN}"
                        background_url = plex_poster_url
                        logger.info("[PREVIEW] Using Plex poster as fallback after error: %s", plex_poster_url.split('?')[0])
                    except Exception as plex_err:
                        logger.warning("[PREVIEW] Failed to construct Plex poster URL: %s", plex_err)

        elif rating_key and is_tv_show:
            # Handle TV show logo and poster fetching (including seasons)
            try:
                from ..config import settings as config_settings, plex_session, plex_headers
                from ..config import extract_tmdb_id_from_metadata, extract_tvdb_id_from_metadata
                from ..tmdb_client import get_tv_show_details, get_images_for_tv_show, get_tv_external_ids, get_tv_season_images
                from .. import tvdb_client
                from ..fanart_client import get_images_for_tv_show as get_fanart_tv_images

                logger.debug("[PREVIEW] Detected TV show rating_key=%s season_index=%s from URL", rating_key, req.season_index)

                # Fetch TV show metadata from Plex
                url = f"{config_settings.PLEX_URL}/library/metadata/{rating_key}"
                r = plex_session.get(url, headers=plex_headers(), timeout=6)
                r.raise_for_status()

                tmdb_id = extract_tmdb_id_from_metadata(r.text)
                tvdb_id = extract_tvdb_id_from_metadata(r.text)

                if tmdb_id and not tvdb_id:
                    try:
                        external_ids = get_tv_external_ids(tmdb_id)
                        tvdb_id = external_ids.get("tvdb_id") or external_ids.get("id")
                    except Exception:
                        pass

                if tmdb_id:
                    logger.debug("[PREVIEW] Found TV show tmdb_id=%s for rating_key=%s", tmdb_id, rating_key)

                    # Get TV show details and images
                    show_details = get_tv_show_details(tmdb_id)
                    original_language = show_details.get("original_language")

                    # Only fetch posters if background_url is not already a direct image URL
                    # (Frontend may have already selected a specific poster via /select-poster endpoint)
                    should_fetch_poster = not background_url or background_url.startswith(config_settings.PLEX_URL) or "/api/" in background_url

                    if should_fetch_poster:
                        # Fetch series or season posters based on season_index
                        posters = []
                        if req.season_index is not None:
                            # Fetch season posters
                            logger.info("[PREVIEW] Fetching season %d poster for tmdb_id=%s", req.season_index, tmdb_id)
                            try:
                                season_imgs = get_tv_season_images(tmdb_id, req.season_index, original_language)
                                posters = season_imgs.get("posters", [])
                            except Exception as e:
                                logger.warning("[PREVIEW] Failed to fetch season %d images: %s", req.season_index, e)
                                posters = []  # Empty list will trigger series fallback logic below
                        else:
                            # Fetch series posters
                            show_imgs = get_images_for_tv_show(tmdb_id, original_language)
                            posters = show_imgs.get("posters", [])

                        # Pick poster based on filter
                        poster = pick_poster(posters, poster_filter)
                        poster_fallback_action_used = None

                        # Poster fallback handling
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
                                    # Use season_options if this is a season poster, otherwise use regular options
                                    if req.season_index is not None and "season_options" in fpreset:
                                        fp_opts = fpreset.get("season_options", {})
                                        logger.debug("[PREVIEW] Using season_options from fallback preset")
                                    else:
                                        fp_opts = fpreset.get("options", {})
                                    render_options = {**render_options, **fp_opts}
                                    # NOTE: Don't update poster_filter here - we already tried with the original filter and failed
                                    # The fallback template will be used to render whatever poster we find below
                                    logo_preference = render_options.get("logo_preference") or render_options.get("logo_mode") or logo_preference
                                    logo_preference = map_logo_mode_to_preference(logo_preference)
                                    template_id = fallback_poster_template
                                    req.preset_id = fallback_poster_preset  # Update preset_id to match fallback
                                    logger.info("[PREVIEW] Applied poster fallback: %s/%s", fallback_poster_template, fallback_poster_preset)
                                    # After switching to fallback template, try to get ANY available poster
                                    poster = pick_poster(posters, "all")
                                    if poster:
                                        logger.info("[PREVIEW] Using fallback poster from TMDB after template switch")
                                else:
                                    logger.warning("[PREVIEW] Fallback poster preset '%s' not found for template '%s'", fallback_poster_preset, fallback_poster_template)
                            elif fallback_action == "skip":
                                raise HTTPException(status_code=400, detail="Poster fallback is set to skip (no poster found).")
                            else:  # continue
                                # Re-pick with "all" filter to get any available poster
                                poster = pick_poster(posters, "all")
                                if not poster:
                                    logger.warning("[PREVIEW] No posters available even with 'all' filter")

                        if poster:
                            background_url = poster.get("url")
                            logger.info("[PREVIEW] Picked TV show poster with filter='%s': %s", poster_filter, background_url)
                        else:
                            # If no season poster found, fall back to series poster as last resort
                            if req.season_index is not None:
                                logger.warning("[PREVIEW] No season %d poster found, falling back to series poster", req.season_index)
                                show_imgs = get_images_for_tv_show(tmdb_id, original_language)
                                series_posters = show_imgs.get("posters", [])
                                series_poster = pick_poster(series_posters, "all")  # Use "all" to get any poster
                                if series_poster:
                                    background_url = series_poster.get("url")
                                    logger.info("[PREVIEW] Using series poster as fallback: %s", background_url)
                                else:
                                    logger.warning("[PREVIEW] No valid TV show poster found (even series poster)")
                            else:
                                logger.warning("[PREVIEW] No valid TV show poster found (even after fallback)")
                    else:
                        # background_url is already a direct image URL (from frontend /select-poster)
                        logger.info("[PREVIEW] Using pre-selected poster URL from frontend: %s", background_url[:100] if background_url else None)

                    # Fetch logos (always from series, not season-specific)
                    show_imgs = get_images_for_tv_show(tmdb_id, original_language)
                    logos = show_imgs.get("logos", [])

                    # Add TVDB logos if available
                    if tvdb_id and config_settings.TVDB_API_KEY:
                        try:
                            tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                            logos.extend(tvdb_imgs.get("logos", []))
                        except Exception as e:
                            logger.warning("[PREVIEW] Failed to fetch TVDB logos: %s", e)

                    # Add Fanart logos if available
                    if tvdb_id and config_settings.FANART_API_KEY:
                        try:
                            fanart_imgs = get_fanart_tv_images(int(tvdb_id))
                            logos.extend(fanart_imgs.get("logos", []))
                        except Exception as e:
                            logger.warning("[PREVIEW] Failed to fetch Fanart logos: %s", e)

                    # Pick logo based on preference (only if logo_mode is not 'none')
                    logo_mode = render_options.get("logo_mode", "first")
                    if not logo_url and logo_mode != "none":
                        logo = pick_logo(logos, logo_preference, white_logo_fallback, language_pref)
                        if logo:
                            logo_url = logo.get("url")
                            logger.info("[PREVIEW] Picked TV show logo with preference='%s': %s", logo_preference, logo_url)
                    elif logo_mode == "none":
                        logger.debug("[PREVIEW] Skipping TV show logo fetch because logo_mode='none'")
                else:
                    logger.warning("[PREVIEW] Could not find TMDB ID for TV show rating_key=%s, trying TVDB", rating_key)
                    # Fallback 1: Try TVDB if we have a tvdb_id
                    if tvdb_id and not background_url:
                        try:
                            logger.info("[PREVIEW] Trying TVDB poster lookup for tvdb_id=%s", tvdb_id)
                            tvdb_imgs = tvdb_client.get_series_images(int(tvdb_id))
                            tvdb_posters = tvdb_imgs.get("posters", [])
                            if tvdb_posters:
                                poster = pick_poster(tvdb_posters, poster_filter)
                                if poster:
                                    background_url = poster.get("url")
                                    logger.info("[PREVIEW] Using TVDB poster: %s", background_url)
                                else:
                                    # Try any poster
                                    background_url = tvdb_posters[0].get("url") if tvdb_posters else None
                                    if background_url:
                                        logger.info("[PREVIEW] Using first TVDB poster: %s", background_url)
                            # Also try to get logos from TVDB
                            tvdb_logos = tvdb_imgs.get("logos", [])
                            if tvdb_logos and not logo_url:
                                logo = pick_logo(tvdb_logos, logo_preference, white_logo_fallback, language_pref)
                                if logo:
                                    logo_url = logo.get("url")
                                    logger.info("[PREVIEW] Using TVDB logo: %s", logo_url)
                        except Exception as tvdb_err:
                            logger.warning("[PREVIEW] TVDB lookup failed: %s", tvdb_err)

                    # Fallback 2: Try Plex poster directly
                    if not background_url:
                        try:
                            plex_base = config_settings.PLEX_URL.rstrip('/')
                            plex_poster_url = f"{plex_base}/library/metadata/{rating_key}/thumb?X-Plex-Token={config_settings.PLEX_TOKEN}"
                            background_url = plex_poster_url
                            logger.info("[PREVIEW] Using Plex poster as fallback: %s", plex_poster_url.split('?')[0])
                        except Exception as plex_err:
                            logger.warning("[PREVIEW] Failed to construct Plex poster URL: %s", plex_err)
            except Exception as e:
                logger.warning("[PREVIEW] TV show lookup failed: %s", e)
                # Fallback: try to fetch poster directly from Plex
                if not background_url and rating_key:
                    try:
                        from ..config import settings as config_settings
                        plex_base = config_settings.PLEX_URL.rstrip('/')
                        plex_poster_url = f"{plex_base}/library/metadata/{rating_key}/thumb?X-Plex-Token={config_settings.PLEX_TOKEN}"
                        background_url = plex_poster_url
                        logger.info("[PREVIEW] Using Plex poster as fallback after error: %s", plex_poster_url.split('?')[0])
                    except Exception as plex_err:
                        logger.warning("[PREVIEW] Failed to construct Plex poster URL: %s", plex_err)

        # Final check: if we still don't have a background_url, raise a clear error
        if not background_url:
            logger.error("[PREVIEW] No background URL available after all lookups (rating_key=%s, is_tv=%s)", rating_key, is_tv_show)
            raise HTTPException(status_code=400, detail="Could not find a poster image. Check that the item has a valid TMDB/TVDB ID or Plex poster.")

        logo_mode_val = render_options.get("logo_mode", "first")
        effective_logo_url = None if logo_mode_val == "none" else logo_url

        # Use overlay cache only if we have a background_url (can't use cache when fetching from TMDb)
        if req.preset_id and background_url:
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
    except (ImportError, AttributeError, KeyError, sqlite3.Error) as e:
        logger.debug("Failed to load image quality settings: %s", e)
    img.convert("RGB").save(buf, "JPEG", quality=quality)

    import base64
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}
