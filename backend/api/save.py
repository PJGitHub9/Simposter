# backend/api/save.py
from fastapi import APIRouter
import os
import json
from pathlib import Path
from typing import Optional
from PIL import Image, PngImagePlugin

from ..config import settings, logger
from ..rendering import render_poster_image
from ..schemas import SaveRequest

router = APIRouter()


DEFAULT_SAVE_TEMPLATE = "/config/output/{library}/{title}.jpg"


def resolve_library_label(library_id: Optional[str]) -> str:
    """Return a human-friendly library label (display name/title) given an id."""
    mappings = getattr(settings, "PLEX_LIBRARY_MAPPINGS", []) or []
    label: Optional[str] = None

    # Normalize incoming id so any accidental path-like strings are reduced to the last segment
    normalized_id = None
    if library_id:
        normalized_id = str(library_id).replace("\\", "/").rstrip("/")
        if "/" in normalized_id:
            normalized_id = normalized_id.split("/")[-1] or normalized_id
    lib_id = normalized_id or library_id

    # If no id provided, fall back to first mapping/display name
    if not lib_id:
        if mappings:
            first = mappings[0]
            label = first.get("displayName") or first.get("title") or str(first.get("id") or "default")
        else:
            names = getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", []) or []
            label = str(names[0]) if names else "default"
    else:
        mappings = getattr(settings, "PLEX_LIBRARY_MAPPINGS", []) or []
        for m in mappings:
            mid = str(m.get("id", ""))
            if mid == str(lib_id):
                label = m.get("displayName") or m.get("title") or mid
                break

        # Fallback to configured names list if it contains the id or a name
        if not label:
            names = getattr(settings, "PLEX_MOVIE_LIBRARY_NAMES", []) or []
            for n in names:
                if str(n) == str(lib_id):
                    label = str(n)
                    break

    # Final fallback
    label = label or str(lib_id or "default")

    # If the label looks like a path (e.g., "config/output/Movies"), use only the trailing segment
    cleaned = label.replace("\\", "/").rstrip("/")
    if "/" in cleaned:
        cleaned = cleaned.split("/")[-1] or cleaned

    return cleaned


def embed_library_metadata(
    img: Image.Image,
    library_id: Optional[str],
    library_label: Optional[str],
    movie_title: Optional[str] = None,
    movie_year: Optional[str] = None,
) -> Image.Image:
    """
    Embed library metadata into image for reliable filtering.
    Uses PNG metadata for PNG files, falls back to comment-based metadata for JPEG.
    """
    metadata = {}

    if library_id:
        metadata["simposter_library_id"] = str(library_id)
        metadata["simposter_library_name"] = str(library_label or library_id)

    if movie_title:
        metadata["simposter_movie_title"] = str(movie_title)
    if movie_year:
        metadata["simposter_movie_year"] = str(movie_year)

    if not metadata:
        return img

    # For PNG images, use PNG metadata chunks
    # For JPEG, we'll embed in EXIF or use a different approach
    # Since PIL doesn't easily support custom EXIF fields, we'll use PNG metadata when possible
    # and for JPEG we'll store in the info dict which can be retrieved later

    # Store in image info dict (available for both formats)
    if not hasattr(img, 'info'):
        img.info = {}
    img.info.update(metadata)

    return img


def get_save_location_template() -> str:
    """Read save location template from UI settings."""
    # First try database (source of truth after migration)
    try:
        from .. import database as db  # local import to avoid circular
        data = db.get_ui_settings()
        if data:
            tmpl = data.get("saveLocation")
            if tmpl:
                return tmpl
    except Exception:
        pass

    # Prefer settings directory (config/settings/ui_settings.json), then legacy config root
    settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
    legacy_file = Path(settings.CONFIG_DIR) / "ui_settings.json"
    try:
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            return data.get("saveLocation") or DEFAULT_SAVE_TEMPLATE
        if legacy_file.exists():
            data = json.loads(legacy_file.read_text(encoding="utf-8"))
            return data.get("saveLocation") or DEFAULT_SAVE_TEMPLATE
    except Exception:
        pass
    return DEFAULT_SAVE_TEMPLATE


def apply_save_location_variables(template: str, title: str, year: Optional[int], key: Optional[str], library: Optional[str] = None) -> str:
    """Replace variables in save location template with actual values."""
    # Replace variables
    result = template.replace("{title}", title)
    result = result.replace("{year}", str(year) if year else "")
    result = result.replace("{key}", key if key else "")
    result = result.replace("{library}", library if library else "")

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

    # Resolve library label for template substitution (prefer display name/title over id)
    library_label = resolve_library_label(req.library_id)

    # Apply variable substitution
    save_path = apply_save_location_variables(
        save_template,
        req.movie_title,
        req.movie_year,
        req.rating_key,
        library_label
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

    # Map explicit /config/* to configured CONFIG_DIR so the default template lands in the config volume
    base_dir_str = str(base_dir).replace("\\", "/")
    if base_dir.is_absolute() and base_dir_str.startswith("/config"):
        tail = base_dir_str[len("/config"):].lstrip("/")
        base_dir = Path(settings.CONFIG_DIR) / tail

    # If path is relative, anchor under OUTPUT_ROOT
    if not base_dir.is_absolute():
        lower_path = base_dir_str.lower()
        # If user supplied "config/..." without leading slash, respect CONFIG_DIR
        if lower_path.startswith("config/"):
            tail = base_dir_str.split("/", 1)[1] if "/" in base_dir_str else ""
            base_dir = Path(settings.CONFIG_DIR) / tail
        # If user supplied "output/..." without leading slash, respect OUTPUT_ROOT
        elif lower_path.startswith("output/"):
            tail = base_dir_str.split("/", 1)[1] if "/" in base_dir_str else ""
            base_dir = Path(settings.OUTPUT_ROOT) / tail
        else:
            base_dir = Path(settings.OUTPUT_ROOT) / str(base_dir).lstrip("/\\")

    os.makedirs(base_dir, exist_ok=True)
    out_path = base_dir / filename

    # Embed library metadata into the image
    img = embed_library_metadata(img, req.library_id, library_label, req.movie_title, str(req.movie_year) if req.movie_year else None)

    # Determine output format from filename extension
    file_ext = out_path.suffix.lower()

    if file_ext == '.png':
        # For PNG, properly embed metadata in PNG chunks
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("simposter_library_id", str(req.library_id or ""))
        pnginfo.add_text("simposter_library_name", str(library_label or ""))
        pnginfo.add_text("simposter_movie_title", str(req.movie_title or ""))
        pnginfo.add_text("simposter_movie_year", str(req.movie_year or ""))
        img.save(out_path, "PNG", pnginfo=pnginfo)
    else:
        # For JPEG, embed metadata in EXIF UserComment field
        img_rgb = img.convert("RGB")

        # Create EXIF data with library metadata
        exif = img_rgb.getexif()
        if exif is None:
            from PIL.Image import Exif
            exif = Exif()

        # EXIF UserComment tag (0x9286) - store as JSON for easy parsing
        import json
        metadata_json = json.dumps({
            "simposter_library_id": str(req.library_id or ""),
            "simposter_library_name": str(library_label or ""),
            "simposter_movie_title": str(req.movie_title or ""),
            "simposter_movie_year": str(req.movie_year or "")
        })
        exif[0x9286] = metadata_json.encode('utf-8')  # UserComment field
        exif_bytes = exif.tobytes()

        img_rgb.save(out_path, "JPEG", quality=95, exif=exif_bytes)

    logger.info("Saved poster to %s (library: %s)", out_path, library_label)
    return {"status": "ok", "saved_path": out_path}
