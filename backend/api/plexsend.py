import requests
from fastapi import APIRouter, HTTPException
from io import BytesIO

from ..config import settings, plex_headers, plex_remove_label, logger
from ..rendering import render_poster_image
from ..schemas import PlexSendRequest

router = APIRouter()


@router.post("/plex/send")
def api_plex_send(req: PlexSendRequest):
    # Validate Plex settings
    if not settings.PLEX_URL or not settings.PLEX_TOKEN:
        raise HTTPException(400, "PLEX_URL and PLEX_TOKEN must be set.")

    # Allow ANY URL (TMDB, uploaded, custom)
    if not (
        req.background_url.startswith("http://")
        or req.background_url.startswith("https://")
        or req.background_url.startswith("/uploads/")
    ):
        raise HTTPException(400, "Invalid background_url")

    # Render poster using template + preset
    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        req.options,
    )

    # Encode for Plex
    buf = BytesIO()
    img.convert("RGB").save(buf, "JPEG", quality=95)
    payload = buf.getvalue()

    plex_url = f"{settings.PLEX_URL}/library/metadata/{req.rating_key}/posters"
    headers = {
        "X-Plex-Token": settings.PLEX_TOKEN,
        "Content-Type": "image/jpeg",
    }

    logger.info("[PLEX] Uploading poster rating_key=%s template=%s preset=%s", req.rating_key, req.template_id, req.preset_id)
    try:
        r = requests.post(plex_url, headers=headers, data=payload, timeout=20)
        r.raise_for_status()
    except Exception as e:
        logger.error("[PLEX] Upload failed rating_key=%s err=%s", req.rating_key, e)
        raise

    # Remove labels if requested
    for label in req.labels or []:
        plex_remove_label(req.rating_key, label)

    logger.info(f"Sent poster to Plex for ratingKey={req.rating_key}")
    return {"status": "ok"}
