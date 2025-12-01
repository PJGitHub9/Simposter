import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ..config import settings
from ..schemas import UISettings

router = APIRouter()

_settings_file = Path(settings.SETTINGS_DIR) / "ui_settings.json"
_legacy_settings_file = Path(settings.CONFIG_DIR) / "ui_settings.json"


def _read_settings() -> UISettings:
    """
    Read settings from disk, creating the file with defaults if missing.
    Mirrors the simple JSON read/write pattern we use for presets.
    """
    try:
        if not _settings_file.exists() and _legacy_settings_file.exists():
            try:
                _settings_file.parent.mkdir(parents=True, exist_ok=True)
                _legacy_settings_file.replace(_settings_file)
            except OSError:
                data = json.loads(_legacy_settings_file.read_text(encoding="utf-8"))
                _settings_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        if not _settings_file.exists():
            defaults = UISettings().model_dump(
                exclude_none=False, exclude_defaults=False, exclude_unset=False
            )
            _settings_file.parent.mkdir(parents=True, exist_ok=True)
            _settings_file.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
            return UISettings(**defaults)

        data = json.loads(_settings_file.read_text(encoding="utf-8"))
        # Merge with defaults so newly added fields are included
        merged = {**UISettings().model_dump(exclude_none=False, exclude_defaults=False), **data}
        if merged != data:
            _settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return UISettings(**merged)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")


@router.get("/ui-settings")
def get_ui_settings():
    defaults = {
        "theme": "neon",
        "showBoundingBoxes": True,
        "autoSave": False,
        "posterDensity": 20,
        "saveLocation": "/output",
        "defaultLabelsToRemove": []
    }

    if not _settings_file.exists():
        return JSONResponse(content=defaults)

    data = json.loads(_settings_file.read_text(encoding="utf-8"))
    result = {**defaults, **data}
    return JSONResponse(content=result)


@router.post("/ui-settings")
def save_ui_settings(payload: UISettings):
    try:
        _settings_file.parent.mkdir(parents=True, exist_ok=True)
        # Merge defaults + current file + incoming payload to avoid losing fields
        defaults = UISettings().model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        current = _read_settings().model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        incoming = payload.model_dump(
            exclude_none=False, exclude_defaults=False, exclude_unset=False
        )
        merged = {**defaults, **current, **incoming}

        _settings_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return merged
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")
