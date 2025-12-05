# backend/api/presets.py
from pathlib import Path
import json
from fastapi import APIRouter, HTTPException

from ..config import load_presets, save_presets, USER_PRESETS_PATH, logger
from ..schemas import PresetDeleteRequest, PresetSaveRequest
from .. import database as db

router = APIRouter()


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


@router.post("/presets/save")
def api_save_preset(req: PresetSaveRequest):
    """Save a preset to the database."""
    template_id = req.template_id or "default"
    preset_id = req.preset_id
    options = req.options

    try:
        # Save to database
        db.save_preset(template_id, preset_id, preset_id, options)
        logger.info(f"[PRESETS] Saved preset {preset_id} for template {template_id}")
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
