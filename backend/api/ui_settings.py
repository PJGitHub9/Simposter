import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..config import settings
from ..schemas import UISettings

router = APIRouter()

_settings_file = Path(settings.CONFIG_DIR) / "ui_settings.json"


def _read_settings() -> UISettings:
    if not _settings_file.exists():
        return UISettings()
    try:
        data = json.loads(_settings_file.read_text(encoding="utf-8"))
        return UISettings(**data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read settings: {e}")


@router.get("/ui-settings", response_model=UISettings)
def get_ui_settings():
    return _read_settings()


@router.post("/ui-settings", response_model=UISettings)
def save_ui_settings(payload: UISettings):
    try:
        _settings_file.parent.mkdir(parents=True, exist_ok=True)
        _settings_file.write_text(payload.model_dump_json(indent=2), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save settings: {e}")
    return payload
