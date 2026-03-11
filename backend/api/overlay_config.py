# backend/api/overlay_config.py
"""API endpoints for overlay configuration management."""
import os
import re
import uuid
from pathlib import Path
from typing import List

import io
from fastapi import APIRouter, Form, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response

from ..config import settings, logger, BASE_DIR
from .. import database as db
from ..schemas import (
    OverlayConfigSaveRequest,
    OverlayConfigDeleteRequest,
    OverlayAssetUploadRequest,
    OverlayAssetDeleteRequest,
    PresetOverlayLinkRequest,
)

router = APIRouter()


def _get_overlay_assets_dir() -> Path:
    """Get the overlay assets directory path."""
    assets_dir = Path(settings.CONFIG_DIR) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    return assets_dir


# ═══════════════════════════════════════════════════════════════════════════
# Overlay Configuration Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/overlay-configs")
def api_get_all_overlay_configs():
    """Get all overlay configurations."""
    try:
        configs = db.get_all_overlay_configs()
        return {"configs": configs}
    except Exception as e:
        logger.error(f"[OVERLAY] Error fetching overlay configs: {e}")
        raise HTTPException(500, "Failed to fetch overlay configurations")


@router.get("/overlay-configs/{config_id}")
def api_get_overlay_config(config_id: str):
    """Get a specific overlay configuration."""
    try:
        config = db.get_overlay_config(config_id)
        if not config:
            raise HTTPException(404, f"Overlay config {config_id} not found")
        return config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error fetching overlay config {config_id}: {e}")
        raise HTTPException(500, "Failed to fetch overlay configuration")


@router.post("/overlay-configs/save")
def api_save_overlay_config(req: OverlayConfigSaveRequest):
    """Save or update an overlay configuration."""
    try:
        elements = [elem.model_dump() for elem in req.elements]
        db.save_overlay_config(req.id, req.name, elements, streaming_region=req.streaming_region)
        return {"status": "ok", "id": req.id}
    except Exception as e:
        logger.error(f"[OVERLAY] Error saving overlay config {req.id}: {e}")
        raise HTTPException(500, "Failed to save overlay configuration")


@router.delete("/overlay-configs/{config_id}")
def api_delete_overlay_config(config_id: str):
    """Delete an overlay configuration."""
    try:
        deleted = db.delete_overlay_config(config_id)
        if not deleted:
            raise HTTPException(404, f"Overlay config {config_id} not found")
        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error deleting overlay config {config_id}: {e}")
        raise HTTPException(500, "Failed to delete overlay configuration")


# ═══════════════════════════════════════════════════════════════════════════
# Overlay Asset Endpoints
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/overlay-assets")
def api_get_all_overlay_assets():
    """Get all overlay assets."""
    try:
        assets = db.get_all_overlay_assets()
        return {"assets": assets}
    except Exception as e:
        logger.error(f"[OVERLAY] Error fetching overlay assets: {e}")
        raise HTTPException(500, "Failed to fetch overlay assets")


@router.get("/overlay-assets/{asset_id}")
def api_get_overlay_asset(asset_id: str):
    """Get a specific overlay asset."""
    try:
        asset = db.get_overlay_asset(asset_id)
        if not asset:
            raise HTTPException(404, f"Overlay asset {asset_id} not found")
        return asset
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error fetching overlay asset {asset_id}: {e}")
        raise HTTPException(500, "Failed to fetch overlay asset")


def _sanitize_filename(name: str) -> str:
    """Convert asset name to a safe filename (lowercase, hyphens, no special chars)."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s-]", "", s)       # remove non-word chars except hyphens
    s = re.sub(r"[\s_]+", "-", s)         # spaces/underscores → hyphens
    s = re.sub(r"-+", "-", s).strip("-")  # collapse multiple hyphens
    return s or "asset"


@router.post("/overlay-assets/upload")
async def api_upload_overlay_asset(
    name: str = Form(...),
    file: UploadFile = File(...)
):
    """Upload a new overlay asset (image file)."""
    try:
        # Validate file type
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(400, "File must be an image (PNG, JPG, WebP)")

        # Use sanitized asset name as filename
        asset_id = str(uuid.uuid4())
        file_ext = Path(file.filename or "image.png").suffix.lower()
        if file_ext not in [".png", ".jpg", ".jpeg", ".webp"]:
            file_ext = ".png"

        # Save file to disk using the asset name
        assets_dir = _get_overlay_assets_dir()
        safe_name = _sanitize_filename(name)
        filename = f"{safe_name}{file_ext}"
        file_path = assets_dir / filename

        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        # Get image dimensions
        from PIL import Image
        with Image.open(file_path) as img:
            width, height = img.size

        # Save to database
        relative_path = f"assets/{filename}"
        file_type = file_ext[1:]  # Remove leading dot
        db.save_overlay_asset(asset_id, name, relative_path, file_type, width, height)

        logger.info(f"[OVERLAY] Uploaded overlay asset {asset_id} ({name})")
        return {
            "status": "ok",
            "id": asset_id,
            "name": name,
            "file_path": relative_path,
            "file_type": file_type,
            "width": width,
            "height": height
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error uploading overlay asset: {e}")
        raise HTTPException(500, f"Failed to upload overlay asset: {str(e)}")


@router.get("/overlay-assets/{asset_id}/file")
def api_get_overlay_asset_file(asset_id: str):
    """Serve an overlay asset image file."""
    try:
        asset = db.get_overlay_asset(asset_id)
        if not asset:
            raise HTTPException(404, f"Overlay asset {asset_id} not found")

        file_path = Path(settings.CONFIG_DIR) / asset["file_path"]
        if not file_path.exists():
            raise HTTPException(404, "Asset file not found on disk")

        return FileResponse(file_path, media_type=f"image/{asset['file_type']}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error serving overlay asset {asset_id}: {e}")
        raise HTTPException(500, "Failed to serve overlay asset")


@router.delete("/overlay-assets/{asset_id}")
def api_delete_overlay_asset(asset_id: str):
    """Delete an overlay asset."""
    try:
        # Get asset info before deleting from DB
        asset = db.get_overlay_asset(asset_id)
        if not asset:
            raise HTTPException(404, f"Overlay asset {asset_id} not found")

        # Delete from database
        deleted = db.delete_overlay_asset(asset_id)

        # Delete file from disk
        try:
            file_path = Path(settings.CONFIG_DIR) / asset["file_path"]
            if file_path.exists():
                os.remove(file_path)
        except Exception as file_err:
            logger.warning(f"[OVERLAY] Could not delete asset file for {asset_id}: {file_err}")

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error deleting overlay asset {asset_id}: {e}")
        raise HTTPException(500, "Failed to delete overlay asset")


@router.post("/overlay-assets/rescan")
def api_rescan_overlay_assets():
    """Scan the assets folder and register any untracked image files."""
    try:
        from PIL import Image as PILImage

        assets_dir = _get_overlay_assets_dir()
        image_extensions = {".png", ".jpg", ".jpeg", ".webp"}

        # Build set of already-tracked relative paths
        existing = {a["file_path"] for a in db.get_all_overlay_assets()}

        added = []
        for file_path in sorted(assets_dir.iterdir()):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in image_extensions:
                continue

            relative_path = f"assets/{file_path.name}"
            if relative_path in existing:
                continue

            # Register untracked file
            try:
                with PILImage.open(file_path) as img:
                    width, height = img.size
                asset_id = str(uuid.uuid4())
                name = file_path.stem.replace("-", " ").replace("_", " ").title()
                file_type = file_path.suffix.lower()[1:]
                db.save_overlay_asset(asset_id, name, relative_path, file_type, width, height)
                added.append(name)
                logger.info(f"[OVERLAY] Rescan: registered new asset '{name}' ({file_path.name})")
            except Exception as e:
                logger.warning(f"[OVERLAY] Rescan: could not register {file_path.name}: {e}")

        return {"status": "ok", "added": len(added), "names": added}
    except Exception as e:
        logger.error(f"[OVERLAY] Error rescanning overlay assets: {e}")
        raise HTTPException(500, "Failed to rescan overlay assets")


# ═══════════════════════════════════════════════════════════════════════════
# Font Listing Endpoint
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/fonts")
def api_list_fonts():
    """List available font files from config and bundled font directories."""
    font_extensions = {'.ttf', '.otf', '.ttc'}
    font_names: set[str] = set()

    search_dirs = [
        Path(settings.CONFIG_DIR) / "fonts",   # User-uploaded fonts
        BASE_DIR / "config" / "fonts",          # Bundled fonts
    ]

    for font_dir in search_dirs:
        if not font_dir.exists():
            continue
        for font_file in font_dir.iterdir():
            if font_file.suffix.lower() in font_extensions and font_file.is_file():
                font_names.add(font_file.stem)

    return {"fonts": sorted(font_names, key=str.lower)}


# ═══════════════════════════════════════════════════════════════════════════
# Preset-Overlay Linking Endpoint
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/presets/link-overlay")
def api_link_preset_to_overlay(req: PresetOverlayLinkRequest):
    """Link a preset to an overlay configuration."""
    try:
        # Verify preset exists
        preset = db.get_preset(req.template_id, req.preset_id)
        if not preset:
            raise HTTPException(404, f"Preset {req.preset_id} not found in template {req.template_id}")

        # Verify overlay config exists (if provided)
        if req.overlay_config_id:
            overlay_config = db.get_overlay_config(req.overlay_config_id)
            if not overlay_config:
                raise HTTPException(404, f"Overlay config {req.overlay_config_id} not found")

        # Link preset to overlay config
        db.link_preset_to_overlay_config(req.template_id, req.preset_id, req.overlay_config_id)

        return {"status": "ok"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OVERLAY] Error linking preset to overlay config: {e}")
        raise HTTPException(500, "Failed to link preset to overlay configuration")


# ═══════════════════════════════════════════════════════════════════════════
# Image Proxy (for CORS-free canvas preview of URL badge images)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/proxy-image")
def api_proxy_image(url: str):
    """Fetch an external image URL server-side and return it, bypassing browser CORS restrictions.
    Reuses the URL badge disk cache (7-day TTL) so repeated previews are instant."""
    if not url or not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid URL")
    try:
        from ..templates.universal import _fetch_url_badge_image
        img = _fetch_url_badge_image(url)
        if img is None:
            raise HTTPException(status_code=502, detail="Failed to fetch image from URL")
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return Response(
            content=buf.getvalue(),
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"[OVERLAY] Proxy image error for {url[:80]}: {e}")
        raise HTTPException(status_code=502, detail="Failed to proxy image")
