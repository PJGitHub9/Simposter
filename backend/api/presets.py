# backend/api/presets.py
from fastapi import APIRouter, HTTPException

from ..config import load_presets, save_presets
from ..schemas import PresetDeleteRequest, PresetSaveRequest

router = APIRouter()


@router.get("/presets")
def api_presets():
    return load_presets()


@router.post("/presets/save")
def api_save_preset(req: PresetSaveRequest):
    template_id = req.template_id or "default"
    preset_id = req.preset_id
    options = req.options

    data = load_presets()
    presets = data.setdefault(template_id, {}).setdefault("presets", [])

    existing = next((p for p in presets if p.get("id") == preset_id), None)
    if existing:
        existing["options"] = options
    else:
        presets.append(
            {
                "id": preset_id,
                "name": preset_id,
                "options": options,
            }
        )

    save_presets(data)
    return {"message": f"Preset '{preset_id}' saved."}


@router.post("/presets/delete")
def api_delete_preset(req: PresetDeleteRequest):
    template_id = req.template_id or "default"
    preset_id = req.preset_id

    data = load_presets()
    template_block = data.get(template_id)
    if not template_block:
        raise HTTPException(404, f"Template '{template_id}' not found")

    presets = template_block.get("presets", [])

    new_list = [p for p in presets if p.get("id") != preset_id]
    if len(new_list) == len(presets):
        raise HTTPException(404, "Preset not found")

    data[template_id]["presets"] = new_list
    save_presets(data)

    return {"message": f"Preset '{preset_id}' deleted."}
