from fastapi import APIRouter, HTTPException
from io import BytesIO

from ..config import logger, load_presets, get_movie_tmdb_id
from ..rendering import render_poster_image
from ..schemas import PreviewRequest
from ..tmdb_client import get_images_for_movie
from ..assets.selection import pick_poster, pick_logo

router = APIRouter()

@router.post("/preview")
def api_preview(req: PreviewRequest):
    try:
        # Load preset options if preset_id is provided
        render_options = dict(req.options or {})
        poster_filter = "all"
        logo_preference = "first"

        if req.preset_id:
            presets = load_presets()

            if req.template_id in presets:
                preset_list = presets[req.template_id]["presets"]
                preset = next((p for p in preset_list if p["id"] == req.preset_id), None)

                if preset:
                    # Merge preset options (request options take precedence so sliders work)
                    preset_options = preset.get("options", {})
                    render_options = {**preset_options, **render_options}
                    poster_filter = render_options.get("poster_filter", preset_options.get("poster_filter", "all"))
                    logo_preference = render_options.get("logo_preference", preset_options.get("logo_preference", "first"))
                    logger.debug("[PREVIEW] Applied preset '%s' options: %s", req.preset_id, preset_options)
                else:
                    logger.warning("[PREVIEW] Preset '%s' not found for template '%s'", req.preset_id, req.template_id)
            else:
                logger.warning("[PREVIEW] Template '%s' not found in presets", req.template_id)

        # Add movie details to options for template variable substitution
        if req.movie_title:
            render_options["movie_title"] = req.movie_title
        if req.movie_year:
            render_options["movie_year"] = str(req.movie_year)

        # If background_url contains a rating key pattern, try TMDB lookup
        background_url = req.background_url
        logo_url = req.logo_url

        # Check if this is a Plex URL - if so, extract rating key and fetch from TMDB
        if "/library/metadata/" in background_url and "/thumb" in background_url:
            try:
                # Extract rating key from Plex URL
                rating_key = background_url.split("/library/metadata/")[1].split("/")[0]
                logger.debug("[PREVIEW] Detected Plex URL, extracting rating_key=%s", rating_key)

                # Get TMDB ID
                tmdb_id = get_movie_tmdb_id(rating_key)
                if tmdb_id:
                    logger.debug("[PREVIEW] Found tmdb_id=%s for rating_key=%s", tmdb_id, rating_key)

                    # Fetch TMDB images
                    imgs = get_images_for_movie(tmdb_id)
                    posters = imgs.get("posters", [])
                    logos = imgs.get("logos", [])

                    # Pick poster based on filter
                    poster = pick_poster(posters, poster_filter)
                    if poster:
                        background_url = poster.get("url")
                        logger.info("[PREVIEW] Picked TMDB poster with filter='%s': %s", poster_filter, background_url)

                    # Pick logo based on preference (only if logo_mode is not 'none')
                    logo_mode = render_options.get("logo_mode", "first")
                    if not logo_url and logo_mode != "none":
                        logo = pick_logo(logos, logo_preference)
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
            req.template_id,
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
