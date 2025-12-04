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
    # Prefer settings directory (config/settings/ui_settings.json), then legacy config root
    settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
    legacy_file = Path(settings.CONFIG_DIR) / "ui_settings.json"
    try:
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return data.get("saveLocation", "/output")
        if legacy_file.exists():
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
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
    # Add movie details to options for template variable substitution
    render_options = dict(req.options or {})
    render_options["movie_title"] = req.movie_title or ""
    render_options["movie_year"] = str(req.movie_year) if req.movie_year else ""

    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        render_options,
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

    # Sanitize path components (keep dots so we can detect filenames)
    safe_path = "".join(c for c in save_path if c.isalnum() or c in " _-/().")
    safe_path = safe_path.strip()

    # Determine if the template included a filename (suffix present)
    candidate = Path(safe_path)
    if candidate.suffix:  # treat as full file path
        base_dir = candidate.parent
        filename = candidate.name
    else:
        base_dir = candidate
        filename = req.filename or "poster.jpg"

    # Map explicit /output/* to configured OUTPUT_ROOT to respect template defaults
    base_dir_str = str(base_dir).replace("\\", "/")
    if base_dir.is_absolute() and base_dir_str.startswith("/output"):
        # Strip leading /output and re-root under settings.OUTPUT_ROOT
        tail = base_dir_str[len("/output"):].lstrip("/")
        base_dir = Path(settings.OUTPUT_ROOT) / tail

    # If path is relative, anchor under OUTPUT_ROOT
    if not base_dir.is_absolute():
        base_dir = Path(settings.OUTPUT_ROOT) / str(base_dir).lstrip("/\\")

    os.makedirs(base_dir, exist_ok=True)
    out_path = base_dir / filename

    img.convert("RGB").save(out_path, "JPEG", quality=95)

    logger.info("Saved poster to %s", out_path)
    return {"status": "ok", "saved_path": out_path}
