# backend/api/save.py
from fastapi import APIRouter
import os

from ..config import settings, logger
from ..rendering import render_poster_image
from ..schemas import SaveRequest

router = APIRouter()

@router.post("/save")
def api_save(req: SaveRequest):
    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        req.options,
    )

    if req.movie_year:
        folder_name = f"{req.movie_title} ({req.movie_year})"
    else:
        folder_name = req.movie_title

    safe_folder = "".join(c for c in folder_name if c.isalnum() or c in " _-()")
    out_dir = os.path.join(settings.OUTPUT_ROOT, safe_folder)
    os.makedirs(out_dir, exist_ok=True)

    out_path = os.path.join(out_dir, f"{safe_folder}.jpg")
    img.convert("RGB").save(out_path, "JPEG", quality=95)

    logger.info("Saved poster to %s", out_path)
    return {"status": "ok", "path": out_path}
