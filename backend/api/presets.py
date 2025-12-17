# backend/api/presets.py
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Body

from ..config import load_presets, save_presets, USER_PRESETS_PATH, logger
from ..schemas import PresetDeleteRequest, PresetSaveRequest
from .. import database as db
from .template_manager import _get_fallback_settings

router = APIRouter()


def _apply_global_template_defaults(options: dict) -> dict:
    """
    Fill missing template selection defaults (poster_filter, logo_mode, logo source)
    from the global template preferences. Does not override values that are already set.
    """
    opts = dict(options or {})
    try:
        global_defaults = _get_fallback_settings()
    except Exception as e:
        logger.warning("[PRESETS] Could not load global template defaults: %s", e)
        global_defaults = {}

    poster_filter = global_defaults.get("poster_filter")
    logo_mode = global_defaults.get("logo_mode")
    logo_source = global_defaults.get("logo_source")

    if poster_filter is not None and "poster_filter" not in opts:
        opts["poster_filter"] = poster_filter
    if logo_mode is not None and "logo_mode" not in opts:
        opts["logo_mode"] = logo_mode
    # Support both camelCase and snake_case; prefer camelCase used in existing options
    if logo_source is not None and "logoSource" not in opts and "logo_source" not in opts:
        opts["logoSource"] = logo_source

    return opts


@router.get("/presets")
def api_presets():
    """Get all presets, reading from database with JSON fallback."""
    try:
        # Try database first
        data = db.get_all_presets()

        # If database is empty, try loading from JSON
        if not data:
            presets_file = Path(USER_PRESETS_PATH)
            if presets_file.exists():
                logger.info("[PRESETS] Loading from JSON file for migration")
                data = load_presets()
                # Migrate to database
                for template_id, template_data in data.items():
                    if "presets" in template_data:
                        for preset in template_data["presets"]:
                            db.save_preset(
                                template_id,
                                preset["id"],
                                preset.get("name", preset["id"]),
                                preset.get("options", {})
                            )
                logger.info("[PRESETS] Migrated presets to database")

                # Backup JSON file
                backup_path = presets_file.with_suffix(".json.migrated")
                presets_file.rename(backup_path)
                logger.info(f"[PRESETS] Backed up presets.json as {backup_path}")

                # Return migrated data
                return db.get_all_presets()
            else:
                # No presets found, return defaults from JSON fallback
                return load_presets()

        return data
    except Exception as e:
        logger.error(f"[PRESETS] Error loading presets: {e}")
        # Fallback to JSON-based loading
        return load_presets()


@router.get("/presets/export")
def api_presets_export():
    """Export all presets as JSON."""
    try:
        data = db.get_all_presets()
        return data
    except Exception as e:
        logger.error(f"[PRESETS] Error exporting presets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export presets: {e}")


@router.post("/presets/import")
async def api_presets_import(payload: dict = Body(...)):
    """
    Import presets from JSON (merges with existing presets).
    Expected shape matches /presets: { template_id: { presets: [{id,name,options}, ...] } }
    """
    try:
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Invalid JSON payload")

        db.merge_presets(payload)
        logger.info("[PRESETS] Imported and merged presets from JSON")
        return {"message": "Presets imported and merged"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRESETS] Error importing presets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to import presets: {e}")


@router.post("/presets/save")
def api_save_preset(req: PresetSaveRequest):
    """Save a preset to the database and generate overlay cache."""
    from ..rendering import generate_overlay
    from ..config import settings
    
    template_id = req.template_id or "default"
    preset_id = req.preset_id
    options = _apply_global_template_defaults(req.options)

    try:
        # Save to database
        db.save_preset(template_id, preset_id, preset_id, options)
        logger.info(f"[PRESETS] Saved preset {preset_id} for template {template_id}")
        
        # Generate and save overlay cache
        try:
            overlay = generate_overlay(options)
            
            # Create overlay directory: config/overlays/{template_id}/
            overlay_dir = Path(settings.CONFIG_DIR) / "overlays" / template_id
            overlay_dir.mkdir(parents=True, exist_ok=True)
            
            # Save overlay as PNG
            overlay_path = overlay_dir / f"{preset_id}.png"
            overlay.save(overlay_path, "PNG")
            logger.info(f"[PRESETS] Generated overlay cache: {overlay_path}")
        except Exception as overlay_err:
            logger.warning(f"[PRESETS] Failed to generate overlay cache: {overlay_err}")
            # Non-fatal: continue even if overlay generation fails
        
        return {"message": f"Preset '{preset_id}' saved."}
    except Exception as e:
        logger.error(f"[PRESETS] Error saving preset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save preset: {e}")


@router.post("/presets/delete")
def api_delete_preset(req: PresetDeleteRequest):
    """Delete a preset from the database."""
    template_id = req.template_id or "default"
    preset_id = req.preset_id

    try:
        deleted = db.delete_preset(template_id, preset_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Preset not found")

        logger.info(f"[PRESETS] Deleted preset {preset_id} from template {template_id}")
        return {"message": f"Preset '{preset_id}' deleted."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRESETS] Error deleting preset: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete preset: {e}")
