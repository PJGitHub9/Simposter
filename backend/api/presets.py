# backend/api/presets.py
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Body

from ..config import load_presets, save_presets, USER_PRESETS_PATH, logger
from ..schemas import PresetDeleteRequest, PresetSaveRequest
from .. import database as db
from .template_manager import _get_fallback_settings
from ..middleware.validation import validate_preset_id

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


@router.get("/presets/default-template")
def api_presets_default_template():
    """Return the built-in default preset for new-user onboarding (never auto-imported)."""
    return {
        "uniformlogo": {
            "presets": [
                {
                    "id": "default",
                    "name": "Default",
                    "options": {
                        "poster_zoom": 1,
                        "poster_shift_y": -0.04,
                        "matte_height_ratio": 0.22,
                        "fade_height_ratio": 0.21,
                        "top_matte_height_ratio": 0.0,
                        "top_fade_height_ratio": 0.0,
                        "vignette_strength": 0.03,
                        "grain_amount": 0.22,
                        "logo_scale": 0.45,
                        "logo_offset": 0.88,
                        "uniform_logo_max_w": 1282,
                        "uniform_logo_max_h": 352,
                        "uniform_logo_offset_x": 0.5,
                        "uniform_logo_offset_y": 0.83,
                        "uniform_logo_h_align": "center",
                        "uniform_logo_v_align": "center",
                        "border_enabled": False,
                        "border_px": 14,
                        "border_color": "#ffffff",
                        "overlay_file": "",
                        "overlay_opacity": 0.4,
                        "overlay_mode": "screen",
                        "poster_filter": "textless",
                        "logo_preference": "white",
                        "logo_mode": "original",
                        "logo_hex": "#4b5efc",
                        "text_overlay_enabled": False,
                        "custom_text": "",
                        "font_family": "Arial",
                        "font_size": 120,
                        "font_weight": "700",
                        "text_color": "#ffffff",
                        "text_align": "center",
                        "text_transform": "uppercase",
                        "letter_spacing": 2,
                        "line_height": 1.2,
                        "position_y": 0.75,
                        "shadow_enabled": True,
                        "shadow_blur": 10,
                        "shadow_offset_x": 0,
                        "shadow_offset_y": 4,
                        "shadow_color": "#000000",
                        "shadow_opacity": 0.8,
                        "stroke_enabled": False,
                        "stroke_width": 4,
                        "stroke_color": "#000000",
                        "logoSource": "tmdb_fanart",
                        "fallbackPosterAction": "template",
                        "fallbackPosterTemplate": "uniformlogo",
                        "fallbackPosterPreset": "stock-poster",
                        "fallbackLogoAction": "template",
                        "fallbackLogoTemplate": "uniformlogo",
                        "fallbackLogoPreset": "stock-poster",
                    },
                    # Only the fields that actually differ from "options" above — merged on
                    # top of it via resolve_season_options() wherever season posters render.
                    "season_options": {
                        "logo_mode": "none",
                        "text_overlay_enabled": True,
                        "custom_text": "{season}",
                        "font_size": 150,
                        "letter_spacing": 1,
                        "position_y": 0.85,
                        "shadow_enabled": False,
                        "shadow_blur": 0,
                    },
                }
            ]
        }
    }


@router.get("/presets/export")
def api_presets_export():
    """Export all presets — IDs are internal and excluded; import generates fresh ones."""
    try:
        data = db.get_all_presets()
        # Strip internal IDs — export is name+options only
        for tdata in data.values():
            for preset in tdata.get("presets", []):
                preset.pop("id", None)
        return data
    except Exception as e:
        logger.error(f"[PRESETS] Error exporting presets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export presets: {e}")


# Default values that are stripped from compact exports to keep shared presets small
_PRESET_DEFAULTS = {
    "poster_zoom": 1, "poster_shift_y": -0.04, "matte_height_ratio": 0.22,
    "fade_height_ratio": 0.21, "top_matte_height_ratio": 0.0, "top_fade_height_ratio": 0.0,
    "vignette_strength": 0.03, "grain_amount": 0.22,
    "logo_scale": 0.45, "logo_offset": 0.88, "uniform_logo_max_w": 1282,
    "uniform_logo_max_h": 352, "uniform_logo_offset_x": 0.5, "uniform_logo_offset_y": 0.83,
    "uniform_logo_h_align": "center", "uniform_logo_v_align": "center",
    "border_enabled": False, "border_px": 14, "border_color": "#ffffff",
    "overlay_file": "", "overlay_opacity": 0.4, "overlay_mode": "screen",
    "poster_filter": "textless", "logo_preference": "white", "logo_mode": "original",
    "logo_hex": "#4b5efc", "text_overlay_enabled": False, "custom_text": "",
    "font_family": "Arial", "font_size": 120, "font_weight": "700",
    "text_color": "#ffffff", "text_align": "center", "text_transform": "uppercase",
    "letter_spacing": 2, "line_height": 1.2, "position_y": 0.75,
    "shadow_enabled": False, "shadow_blur": 10, "shadow_offset_x": 0,
    "shadow_offset_y": 4, "shadow_color": "#000000", "shadow_opacity": 0.8,
    "stroke_enabled": False, "stroke_width": 4, "stroke_color": "#000000",
    "logoSource": "tmdb_fanart",
}


def _compact_options(opts: dict) -> dict:
    """Strip fields that match built-in defaults; keep everything else."""
    return {k: v for k, v in opts.items() if _PRESET_DEFAULTS.get(k, "__missing__") != v}


@router.get("/presets/export-compact")
def api_presets_export_compact():
    """Export presets for sharing — defaults stripped from options, internal IDs omitted,
    season_options reduced to only the fields that differ from options."""
    try:
        data = db.get_all_presets()
        compact: dict = {}
        for template_id, tdata in data.items():
            compact_presets = []
            for preset in tdata.get("presets", []):
                raw_options = preset.get("options", {})
                opts = _compact_options(raw_options)
                # Diff against the raw (uncompacted) options, not the global defaults — a
                # season field's fallback is "inherit from this preset's options" via
                # resolve_season_options(), not "fall back to the factory default," so it
                # must not be stripped just because it happens to equal _PRESET_DEFAULTS.
                season_diff = db.diff_season_options(raw_options, preset.get("season_options") or {})
                # id is intentionally omitted — import will generate a fresh one to avoid conflicts
                entry: dict = {"name": preset["name"], "options": opts}
                if season_diff:
                    entry["season_options"] = season_diff
                compact_presets.append(entry)
            compact[template_id] = {"presets": compact_presets}
        return compact
    except Exception as e:
        logger.error(f"[PRESETS] Error exporting compact presets: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to export: {e}")


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

    template_id = req.template_id or "uniformlogo"
    preset_id = validate_preset_id(req.preset_id)
    # Keep season_options as None when not provided — db.save_preset will preserve the existing value
    season_options = req.season_options

    # Merge with existing preset options so fields not managed by the EditorPane
    # (fallback rules, overlayConfigId, logoSource, etc.) survive a slider-only save.
    # New values from req.options take precedence; existing unknowns are preserved.
    existing = db.get_preset(template_id, preset_id)
    if existing:
        merged = {**existing["options"], **req.options}
    else:
        merged = dict(req.options)
    options = _apply_global_template_defaults(merged)

    try:
        # Save to database (use explicit name if provided, fall back to preset_id)
        preset_name = req.name if req.name else preset_id
        db.save_preset(template_id, preset_id, preset_name, options, season_options)
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


@router.post("/presets/save-season-options")
def api_save_season_options(req: dict = Body(...)):
    """Save only the season_options for a preset without modifying the base options."""
    import json

    template_id = req.get('template_id') or "uniformlogo"
    preset_id = req.get('preset_id')
    season_options = req.get('season_options', {})
    
    if not preset_id:
        raise HTTPException(status_code=400, detail="preset_id is required")

    try:
        # Get current preset to verify it exists
        current = db.get_preset(template_id, preset_id)
        if not current:
            raise HTTPException(status_code=404, detail="Preset not found")

        # Store only what differs from the base options — the editor sends a complete
        # options blob here, but persisting it verbatim would duplicate ~45 fields that
        # are almost always identical to the series preset.
        season_diff = db.diff_season_options(current["options"], season_options)

        # Update only season_options_json in the database
        with db.get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE presets SET season_options_json = ?, updated_at = CURRENT_TIMESTAMP WHERE template_id = ? AND id = ?",
                (json.dumps(season_diff), template_id, preset_id)
            )
        
        logger.info(f"[PRESETS] Saved season options for preset {preset_id}")
        return {"message": f"Season options for preset '{preset_id}' saved."}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[PRESETS] Error saving season options: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save season options: {e}")


@router.post("/presets/delete")
def api_delete_preset(req: PresetDeleteRequest):
    """Delete a preset from the database."""
    template_id = req.template_id or "uniformlogo"
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
