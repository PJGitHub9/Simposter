# backend/api/overlay_config.py
"""API endpoints for overlay configuration management."""
import os
import re
import uuid
from pathlib import Path
from typing import List, Optional

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
        db.save_overlay_config(req.id, req.name, elements, streaming_region=req.streaming_region,
                               conditions=req.conditions)
        return {"status": "ok", "id": req.id}
    except Exception as e:
        logger.error(f"[OVERLAY] Error saving overlay config {req.id}: {e}")
        raise HTTPException(500, "Failed to save overlay configuration")


@router.get("/overlay-configs/{config_id}/usage")
def api_get_overlay_config_usage(config_id: str):
    """List presets that currently reference this overlay config, for the
    delete-confirmation warning."""
    presets = db.get_presets_using_overlay_config(config_id)
    return {"presets": presets, "count": len(presets)}


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
    """List available font files from config/bundled directories, already-cached
    Kometa Creator default fonts, and the full set of Kometa default font names
    (fetched-and-cached on first actual use — see universal.py's
    _load_remote_kometa_font() — so they're listed as selectable immediately
    even before that first fetch happens)."""
    from ..templates.universal import _KOMETA_REMOTE_FONTS, _KOMETA_REPO_FONTS, _kometa_fonts_cache_dir

    font_extensions = {'.ttf', '.otf', '.ttc'}
    font_names: set[str] = set()

    search_dirs = [
        Path(settings.CONFIG_DIR) / "fonts",   # User-uploaded fonts
        BASE_DIR / "config" / "fonts",          # Bundled fonts (Docker-seeded from system packages)
        _kometa_fonts_cache_dir(),               # Already-fetched Kometa Creator default fonts
    ]

    for font_dir in search_dirs:
        if not font_dir.exists():
            continue
        for font_file in font_dir.iterdir():
            if font_file.suffix.lower() in font_extensions and font_file.is_file():
                font_names.add(font_file.stem)

    # Known Kometa default font names, listed even before first use fetches them
    font_names.update(Path(fname).stem for fname in _KOMETA_REMOTE_FONTS.values())
    font_names.update(Path(fname).stem for fname in _KOMETA_REPO_FONTS.values())
    # Simposter's own font set (simposter-assets fonts.json), downloaded on first use
    try:
        from ..templates.universal import asset_font_names
        font_names.update(asset_font_names())
    except Exception as e:
        logger.debug("[FONTS] simposter-assets font list unavailable: %s", e)

    return {"fonts": sorted(font_names, key=str.lower)}


_FONT_MEDIA_TYPES = {".ttf": "font/ttf", ".otf": "font/otf", ".ttc": "font/collection"}


@router.get("/fonts/file")
def api_font_file(name: str):
    """The font file for a font name, so the Overlay Manager preview can draw
    with the same font as the render. Looks in the same folders as the render
    (exact file name, case-insensitive) and fetches a Kometa font on first use."""
    from ..templates.universal import _kometa_fonts_cache_dir, _load_remote_kometa_font
    wanted = (name or "").strip()
    if not wanted or "/" in wanted or "\\" in wanted or ".." in wanted:
        raise HTTPException(400, "Invalid font name")
    dirs = [Path(settings.CONFIG_DIR) / "fonts", BASE_DIR / "config" / "fonts", _kometa_fonts_cache_dir()]

    def find():
        low = wanted.lower()
        for d in dirs:
            if not d.is_dir():
                continue
            for f in d.iterdir():
                if f.is_file() and f.suffix.lower() in _FONT_MEDIA_TYPES and f.stem.lower() == low:
                    return f
        return None

    path = find()
    if path is None:
        # Simposter's own font set. A variable file holds every weight; the
        # preview draws it at the file's default weight.
        from ..templates.universal import asset_font_path
        path = asset_font_path(wanted)
    if path is None and _load_remote_kometa_font(wanted, 12, False) is not None:
        path = find()
    if path is None:
        raise HTTPException(404, "Font not found")
    return FileResponse(str(path), media_type=_FONT_MEDIA_TYPES[path.suffix.lower()],
                        headers={"Cache-Control": "public, max-age=86400"})


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

@router.get("/overlay-preview-metadata")
def api_overlay_preview_metadata(
    rating_key: str,
    config_id: Optional[str] = None,
    media_type: str = "movie",
    ratings: bool = False,
    lists: Optional[str] = None,
    badge_types: Optional[str] = None,
    fields: Optional[str] = None,
):
    """Return Plex media metadata for a given rating_key for use in the overlay config preview.

    If config_id is provided, also resolves streaming_platform and studio via the same
    TMDb pre-pass that apply_overlay_config uses, so item-mode preview reflects real values.

    The editor also says what its current, possibly unsaved, layers use (ratings=1,
    lists=comma-separated list URLs, badge_types=comma-separated element types,
    fields=other data fields its rules use, e.g. days_since_added,show_status), so
    the preview doesn't wait for a save before fetching that data.
    """
    try:
        from ..config import get_plex_media_info, get_movie_tmdb_id
        info = get_plex_media_info(rating_key) or {}

        saved_cfg = db.get_overlay_config(config_id) if config_id else None
        extra_types = {t.strip() for t in (badge_types or "").split(",") if t.strip()}
        if saved_cfg or extra_types:
            try:
                cfg = saved_cfg or {}
                element_types = {e.get("type") for e in cfg.get("elements", [])} | extra_types
                tmdb_id = None
                if element_types & {"streaming_platform_badge", "studio_badge"}:
                    # Scanned id first: a Jellyfin/Emby item (or a TV show) has
                    # no Plex movie metadata to read it from.
                    tmdb_id = db.get_ids_for_rating_key(str(rating_key))[0]
                    if not tmdb_id and db.get_server_id_for_rating_key(str(rating_key)) == "plex-1":
                        tmdb_id = get_movie_tmdb_id(rating_key)

                if tmdb_id and "streaming_platform_badge" in element_types:
                    try:
                        from ..tmdb_client import get_watch_providers, normalize_provider_name
                        region = cfg.get("streaming_region") or "US"
                        providers = get_watch_providers(tmdb_id, media_type, region)
                        if providers:
                            slug = normalize_provider_name(providers[0].get("provider_name", ""))
                            if slug:
                                info["streaming_platform"] = slug
                    except Exception as sp_err:
                        logger.debug(f"[OVERLAY] Preview streaming platform error: {sp_err}")

                if tmdb_id and "studio_badge" in element_types:
                    try:
                        from ..tmdb_client import get_studio_name, get_studio_company_id
                        slug = get_studio_name(tmdb_id, media_type)
                        if slug:
                            info["studio"] = slug
                        cid = get_studio_company_id(tmdb_id, media_type)
                        if cid is not None:
                            info["studio_company_id"] = str(cid)
                    except Exception as st_err:
                        logger.debug(f"[OVERLAY] Preview studio error: {st_err}")
            except Exception as pre_err:
                logger.debug(f"[OVERLAY] Preview pre-pass error: {pre_err}")

        # TMDb/TVDB ids, for conditions that match fixed id lists (imported tmdb_movie etc.).
        try:
            cached_tmdb, cached_tvdb = db.get_ids_for_rating_key(rating_key)
            if cached_tmdb and not info.get("tmdb_id"):
                info["tmdb_id"] = str(cached_tmdb)
            if cached_tvdb and not info.get("tvdb_id"):
                info["tvdb_id"] = str(cached_tvdb)
        except Exception:
            pass

        # Labels and file paths for previewing element conditions (overlay engine v2).
        labels: list = []
        file_paths: list = []
        try:
            labels = (db.get_tv_labels(rating_key) if media_type == "tv" else db.get_movie_labels(rating_key)) or []
            file_paths = db.get_file_paths(rating_key)
        except Exception:
            pass
        # MDBList ratings and list membership, only when this config uses them.
        lists_out: list = []
        extra_lists = [u.strip() for u in (lists or "").split(",") if u.strip()]
        if saved_cfg or ratings or extra_lists:
            try:
                from .. import overlay_engine
                elements = [e for e in (saved_cfg or {}).get("elements", []) if isinstance(e, dict)]
                # Stand-in layers for what the unsaved editor uses.
                if ratings:
                    elements.append({"type": "text_label", "text": "{audience_rating}"})
                if extra_lists:
                    elements.append({"type": "text_label", "conditions": [{"field": "list", "op": "in", "value": extra_lists}]})
                needs = overlay_engine.needed_data(elements)
                if needs["ratings"] or needs["lists"]:
                    tmdb_id, tvdb_id = db.get_ids_for_rating_key(rating_key)
                    ctx = overlay_engine.build_context(
                        {"rating_key": rating_key, "tmdb_id": tmdb_id, "tvdb_id": tvdb_id, "media_type": media_type},
                        elements=elements,
                    )
                    for key in ctx:
                        if key.endswith("_rating") and ctx[key] is not None and key not in info:
                            info[key] = ctx[key]
                    lists_out = ctx.get("lists") or []
            except Exception as mdb_err:
                logger.debug(f"[OVERLAY] Preview MDBList error: {mdb_err}")
        # Date added and show status, when the layers' rules use them.
        wanted = {f.strip() for f in (fields or "").split(",") if f.strip()}
        if saved_cfg:
            for e in saved_cfg.get("elements", []):
                for c in (e.get("conditions") or []) if isinstance(e, dict) else []:
                    if isinstance(c, dict) and c.get("field") in ("days_since_added", "show_status"):
                        wanted.add(c["field"])
        wanted &= {"days_since_added", "show_status"}
        if wanted:
            try:
                from .. import overlay_engine
                tmdb_id, tvdb_id = db.get_ids_for_rating_key(rating_key)
                stand_in = [{"type": "text_label", "conditions": [{"field": f, "op": "exists"} for f in wanted]}]
                ctx = overlay_engine.build_context(
                    {"rating_key": rating_key, "tmdb_id": tmdb_id, "tvdb_id": tvdb_id, "media_type": media_type},
                    elements=stand_in,
                )
                for f in wanted:
                    if ctx.get(f) not in (None, ""):
                        info[f] = ctx[f]
            except Exception as extra_err:
                logger.debug(f"[OVERLAY] Preview extra fields error: {extra_err}")
        return {"metadata": info, "labels": labels, "file_paths": file_paths, "lists": lists_out}
    except Exception as e:
        logger.warning(f"[OVERLAY] Failed to fetch preview metadata for {rating_key}: {e}")
        return {"metadata": {}}


@router.get("/simposter-assets-map")
def api_simposter_assets_map():
    """Return the full slug→URL mapping for curated simposter-assets logos."""
    from ..simposter_assets import get_full_map
    return {"assets": get_full_map()}


@router.get("/asset-image")
def api_asset_image(slug: str = "", company_id: Optional[int] = None):
    """Resolve a simposter-assets slug (and/or TMDb company ID) and proxy the image.

    Does full resolution: company_id (ID cache) → logos.json slug → overrides → heuristic.
    Returns 404 when no image can be found so the canvas can fall back gracefully.
    """
    if not slug and company_id is None:
        raise HTTPException(status_code=400, detail="Missing slug or company_id")
    try:
        from ..simposter_assets import get_asset_url
        from ..templates.universal import _fetch_url_badge_image
        url = get_asset_url(slug, company_id=company_id)
        if not url:
            raise HTTPException(status_code=404, detail="No asset URL for slug")
        img = _fetch_url_badge_image(url)
        if img is None:
            raise HTTPException(status_code=404, detail="Asset image not found or inaccessible")
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
        logger.warning(f"[OVERLAY] asset-image error for slug={slug!r} company_id={company_id}: {e}")
        raise HTTPException(status_code=502, detail="Failed to resolve asset image")


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
