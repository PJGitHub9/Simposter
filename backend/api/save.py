from fastapi import APIRouter, HTTPException
from typing import Optional, Tuple
from io import BytesIO
from PIL import Image, PngImagePlugin

from ..config import logger, get_media_folder_name
from ..rendering import render_poster_image
from ..schemas import SaveRequest
from ..save_paths import SaveContext, resolve_save_path, resolve_library_label, PathTraversalError

router = APIRouter()


def get_output_format_settings() -> dict:
    """Read the user's output format preference from settings.
    Returns dict with keys: format ('jpg'|'png'|'webp'), ext ('.jpg'|'.png'|'.webp'),
    pil_format ('JPEG'|'PNG'|'WEBP'), quality (int)."""
    from .. import database as db

    fmt = "jpg"
    jpg_quality = 95
    png_compression = 6
    webp_quality = 90

    try:
        settings_data = db.get_ui_settings()
        if settings_data and "imageQuality" in settings_data:
            iq = settings_data["imageQuality"]
            fmt = iq.get("outputFormat", "jpg").lower()
            jpg_quality = iq.get("jpgQuality", 95)
            png_compression = iq.get("pngCompression", 6)
            webp_quality = iq.get("webpQuality", 90)
    except Exception:
        pass

    if fmt == "png":
        return {"format": "png", "ext": ".png", "pil_format": "PNG", "quality": png_compression}
    elif fmt == "webp":
        return {"format": "webp", "ext": ".webp", "pil_format": "WEBP", "quality": webp_quality}
    else:
        return {"format": "jpg", "ext": ".jpg", "pil_format": "JPEG", "quality": jpg_quality}


# Plex's /posters upload endpoint rejects payloads over roughly 10MB (returns a
# 500, not a helpful "too large" error). Leave headroom under the real cap.
_PLEX_UPLOAD_SIZE_LIMIT = 9_500_000


def encode_poster_for_plex(img: Image.Image) -> Tuple[bytes, str]:
    """Encode a freshly-rendered poster for upload to Plex's /posters endpoint.

    PNG (lossless) by default, regardless of the user's local save format
    setting — a Plex upload is a one-time transfer, not a disk-space-constrained
    archive copy, so there's no reason to introduce JPEG generation loss when we
    don't have to. Always flattened to RGB first (the render pipeline returns
    RGBA — every pixel ends up fully opaque, but the file would otherwise carry
    a real, functionally meaningless alpha channel) and encoded at max PNG
    compression to get the smallest possible lossless file.

    If that PNG would still exceed Plex's ~10MB upload cap (this app's grain/
    matte effects compress poorly under PNG's lossless algorithm at the fixed
    2000x3000 canvas size — this is exactly what caused real 500s from Plex on
    some posters), falls back to a high-quality JPEG instead, which reliably
    stays well under the limit."""
    from .. import database as db

    jpg_quality = 95
    try:
        settings_data = db.get_ui_settings()
        if settings_data and "imageQuality" in settings_data:
            jpg_quality = settings_data["imageQuality"].get("jpgQuality", 95)
    except Exception:
        pass

    rgb = img.convert("RGB")

    buf = BytesIO()
    rgb.save(buf, "PNG", compress_level=9)
    png_bytes = buf.getvalue()
    if len(png_bytes) <= _PLEX_UPLOAD_SIZE_LIMIT:
        return png_bytes, "image/png"

    logger.warning(
        "[PLEX] Rendered PNG (%.1fMB) exceeds Plex's upload size limit, falling back to JPEG",
        len(png_bytes) / 1_000_000,
    )
    buf2 = BytesIO()
    rgb.save(buf2, "JPEG", quality=max(jpg_quality, 98), subsampling=0)
    return buf2.getvalue(), "image/jpeg"


def normalize_logo_for_plex(logo_bytes: bytes, fallback_content_type: str = "image/png") -> Tuple[bytes, str]:
    """Normalize logo bytes through PIL before upload to Plex's clearLogos endpoint,
    rather than forwarding raw bytes from an arbitrary source (TMDb/Fanart/upload)
    untouched. Rules out source format quirks (indexed color, ICC profiles,
    interlacing, unusual bit depth) that have caused logos to appear cropped once
    in Plex despite looking correct everywhere in Simposter, without touching
    dimensions/aspect ratio. Falls back to the original bytes/content-type if the
    image can't be parsed, rather than failing the upload outright.

    Every code path that uploads a logo to Plex — the standalone "Send Logo"
    button, and logo uploads during batch/webhook/retry/auto-generate sends —
    must go through this rather than posting fetched bytes directly."""
    try:
        img = Image.open(BytesIO(logo_bytes)).convert("RGBA")
        buf = BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue(), "image/png"
    except Exception as e:
        logger.warning("[PLEX] Failed to normalize logo image, uploading raw bytes instead: %s", e)
        return logo_bytes, fallback_content_type


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


@router.post("/save")
def api_save(req: SaveRequest):
    # Add movie details to options for template variable substitution
    render_options = dict(req.options or {})
    render_options["movie_title"] = req.movie_title or ""
    render_options["movie_year"] = str(req.movie_year) if req.movie_year else ""

    # Load preset season_options if rendering a season (same logic as preview endpoint)
    if req.preset_id:
        from .. import database as db
        preset = db.get_preset(req.template_id or "uniformlogo", req.preset_id)
        if preset:
            # Check if this is a season render based on season_text presence
            is_season = False
            try:
                st = (render_options.get("season_text") or "").strip()
                is_season = len(st) > 0
            except (AttributeError, TypeError):
                is_season = False

            # Use season_options when rendering a season
            if is_season and isinstance(preset.get("season_options"), dict):
                preset_season_opts = preset.get("season_options", {})
                logger.info("[SAVE] Using season_options for preset '%s' (season_text='%s')", req.preset_id, st)
                # Merge preset season options with request options (request options take precedence)
                merged_options = {**preset_season_opts, **render_options}
                render_options = merged_options

    # Pass preset_id so the template renderer can look up linked overlay configs
    if req.preset_id:
        render_options["preset_id"] = req.preset_id

    # Inject Plex media metadata for overlay badge rendering
    if req.rating_key:
        try:
            from ..config import get_plex_media_info, extract_tmdb_id_from_metadata
            import requests as _requests
            import xml.etree.ElementTree as ET
            plex_media = get_plex_media_info(req.rating_key)
            if plex_media:
                existing_meta = render_options.get("metadata") or {}
                render_options["metadata"] = {**existing_meta, **plex_media}
                logger.info("[SAVE] Injected media info for rating_key=%s: %s", req.rating_key, plex_media)

            # Also inject tmdb_id + media_type for studio/streaming platform badge resolution
            from ..config import settings as _cfg, plex_headers
            meta_resp = _requests.get(
                f"{_cfg.PLEX_URL}/library/metadata/{req.rating_key}",
                headers=plex_headers(), timeout=5
            )
            if meta_resp.ok:
                tmdb_id = extract_tmdb_id_from_metadata(meta_resp.text)
                if tmdb_id:
                    root = ET.fromstring(meta_resp.text)
                    is_tv = root.find('.//Directory') is not None
                    render_options.setdefault("metadata", {})
                    render_options["metadata"]["tmdb_id"] = tmdb_id
                    render_options["metadata"]["media_type"] = "tv" if is_tv else "movie"
                    logger.info("[SAVE] Injected tmdb_id=%s media_type=%s for studio/streaming badge resolution", tmdb_id, render_options["metadata"]["media_type"])
        except Exception as e:
            logger.debug("[SAVE] Failed to inject media info: %s", e)

    img = render_poster_image(
        req.template_id,
        req.background_url,
        req.logo_url,
        render_options,
    )

    # Resolve library label for template substitution (prefer display name/title over id)
    library_label = resolve_library_label(req.library_id)

    fmt_settings = get_output_format_settings()

    # {folder} template variable: resolve the real on-disk folder name from Plex
    # (movies only -- TV shows/seasons have no single <Part> file to derive it from,
    # apply_save_location_variables() falls back to {title} automatically).
    folder_name = None
    if req.rating_key:
        folder_name = get_media_folder_name(req.rating_key, req.is_tv)

    ctx = SaveContext(
        media_type="tv-show" if req.is_tv else "movie",
        title=req.movie_title,
        year=req.movie_year,
        rating_key=req.rating_key,
        library_label=library_label,
        season=req.season_index if req.is_tv else None,
        filename_override=req.filename,
        folder_name=folder_name,
    )
    try:
        out_path = resolve_save_path(ctx, fmt_settings["ext"])
    except PathTraversalError as e:
        raise HTTPException(status_code=400, detail=str(e))

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Embed library metadata into the image
    img = embed_library_metadata(img, req.library_id, library_label, req.movie_title, str(req.movie_year) if req.movie_year else None)

    # Save using the correct format based on user's output format setting
    pil_format = fmt_settings["pil_format"]
    file_ext = out_path.suffix.lower()

    if pil_format == "PNG" or file_ext == '.png':
        # For PNG, properly embed metadata in PNG chunks
        pnginfo = PngImagePlugin.PngInfo()
        pnginfo.add_text("simposter_library_id", str(req.library_id or ""))
        pnginfo.add_text("simposter_library_name", str(library_label or ""))
        pnginfo.add_text("simposter_movie_title", str(req.movie_title or ""))
        pnginfo.add_text("simposter_movie_year", str(req.movie_year or ""))
        pnginfo.add_text("simposter_rating_key", str(req.rating_key or ""))
        pnginfo.add_text("simposter_is_tv", "1" if req.is_tv else "0")
        img.save(out_path, "PNG", pnginfo=pnginfo, compress_level=fmt_settings["quality"])
    elif pil_format == "WEBP" or file_ext == '.webp':
        # For WebP, convert to RGB and save with quality setting
        img_rgb = img.convert("RGB")
        img_rgb.save(out_path, "WEBP", quality=fmt_settings["quality"])
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
            "simposter_movie_year": str(req.movie_year or ""),
            "simposter_rating_key": str(req.rating_key or ""),
            "simposter_is_tv": "1" if req.is_tv else "0",
        })
        exif[0x9286] = metadata_json.encode('utf-8')  # UserComment field
        exif_bytes = exif.tobytes()
        img_rgb.save(out_path, "JPEG", quality=fmt_settings["quality"], exif=exif_bytes, subsampling=0)

    logger.info("Saved poster to %s (library: %s)", out_path, library_label)
    return {"status": "ok", "saved_path": out_path}
