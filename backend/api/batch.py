from fastapi import APIRouter
from ..schemas import BatchRequest
from ..config import settings, plex_remove_label, logger, get_movie_tmdb_id
from ..tmdb_client import get_images_for_movie
from ..rendering import render_poster_image
from io import BytesIO
import requests
from backend.assets.selection import pick_poster, pick_logo

router = APIRouter()


@router.post("/batch")
def api_batch(req: BatchRequest):

    results = []

    poster_filter = req.options.get("poster_filter", "all")
    logo_preference = req.options.get("logo_preference", "first")

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

            # ---------------------------
            # Auto-select assets
            # ---------------------------
            poster = pick_poster(posters, poster_filter)
            logo = pick_logo(logos, logo_preference)
            
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
            img = render_poster_image(
                req.template_id,
                poster_url,
                logo_url,
                req.options,
            )

            # ---------------------------
            # Upload to Plex
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
            else:
                logger.info("[BATCH] Rendered only (no Plex send) rating_key=%s", rating_key)

            results.append({
                "rating_key": rating_key,
                "poster_used": poster_url,
                "logo_used": logo_url,
                "status": "ok",
            })

        except Exception as e:
            logger.error(f"[BATCH] Error for {rating_key}\n{e}")
            results.append({
                "rating_key": rating_key,
                "status": "error",
                "error": str(e),
            })

    return {"results": results}
