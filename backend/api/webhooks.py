from fastapi import APIRouter, HTTPException
from ..schemas import RadarrWebhook
from ..config import (
    logger,
    settings,
    plex_remove_label,
    get_movie_tmdb_id,
    find_rating_key_by_title_year,
)
from ..tmdb_client import get_images_for_movie, get_movie_details
from backend.assets.selection import pick_poster, pick_logo
from ..rendering import render_poster_image
from io import BytesIO
import requests
from .presets import load_presets

router = APIRouter()


@router.post("/webhook/radarr/{template_id}/{preset_id}")
def api_webhook_radarr(template_id: str, preset_id: str, req: RadarrWebhook):

    logger.info("[RADARR] Webhook triggered")
    logger.info(f"Event: {req.eventType}")
    logger.info(f"Movie: {req.movie.title} ({req.movie.year})")

    # 1) TMDb ID
    if not req.movie.tmdbId:
        # Radarr's built-in test payload often omits tmdbId; allow the test to pass with a no-op render.
        if str(req.eventType).lower() == "test":
            return {
                "status": "ok",
                "poster_used": None,
                "logo_used": None,
                "image_bytes": 0,
                "sent_to_plex": False,
                "rating_key": None,
                "plex_error": "tmdbId missing in test payload (skipped render)",
            }
        raise HTTPException(400, "TMDb ID missing in Radarr payload")

    tmdb_id = req.movie.tmdbId

    # 2) Fetch images and movie details from TMDb
    imgs = get_images_for_movie(tmdb_id)
    posters = imgs.get("posters", [])
    logos = imgs.get("logos", [])

    if not posters:
        raise HTTPException(400, "No posters available from TMDb")

    # Fetch movie details for template variables
    movie_details = get_movie_details(tmdb_id)
    logger.debug("[RADARR] Movie details: title='%s' year=%s", movie_details.get("title"), movie_details.get("year"))

    # 3) Load preset
    #from ..presets import load_presets  # lazy import
    presets = load_presets()

    # Validate template
    if template_id not in presets:
        raise HTTPException(400, f"Unknown template '{template_id}'")

    # Validate preset
    preset_list = presets[template_id]["presets"]
    preset = next((p for p in preset_list if p["id"] == preset_id), None)

    if not preset:
        raise HTTPException(400, f"Unknown preset '{preset_id}'")

    options = preset["options"]

    # Poster + logo selection
    poster_filter = options.get("poster_filter", "all")
    logo_pref = options.get("logo_preference", "first")

    poster = pick_poster(posters, poster_filter)
    logo = pick_logo(logos, logo_pref)

    poster_url = poster.get("url") if poster else None
    logo_url = logo.get("url") if logo else None

    logger.debug(
        "[RADARR] tmdb_id=%s posters=%d logos=%d filter=%s logo_pref=%s",
        tmdb_id,
        len(posters),
        len(logos),
        poster_filter,
        logo_pref,
    )
    logger.info(f"[RADARR] Picked poster = {poster_url}")
    logger.info(f"[RADARR] Picked logo   = {logo_url}")

    # 4) Render
    # Add movie details to options for template variable substitution
    render_options = dict(options)
    render_options["movie_title"] = movie_details.get("title", "")
    render_options["movie_year"] = movie_details.get("year", "")

    img = render_poster_image(
        template_id,
        poster_url,
        logo_url,
        render_options,
    )

    # 5) Upload to Plex (if available)
    # Radarr doesn't give a Plex rating_key — skip upload unless you want lookup logic
    # For now: just return the image encoded

    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)
    payload = buf.getvalue()

    sent_to_plex = False
    rating_key = None
    plex_error = None

    # Optional auto-send to Plex (best-effort)
    if settings.WEBHOOK_AUTO_SEND:
        try:
            rating_key = find_rating_key_by_title_year(req.movie.title, req.movie.year)
            if rating_key:
                plex_url = f"{settings.PLEX_URL}/library/metadata/{rating_key}/posters"
                headers = {
                    "X-Plex-Token": settings.PLEX_TOKEN,
                    "Content-Type": "image/jpeg",
                }
                r = requests.post(plex_url, headers=headers, data=payload, timeout=20)
                r.raise_for_status()

                # Remove labels if configured
                labels_raw = settings.WEBHOOK_AUTO_LABELS or ""
                labels = [s.strip() for s in labels_raw.split(",") if s.strip()]
                for label in labels:
                    plex_remove_label(rating_key, label)

                sent_to_plex = True
                logger.info(f"[RADARR] Sent poster to Plex ratingKey={rating_key}")
            else:
                plex_error = "Could not resolve rating_key from Plex by title/year"
                logger.warning(f"[RADARR] {plex_error}")
        except Exception as e:
            plex_error = str(e)
            logger.warning(f"[RADARR] Plex upload failed: {e}")

    return {
        "status": "ok",
        "poster_used": poster_url,
        "logo_used": logo_url,
        "image_bytes": len(payload),
        "sent_to_plex": sent_to_plex,
        "rating_key": rating_key,
        "plex_error": plex_error,
    }
