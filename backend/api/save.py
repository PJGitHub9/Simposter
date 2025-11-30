# backend/api/save.py
from fastapi import APIRouter
import os
import json
from pathlib import Path
from typing import Optional

from ..config import settings, logger
from ..rendering import render_poster_image
from ..schemas import SaveRequest

router = APIRouter()


def get_save_location_template() -> str:
    """Read save location template from UI settings."""
    settings_file = Path(settings.CONFIG_DIR) / "ui_settings.json"
    try:
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return data.get("saveLocation", "/output")
    except Exception:
        pass
    return "/output"


def apply_save_location_variables(template: str, title: str, year: Optional[int], key: Optional[str]) -> str:
    """Replace variables in save location template with actual values."""
    # Replace variables
    result = template.replace("{title}", title)
    result = result.replace("{year}", str(year) if year else "")
    result = result.replace("{key}", key if key else "")

    # Clean up any double slashes or trailing spaces
    result = result.replace("//", "/")
    result = " ".join(result.split())  # Remove extra whitespace

    return result


@router.post("/save")
def api_save(req: SaveRequest):
    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        req.options,
    )

    # Get save location template from UI settings
    save_template = get_save_location_template()

    # Apply variable substitution
    save_path = apply_save_location_variables(
        save_template,
        req.movie_title,
        req.movie_year,
        req.rating_key
    )

    # Sanitize path components
    safe_path = "".join(c for c in save_path if c.isalnum() or c in " _-/()")

    # If path is relative, join with OUTPUT_ROOT
    if not os.path.isabs(safe_path):
        out_dir = os.path.join(settings.OUTPUT_ROOT, safe_path.lstrip("/"))
    else:
        out_dir = safe_path

    os.makedirs(out_dir, exist_ok=True)

    # Use filename from request or default to poster.jpg
    filename = req.filename or "poster.jpg"
    out_path = os.path.join(out_dir, filename)

    img.convert("RGB").save(out_path, "JPEG", quality=95)

    logger.info("Saved poster to %s", out_path)
    return {"status": "ok", "path": out_path}
