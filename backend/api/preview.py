from fastapi import APIRouter, HTTPException
from io import BytesIO

from ..config import logger, load_presets, get_movie_tmdb_id
from ..rendering import render_poster_image
from ..schemas import PreviewRequest
from ..tmdb_client import get_images_for_movie, get_movie_details
from ..assets.selection import pick_poster, pick_logo
from ..logo_sources import get_logos_merged

router = APIRouter()

@router.post("/preview")
def api_preview(req: PreviewRequest):
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
        logo_preference = "first"
        template_id = req.template_id

        if req.preset_id:
            presets = load_presets()

            if template_id in presets:
                preset_list = presets[template_id]["presets"]
                preset = next((p for p in preset_list if p["id"] == req.preset_id), None)

                if preset:
                    # Merge preset options (request options take precedence so sliders work)
                    preset_options = preset.get("options", {})
                    render_options = {**preset_options, **render_options}
                    poster_filter = render_options.get("poster_filter", preset_options.get("poster_filter", "all"))
                    logo_preference = render_options.get("logo_preference", preset_options.get("logo_preference", "first"))
                    logger.debug("[PREVIEW] Applied preset '%s' options: %s", req.preset_id, preset_options)
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
                    logos = get_logos_merged(tmdb_id, logo_source_pref, movie_details.get("original_language"))

                    # Pick poster based on filter
                    poster = pick_poster(posters, poster_filter)
                    if poster:
                        background_url = poster.get("url")
                        logger.info("[PREVIEW] Picked TMDB poster with filter='%s': %s", poster_filter, background_url)

                    # Pick logo based on preference (only if logo_mode is not 'none')
                    logo_mode = render_options.get("logo_mode", "first")
                    if not logo_url and logo_mode != "none":
                        logo = pick_logo(logos, logo_preference)

                        # If no logo, try fallback template/preset (append mode, similar to batch)
                        if not logo:
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
                                    logo_preference = render_options.get("logo_preference", logo_preference)
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

                        if logo:
                            logo_url = logo.get("url")
                            logger.info("[PREVIEW] Picked TMDB logo with preference='%s': %s", logo_preference, logo_url)
                    elif logo_mode == "none":
                        logger.debug("[PREVIEW] Skipping logo fetch because logo_mode='none'")
                else:
                    logger.warning("[PREVIEW] Could not find TMDB ID for rating_key=%s", rating_key)
            except Exception as e:
                logger.warning("[PREVIEW] TMDB lookup failed, using original URL: %s", e)

        img = render_poster_image(
            template_id,
            background_url,
            logo_url,
            render_options,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid background image.")
    except Exception:
        logger.exception("Preview render failed")
        raise HTTPException(status_code=500, detail="Preview failed.")

    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)

    import base64
    return {"image_base64": base64.b64encode(buf.getvalue()).decode()}
